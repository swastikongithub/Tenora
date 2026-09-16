import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gateway import (
    ProviderUnavailable,
    SubscriberContactRequired,
    WebhookParseError,
    get_gateway,
)
from apps.billing.models import Plan, Subscription, SubscriptionCheckout
from apps.billing.serializers import (
    CheckoutConfirmSerializer,
    CheckoutStartSerializer,
    PlanSerializer,
    SubscriptionCheckoutSerializer,
    SubscriptionSerializer,
    SubscriptionUpdateSerializer,
)
from apps.billing.services import (
    PlanChangeNotAllowed,
    PlanChangePolicy,
    CheckoutPlanMismatch,
    CheckoutService,
    CheckoutSignatureInvalid,
    IllegalStateTransition,
    PlanNotSyncedToGateway,
    SubscriptionService,
    WebhookProcessingService,
    WebhookService,
)
from apps.tenants.permissions import IsTenantMember, IsTenantOwner, RequiresCapability

logger = logging.getLogger(__name__)

NO_SUBSCRIPTION = {"detail": "This tenant has no subscription yet."}


class PlanListView(APIView):
    """
    GET /api/plans/ — global path (in GLOBAL_PATHS), no X-Tenant-ID.
    Any authenticated user sees every active plan. Plan is global data,
    so the default manager is used — never TenantScopedManager.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True)
        return Response(
            PlanSerializer(plans, many=True).data, status=status.HTTP_200_OK
        )


class CurrentSubscriptionView(APIView):
    """
    GET/PATCH /api/subscriptions/current/ — the current tenant's single
    subscription. Tenant-scoped: request.tenant / request.membership are
    resolved by TenantJWTAuthentication before this view runs.

    Read and change (plan / cancel) are OWNER only — a resident MEMBER is not a
    Tenora subscriber (property-billing plan §16.5). Every
    mutation goes through SubscriptionService — the view never assigns
    .status or .plan directly.

    There is deliberately NO `post` here anymore. Creating a local
    Subscription row from a client action was Phase 1's honest shortcut when
    no real billing existed; once money is involved it would fabricate a paid
    state (stage-d2-spec.md §1). Subscribing now goes through
    POST /api/subscriptions/current/checkout/ (a real Razorpay Subscription),
    and the local row is created only by D3 processing the verified
    subscription.activated webhook.
    """

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), IsTenantOwner()]
        # Property-billing plan §16.5: the Tenora subscription is the OWNER's
        # relationship with Tenora. A resident member must not read it — not
        # just hidden in the UI, refused here.
        return [IsAuthenticated(), IsTenantMember(), RequiresCapability("subscription.view")()]

    def _subscription(self, request):
        # Scoped manager — the sanctioned mechanism, never .filter(tenant=).
        # OneToOne, so .get() is correct (not .filter().first()).
        try:
            return (
                Subscription.objects.for_tenant(request.tenant)
                .select_related("plan")
                .get()
            )
        except Subscription.DoesNotExist:
            return None

    def _active_plan(self, plan_id):
        # Unknown and inactive collapse to the same 400 — a client has
        # no business distinguishing them.
        try:
            return Plan.objects.get(id=plan_id, is_active=True)
        except Plan.DoesNotExist:
            return None

    def get(self, request):
        subscription = self._subscription(request)
        if subscription is None:
            return Response(NO_SUBSCRIPTION, status=status.HTTP_404_NOT_FOUND)
        return Response(
            SubscriptionSerializer(subscription).data, status=status.HTTP_200_OK
        )

    def patch(self, request):
        subscription = self._subscription(request)
        if subscription is None:
            return Response(NO_SUBSCRIPTION, status=status.HTTP_404_NOT_FOUND)

        serializer = SubscriptionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "plan_id" in data:
            plan = self._active_plan(data["plan_id"])
            if plan is None:
                return Response(
                    {"plan_id": ["No active plan with this id."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if subscription.status == Subscription.Status.CANCELED:
                # Keyed to plan_id, the field the client actually sent, so the
                # frontend reads one error key for every plan-change rejection
                # (unknown plan, inactive plan, terminal subscription) instead
                # of branching on which of them it hit.
                return Response(
                    {
                        "plan_id": [
                            f"Cannot change the plan of a {subscription.status} "
                            "subscription."
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # The billing rules decide whether this change is possible at all,
            # and they answer the same whichever endpoint a client asks
            # through. A paid upgrade is NOT applied here — it becomes real
            # only when the new mandate's verified webhook activates it, so
            # this endpoint can no longer move a workspace onto a plan it has
            # not paid for.
            try:
                decision = PlanChangePolicy.classify(subscription.plan, plan)
            except PlanChangeNotAllowed as exc:
                return Response(
                    {"plan_id": [exc.message], "code": exc.code, "detail": exc.message},
                    status=status.HTTP_409_CONFLICT,
                )
            if decision == PlanChangePolicy.UPGRADE:
                message = "Upgrading requires payment. Start checkout for this plan."
                return Response(
                    {
                        "plan_id": [message],
                        "code": "upgrade_requires_checkout",
                        "detail": message,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            # NO_OP: already on this plan. Nothing is created, nothing changes,
            # and the unchanged subscription is echoed back.
        else:
            try:
                subscription = SubscriptionService.transition_status(
                    subscription, data["status"]
                )
            except IllegalStateTransition as exc:
                return Response(
                    {"status": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
                )

        return Response(
            SubscriptionSerializer(subscription).data, status=status.HTTP_200_OK
        )


class StartCheckoutView(APIView):
    """
    POST /api/subscriptions/current/checkout/ — an OWNER starts subscribing.

    Creates a real gateway subscription for the plan and returns what the
    frontend needs to open Razorpay Checkout. Creates NO local Subscription
    row — that only happens later, in D3, from the verified webhook.
    Double-click safe (see CheckoutService.create_checkout).
    """

    permission_classes = [IsAuthenticated, IsTenantOwner]

    def post(self, request):
        serializer = CheckoutStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            plan = Plan.objects.get(
                id=serializer.validated_data["plan_id"], is_active=True
            )
        except Plan.DoesNotExist:
            return Response(
                {"plan_id": ["No active plan with this id."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # An existing subscription no longer blocks checkout outright: a paid
        # UPGRADE is exactly a new mandate raised while the current plan keeps
        # running. Everything else the rules refuse is refused here too, with
        # the same codes the PATCH endpoint returns — a client cannot reach a
        # different answer by picking a different endpoint.
        current = (
            Subscription.objects.for_tenant(request.tenant)
            .select_related("plan")
            .first()
        )
        if current is not None:
            if current.status == Subscription.Status.CANCELED:
                return Response(
                    {
                        "detail": "This workspace's subscription was canceled.",
                        "code": "subscription_canceled",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            try:
                decision = PlanChangePolicy.classify(current.plan, plan)
            except PlanChangeNotAllowed as exc:
                return Response(
                    {"detail": exc.message, "code": exc.code},
                    status=status.HTTP_409_CONFLICT,
                )
            if decision == PlanChangePolicy.NO_OP:
                return Response(
                    {
                        "detail": "This workspace is already on this plan.",
                        "code": "already_on_plan",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            checkout = CheckoutService.create_checkout(
                tenant=request.tenant, plan=plan
            )
        except PlanNotSyncedToGateway:
            return Response(
                {"plan_id": ["This plan isn’t available for checkout yet."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CheckoutPlanMismatch:
            return Response(
                {
                    "detail": "A checkout for a different plan is already in "
                    "progress for this workspace."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SubscriberContactRequired as exc:
            # Fixable by the owner (e.g. Cashfree needs a phone number for the
            # mandate) — not an outage, so a distinct, actionable answer.
            return Response(
                {"detail": str(exc), "code": "subscriber_contact_required"},
                status=status.HTTP_409_CONFLICT,
            )
        except ProviderUnavailable:
            return Response(
                {
                    "detail": "The payment provider is unavailable right now. "
                    "Please try again in a moment.",
                    "code": "provider_unavailable",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        body = SubscriptionCheckoutSerializer(checkout).data
        # Publishable identifiers only — never a secret, for either provider.
        body["razorpay_key_id"] = settings.RAZORPAY_KEY_ID
        body["checkout_mode"] = (
            "production"
            if (
                settings.CASHFREE_SUBSCRIPTION_ENVIRONMENT == "production"
                if checkout.provider == "cashfree"
                else not settings.RAZORPAY_KEY_ID.startswith("rzp_test")
            )
            else "sandbox"
        )
        return Response(body, status=status.HTTP_200_OK)


class ConfirmCheckoutView(APIView):
    """
    POST /api/subscriptions/current/confirm-checkout/ — the frontend reports
    Razorpay Checkout's success callback.

    Verifies the checkout success signature via the active gateway adapter
    (a different signature and key from the webhook one). On success, marks the
    SubscriptionCheckout CONFIRMED for UI feedback / audit ONLY. Creates or
    mutates NO local Subscription row — the real activation is D3's job, from
    the webhook. A bad signature is a clean 400.
    """

    permission_classes = [IsAuthenticated, IsTenantOwner]

    def post(self, request):
        serializer = CheckoutConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            CheckoutService.confirm_checkout(
                tenant=request.tenant,
                subscription_id=(
                    data.get("subscription_id") or data.get("razorpay_subscription_id")
                ),
                report=data,
            )
        except SubscriptionCheckout.DoesNotExist:
            return Response(
                {"detail": "No checkout is in progress for this workspace."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CheckoutSignatureInvalid:
            return Response(
                {"detail": "Checkout could not be verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # "processing", never "active" — local status has not changed and won't
        # until D3 processes the real webhook.
        return Response({"status": "processing"}, status=status.HTTP_200_OK)


class SubscriptionWebhookView(APIView):
    """
    POST /api/webhooks/razorpay/ and /api/webhooks/cashfree/subscriptions/ —
    receive, verify, normalize, and deduplicate SUBSCRIPTION webhook events
    (stage-d1-spec.md §4.4).

    One view, one route per provider: the route says which provider is expected
    to call, while everything provider-specific (signature scheme, event names)
    stays in the adapter `PAYMENT_GATEWAY` selects. A delivery to the route of
    a provider that is not the configured one simply fails its signature check.

    Unauthenticated: the gateway calls this directly, there is no user session.
    The signature check (via the active adapter) IS the authentication — it is
    not skippable, and a request that fails it is rejected before anything is
    parsed or stored.

    Which header holds the signature, how the HMAC is built, and how a
    provider's event names map to the project's `EventType` vocabulary all live
    in the adapter now, not here. This view stays provider-neutral. It stores
    the verified, normalized event, then processes it into `Subscription` state
    changes inline (D3) — but that processing step's failure is caught and
    logged and can NEVER change the HTTP response: once the event is stored the
    response is 200, and a failed processing attempt is retried by
    `manage.py process_webhook_events`.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        # Read the RAW bytes first, before any DRF parsing touches the stream —
        # signature verification must run on exactly what the gateway signed.
        raw_body = request.body
        gateway = get_gateway()

        if not gateway.verify_webhook_signature(request.headers, raw_body):
            # Bad or missing signature — do not process, do not store.
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            event = gateway.parse_webhook_event(request.headers, raw_body)
        except WebhookParseError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # No unique per-delivery id → no safe dedup key, so reject.
        if not event.external_event_id:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # 200 whether newly stored or a redelivery — the dedup is a
        # unique-constraint collision inside record_event, not a check here.
        stored = WebhookService.record_event(
            external_event_id=event.external_event_id,
            event_type=event.event_type.value,
            raw_payload=event.raw_payload,
            external_subscription_id=event.external_subscription_id,
            period_start=event.period_start,
            period_end=event.period_end,
            event_created_at=event.event_created_at,
        )

        # D3: apply the event's effect inline. A redelivery re-runs this too —
        # safe, because process_event no-ops on an already-processed row. ANY
        # failure here is swallowed: the event is stored, the response stays
        # 200, and process_webhook_events will retry the row.
        try:
            WebhookProcessingService.process_event(stored)
        except Exception:  # noqa: BLE001 — deliberately broad, see docstring
            logger.exception(
                "webhook %s stored but processing failed; left for retry",
                stored.external_event_id,
            )

        return Response(status=status.HTTP_200_OK)


#: The route registered in D1 kept its name; the view outgrew it once a second
#: provider arrived.
RazorpayWebhookView = SubscriptionWebhookView

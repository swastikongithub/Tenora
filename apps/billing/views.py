import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.gateway import WebhookParseError, get_gateway
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
    CheckoutPlanMismatch,
    CheckoutService,
    CheckoutSignatureInvalid,
    IllegalStateTransition,
    PlanNotSyncedToGateway,
    SubscriptionService,
    WebhookProcessingService,
    WebhookService,
)
from apps.tenants.permissions import IsTenantMember, IsTenantOwner

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

    Read is OWNER or MEMBER; change (plan / cancel) is OWNER only. Every
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
        return [IsAuthenticated(), IsTenantMember()]

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
            try:
                subscription = SubscriptionService.change_plan(subscription, plan)
            except IllegalStateTransition as exc:
                # Keyed to plan_id, the field the client actually sent, so the
                # frontend reads one error key for every plan-change rejection
                # (unknown plan, inactive plan, terminal subscription) instead
                # of branching on which of them it hit.
                return Response(
                    {"plan_id": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
                )
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

        # Already have a real subscription? That's a plan change (an
        # update-subscription operation), not a new checkout — out of D2 scope.
        if Subscription.objects.for_tenant(request.tenant).exists():
            return Response(
                {"detail": "This tenant already has a subscription."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            plan = Plan.objects.get(
                id=serializer.validated_data["plan_id"], is_active=True
            )
        except Plan.DoesNotExist:
            return Response(
                {"plan_id": ["No active plan with this id."]},
                status=status.HTTP_400_BAD_REQUEST,
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

        body = SubscriptionCheckoutSerializer(checkout).data
        body["razorpay_key_id"] = settings.RAZORPAY_KEY_ID  # public; never the secret
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
                payment_id=data["razorpay_payment_id"],
                subscription_id=data["razorpay_subscription_id"],
                signature=data["razorpay_signature"],
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


class RazorpayWebhookView(APIView):
    """
    POST /api/webhooks/razorpay/ — receive, verify, normalize, and deduplicate
    payment-gateway webhook events (stage-d1-spec.md §4.4).

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

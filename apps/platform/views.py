"""
Platform-admin views — docs/platform-admin-spec.md, extended for Phase 1
(read-only operator surfaces) and Phase 2 (the first mutation phase) of
docs/operator-control-plane-spec.md.

This module is the ONE place in the codebase that deliberately returns
cross-tenant data in a single response. Every query here runs against the
default manager and never calls `.for_tenant()` / reads `request.tenant` —
that is the whole point, and it is stated at each query site, not only in
the spec. Every view here is gated by IsPlatformStaff (a logged-in ordinary
user must get 403, not 200). Phase 4 adds the first Root-gated surfaces —
the user role PATCH and the raw gateway payload read — which use
IsPlatformRoot instead of, never alongside, IsPlatformStaff (Root implies
Staff).

Detail/action lookups are `?id=` query-parameter based on a STATIC path
(`.../detail/`), not a `<uuid:pk>` path segment — apps.tenants.authentication
.GLOBAL_PATHS is an exact-match frozenset of literal path strings (CLAUDE.md:
"never prefix matching... a security control"), which cannot represent a
dynamic segment without either violating that exact-match rule or extending
TenantJWTAuthentication itself — and docs/operator-control-plane-spec.md's own
migration strategy reserves the only change to that file for Phase 5. A static
`.../detail/` path with the id in the query string needs neither: it is one
more literal string added to the existing frozenset, exactly like every entry
already there. Phase 2's subscription mutation uses this exact same
convention (`PATCH .../subscriptions/detail/?id=`) for the identical reason.

Phase 2 mutations are the first writes in this module. Every one of them
reuses an existing domain service unmodified
(SubscriptionService/WebhookProcessingService/ReconciliationService/
UsageMeteringService) — no new business/state-machine logic is written here.
Critical mutations (the subscription override) write their AuditEvent inside
the same transaction as the service call, via AuditService.record_critical;
observational ones (the three fallback sweeps) use
AuditService.record_observational after the sweep has already run.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.billing.models import (
    Plan,
    ReconciliationDiscrepancy,
    Subscription,
    SubscriptionCheckout,
    UsageRecord,
    WebhookEvent,
)
from apps.billing.gateway.base import EventType
from apps.billing.serializers import SubscriptionSerializer, SubscriptionUpdateSerializer
from apps.billing.services import (
    IllegalStateTransition,
    ReconciliationService,
    SubscriptionService,
    UsageMeteringService,
    WebhookProcessingService,
)
from apps.platform.models import AuditEvent
from apps.platform.pagination import PlatformPageNumberPagination
from apps.platform.permissions import IsPlatformRoot, IsPlatformStaff
from apps.platform.serializers import (
    PlatformAuditEventSerializer,
    PlatformPlanCreateSerializer,
    PlatformPlanSerializer,
    PlatformPlanUpdateSerializer,
    PlatformReconciliationDiscrepancySerializer,
    PlatformTenantSerializer,
    PlatformUserDetailSerializer,
    PlatformUserRoleUpdateSerializer,
    PlatformUserSerializer,
    PlatformWebhookEventRawSerializer,
    PlatformWebhookEventSerializer,
)
from apps.platform.services import (
    AuditService,
    LastRootProtected,
    PlanLocked,
    PlanManagementService,
    UserRoleService,
    resolve_tenants_for_external_subscription_ids,
)
from apps.platform.utils import parse_uuid_or_none
from apps.tenants.models import Membership, Tenant
from apps.tenants.serializers import MembershipSerializer, TenantSerializer
from apps.users.models import User

logger = logging.getLogger(__name__)

# Marks the "tenant has no subscription at all" bucket in the status
# breakdown. Not a Subscription.Status value — deliberately outside that
# enum so it can never collide with a real status key.
NO_SUBSCRIPTION_KEY = "NONE"

# How many of a tenant's most recent normalized webhook events the detail
# view surfaces — a fixed, small window (recent activity), not a paginated
# sub-list of its own.
RECENT_WEBHOOK_EVENTS_LIMIT = 10


class PlatformTenantListView(APIView):
    """
    GET /api/platform/tenants/ — every tenant in the system, regardless of
    who is asking. Global path (no X-Tenant-ID): there is no single tenant
    context for a platform-wide view.

    Phase 1 extends this existing endpoint with pagination and filtering
    (docs/operator-control-plane-spec.md §C) — its per-tenant row shape
    (PlatformTenantSerializer) is unchanged; only the envelope (now a
    paginated `{count, next, previous, results}` body) and the available
    `?status=&plan=&search=` filters are new.
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        # Default manager, no .for_tenant(), no request.tenant — the
        # deliberate cross-tenant read. member_count is a real annotation,
        # not a per-row Python loop.
        tenants = (
            Tenant.objects.annotate(
                member_count=Count("memberships", distinct=True)
            )
            .select_related("subscription", "subscription__plan")
            .order_by("created_at")
        )

        status_param = request.query_params.get("status")
        if status_param:
            if status_param == NO_SUBSCRIPTION_KEY:
                tenants = tenants.filter(subscription__isnull=True)
            else:
                tenants = tenants.filter(subscription__status=status_param)

        plan_param = request.query_params.get("plan")
        if plan_param:
            plan_id = parse_uuid_or_none(plan_param)
            tenants = (
                tenants.filter(subscription__plan_id=plan_id)
                if plan_id
                else tenants.none()
            )

        search = request.query_params.get("search")
        if search:
            tenants = tenants.filter(Q(name__icontains=search) | Q(slug__icontains=search))

        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(tenants, request, view=self)
        return paginator.get_paginated_response(
            PlatformTenantSerializer(page, many=True).data
        )


class PlatformTenantDetailView(APIView):
    """
    GET /api/platform/tenants/detail/?id=<uuid> — one tenant's full operator
    view: the tenant row, its memberships, its subscription (or null), and
    its most recent normalized webhook events. A malformed or unmatched id is
    404 — the boundary (non-staff -> 403) is checked before any lookup runs,
    so this endpoint never needs the tenant-facing "404, never 403" rule
    (that rule protects against confirming an object exists to a caller who
    might not be allowed to know; a platform-staff caller is always allowed
    to know).
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        tenant_id = parse_uuid_or_none(request.query_params.get("id"))
        if tenant_id is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        memberships = Membership.objects.filter(tenant=tenant).select_related("user")

        try:
            subscription = Subscription.objects.select_related("plan").get(
                tenant=tenant
            )
            subscription_data = SubscriptionSerializer(subscription).data
            external_subscription_id = subscription.external_subscription_id
        except Subscription.DoesNotExist:
            subscription_data = None
            external_subscription_id = None

        recent_events = []
        if external_subscription_id:
            events = list(
                WebhookEvent.objects.filter(
                    external_subscription_id=external_subscription_id
                ).order_by("-received_at")[:RECENT_WEBHOOK_EVENTS_LIMIT]
            )
            tenant_map = resolve_tenants_for_external_subscription_ids(
                [external_subscription_id]
            )
            recent_events = PlatformWebhookEventSerializer(
                events, many=True, context={"tenant_map": tenant_map}
            ).data

        return Response(
            {
                **TenantSerializer(tenant).data,
                "memberships": MembershipSerializer(memberships, many=True).data,
                "subscription": subscription_data,
                "recent_webhook_events": recent_events,
            },
            status=status.HTTP_200_OK,
        )


class PlatformStatsView(APIView):
    """
    GET /api/platform/stats/ — real aggregate counts, every one computed by
    the ORM (Count / annotate / TruncMonth), never hand-tallied in Python
    from a fetched list. Global path, IsPlatformStaff.

    Unchanged by Phase 1 (docs/operator-control-plane-spec.md task: "preserve
    the existing GET /api/platform/stats/") — response shape, query logic,
    and the endpoint's own tests are all untouched.
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        total_tenants = Tenant.objects.count()

        # Subscription status breakdown. Start from the ORM's grouped count,
        # then zero-fill every Status choice so the frontend never has to
        # reason about a missing key, and add the explicit "no subscription"
        # bucket (a real Count on tenants, not inferred).
        counted = {
            row["status"]: row["count"]
            for row in Subscription.objects.values("status").annotate(
                count=Count("id")
            )
        }
        status_breakdown = {
            value: counted.get(value, 0)
            for value, _label in Subscription.Status.choices
        }
        status_breakdown[NO_SUBSCRIPTION_KEY] = Tenant.objects.filter(
            subscription__isnull=True
        ).count()

        # Plan distribution — count of tenants (== subscriptions, OneToOne)
        # per plan, zero-filled across every plan so an unused plan still
        # charts as a zero bar rather than vanishing.
        per_plan = {
            row["plan_id"]: row["count"]
            for row in Subscription.objects.values("plan_id").annotate(
                count=Count("id")
            )
        }
        plan_distribution = [
            {"plan_name": plan.name, "count": per_plan.get(plan.id, 0)}
            for plan in Plan.objects.order_by("price_cents", "name")
        ]

        # Tenant signups per calendar month — genuine historical data
        # (Tenant.created_at exists on every row). Empty list on a fresh,
        # tenant-less deployment, not an error.
        signups_over_time = [
            {"month": row["month"].strftime("%Y-%m"), "count": row["count"]}
            for row in (
                Tenant.objects.annotate(month=TruncMonth("created_at"))
                .values("month")
                .annotate(count=Count("id"))
                .order_by("month")
            )
        ]

        return Response(
            {
                "total_tenants": total_tenants,
                "status_breakdown": status_breakdown,
                "plan_distribution": plan_distribution,
                "signups_over_time": signups_over_time,
            },
            status=status.HTTP_200_OK,
        )


class PlatformHealthView(APIView):
    """
    GET /api/platform/health/ — a small, honestly-derived system-pulse
    summary composed entirely of existing tables (docs
    /operator-control-plane-spec.md §B). No new persisted state.

    Field naming is deliberately literal about what each timestamp actually
    measures, rather than claiming a "last sweep ran at" guarantee this data
    can't honestly provide: ReconciliationDiscrepancy is written only when
    drift is FOUND (detection-only — a clean sweep leaves no row at all), so
    there is no reliable "last reconciliation run" signal available from
    existing tables alone. `last_discrepancy_detected_at` names exactly what
    it is; `last_usage_snapshot_at` is a reliable signal (UsageRecord is
    written on every successful snapshot, not only when something is wrong);
    `last_webhook_received_at` reports inbound activity, not sweep activity.
    A true "when did each sweep last run" tracker needs Phase 2's audit
    infrastructure and is out of scope here.

    `payment_gateway` is the literal value of settings.PAYMENT_GATEWAY — a
    provider-neutral field whose value happens to reflect whatever adapter is
    configured (docs/operator-control-plane-spec.md's Implementation Note).
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        now = timezone.now()
        last_webhook_received_at = WebhookEvent.objects.aggregate(
            value=Max("received_at")
        )["value"]
        last_usage_snapshot_at = UsageRecord.objects.aggregate(
            value=Max("recorded_at")
        )["value"]
        last_discrepancy_detected_at = ReconciliationDiscrepancy.objects.aggregate(
            value=Max("detected_at")
        )["value"]

        return Response(
            {
                "total_tenants": Tenant.objects.count(),
                "unprocessed_webhook_events": WebhookEvent.objects.filter(
                    processed=False
                ).count(),
                "discrepancies_last_24h": ReconciliationDiscrepancy.objects.filter(
                    detected_at__gte=now - timedelta(hours=24)
                ).count(),
                "last_webhook_received_at": last_webhook_received_at,
                "last_usage_snapshot_at": last_usage_snapshot_at,
                "last_discrepancy_detected_at": last_discrepancy_detected_at,
                "payment_gateway": settings.PAYMENT_GATEWAY,
            },
            status=status.HTTP_200_OK,
        )


def _plan_response(plan, http_status=status.HTTP_200_OK):
    """One plan, re-read through the same annotation the read endpoints use, so
    a mutation's response body is byte-identical in shape to a GET's."""
    annotated = Plan.objects.annotate(
        subscriber_count=Count("subscriptions", distinct=True)
    ).get(pk=plan.pk)
    return Response(PlatformPlanSerializer(annotated).data, status=http_status)


class PlatformPlanListView(APIView):
    """
    GET /api/platform/plans/ — every Plan, active or not (unlike the
    tenant-facing GET /api/plans/, which only ever returns active plans).
    `subscriber_count` is a real annotation, not a Python loop.

    POST /api/platform/plans/ — Phase 3: create a plan. Staff-tier (docs
    /operator-control-plane-spec.md §B: plan management is routine operator
    work, not Root). The write itself is PlanManagementService.create_plan,
    which owns its own transaction and its own critical audit row — this view
    validates input and shapes the response, nothing else (CLAUDE.md: "all
    mutations go through services").
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def post(self, request):
        serializer = PlatformPlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = PlanManagementService.create_plan(
                actor=request.user, **serializer.validated_data
            )
        except IntegrityError:
            # The UNIQUE(code) constraint, not the serializer's pre-check, is
            # the real guarantee — two concurrent creates of the same code
            # both pass validation and one loses here. Caught OUTSIDE the
            # service's own atomic block (CLAUDE.md), which has already rolled
            # its savepoint back, so this transaction stays usable.
            return Response(
                {"code": ["A plan with this code already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _plan_response(plan, status.HTTP_201_CREATED)

    def get(self, request):
        plans = Plan.objects.annotate(
            subscriber_count=Count("subscriptions", distinct=True)
        ).order_by("price_cents", "name")

        is_active = request.query_params.get("is_active")
        if is_active is not None:
            plans = plans.filter(is_active=is_active.strip().lower() == "true")

        search = request.query_params.get("search")
        if search:
            plans = plans.filter(Q(name__icontains=search) | Q(code__icontains=search))

        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(plans, request, view=self)
        return paginator.get_paginated_response(
            PlatformPlanSerializer(page, many=True).data
        )


class PlatformPlanDetailView(APIView):
    """
    GET /api/platform/plans/detail/?id=<uuid> — one plan, including the
    fields the tenant-facing plan list deliberately omits.

    PATCH /api/platform/plans/detail/?id=<uuid> — Phase 3: edit a plan, which
    includes archiving it (`is_active=false`). Staff-tier. There is no DELETE
    here or anywhere else in this API (spec §B): a Plan is referenced by
    subscriptions, checkouts and proration records, so archive is the only
    honest retirement, and the database would refuse the delete anyway.

    The lock rule — once `external_plan_id` is set only `name` and `is_active`
    may change — lives in PlanManagementService.update_plan, not here: it is a
    business rule, and it needs the plan instance to answer.
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def _get_plan(self, request):
        plan_id = parse_uuid_or_none(request.query_params.get("id"))
        if plan_id is None:
            return None
        try:
            return Plan.objects.get(pk=plan_id)
        except Plan.DoesNotExist:
            return None

    def get(self, request):
        plan_id = parse_uuid_or_none(request.query_params.get("id"))
        if plan_id is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            plan = Plan.objects.annotate(
                subscriber_count=Count("subscriptions", distinct=True)
            ).get(pk=plan_id)
        except Plan.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(PlatformPlanSerializer(plan).data, status=status.HTTP_200_OK)

    def patch(self, request):
        plan = self._get_plan(request)
        if plan is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = PlatformPlanUpdateSerializer(instance=plan, data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            plan = PlanManagementService.update_plan(
                actor=request.user, plan=plan, changes=dict(serializer.validated_data)
            )
        except PlanLocked as exc:
            # One field error per locked field the caller tried to change, so
            # the UI can mark the exact inputs — not a single opaque detail.
            return Response(
                {field: [str(exc)] for field in exc.fields},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            return Response(
                {"code": ["A plan with this code already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _plan_response(plan)


class PlatformPlanSyncView(APIView):
    """
    POST /api/platform/plans/sync/?id=<uuid> — Phase 3: provision this plan at
    the configured payment gateway and store the id it returns. Staff-tier.

    Provider-neutral end to end: this view names no provider, reaches no SDK,
    and returns no provider payload. It calls PlanManagementService.sync_plan,
    which calls the REUSED PlanSyncService.sync_plan, which calls
    get_gateway().create_plan() — the adapter boundary
    (docs/payment-gateway-adapter-spec.md §1). The response carries the
    external plan id and whether this call was the one that created it.

    Already synced is a 200 no-op (`created: false`), not an error and not a
    second gateway call: `external_plan_id` is immutable once set, so a
    double-clicked button cannot provision a second gateway plan.

    A gateway failure is a 502 with a fixed, generic message — the provider's
    own error text can carry request/response detail that has no business in
    an operator's browser, so it goes to the application log instead, and an
    observational audit row records that the attempt failed.
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def post(self, request):
        plan_id = parse_uuid_or_none(request.query_params.get("id"))
        if plan_id is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            plan = Plan.objects.get(pk=plan_id)
        except Plan.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            plan, created = PlanManagementService.sync_plan(
                actor=request.user, plan=plan
            )
        except Exception as exc:  # noqa: BLE001 — see docstring
            # Deliberately broad: an adapter may raise anything its provider's
            # SDK raises (a transport error, an auth error, a provider 4xx),
            # and none of those should reach the operator as a 500 with a
            # traceback or as the provider's own message.
            logger.exception(
                "platform: gateway plan sync failed — plan=%s", plan.code
            )
            PlanManagementService.record_sync_failure(
                actor=request.user, plan=plan, exc=exc
            )
            return Response(
                {
                    "detail": "The payment gateway rejected or could not "
                    "complete this sync. Check the service logs."
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        body = PlatformPlanSerializer(
            Plan.objects.annotate(
                subscriber_count=Count("subscriptions", distinct=True)
            ).get(pk=plan.pk)
        ).data
        body["created"] = created
        return Response(body, status=status.HTTP_200_OK)


# The gateway-neutral vocabulary a "tenant" query filter must resolve
# through — WebhookEvent has no tenant FK (the gateway calls the webhook
# with no tenant context; see apps.billing.models.WebhookEvent), so
# filtering "by tenant" means resolving that tenant's Subscription /
# SubscriptionCheckout external_subscription_id(s) first.
def _external_subscription_ids_for_tenant(tenant_id):
    ids = list(
        Subscription.objects.filter(tenant_id=tenant_id).values_list(
            "external_subscription_id", flat=True
        )
    )
    ids += list(
        SubscriptionCheckout.objects.filter(tenant_id=tenant_id).values_list(
            "external_subscription_id", flat=True
        )
    )
    return [i for i in ids if i]


class PlatformWebhookEventListView(APIView):
    """
    GET /api/platform/webhook-events/ — SANITIZED normalized events only
    (see PlatformWebhookEventSerializer) — never raw_payload, in Phase 1 or
    any phase; the raw diagnostic surface is Root-tier, a later phase.
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        events = WebhookEvent.objects.order_by("-received_at")

        tenant_param = request.query_params.get("tenant")
        if tenant_param:
            tenant_id = parse_uuid_or_none(tenant_param)
            if tenant_id is None:
                events = events.none()
            else:
                ext_ids = _external_subscription_ids_for_tenant(tenant_id)
                events = (
                    events.filter(external_subscription_id__in=ext_ids)
                    if ext_ids
                    else events.none()
                )

        event_type = request.query_params.get("event_type")
        if event_type:
            valid_types = {e.value for e in EventType}
            events = (
                events.filter(event_type=event_type)
                if event_type in valid_types
                else events.none()
            )

        processed = request.query_params.get("processed")
        if processed is not None:
            normalized = processed.strip().lower()
            if normalized in ("true", "1"):
                events = events.filter(processed=True)
            elif normalized in ("false", "0"):
                events = events.filter(processed=False)
            # any other value: filter is ignored, matching the "malformed
            # boolean doesn't imply a narrow intent" call in the spec review

        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(events, request, view=self)
        page_objs = list(page)
        tenant_map = resolve_tenants_for_external_subscription_ids(
            [e.external_subscription_id for e in page_objs]
        )
        return paginator.get_paginated_response(
            PlatformWebhookEventSerializer(
                page_objs, many=True, context={"tenant_map": tenant_map}
            ).data
        )


class PlatformWebhookEventDetailView(APIView):
    """GET /api/platform/webhook-events/detail/?id=<uuid> — the same
    sanitized fields as the list, never raw_payload."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        event_id = parse_uuid_or_none(request.query_params.get("id"))
        if event_id is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            event = WebhookEvent.objects.get(pk=event_id)
        except WebhookEvent.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        tenant_map = resolve_tenants_for_external_subscription_ids(
            [event.external_subscription_id]
        )
        return Response(
            PlatformWebhookEventSerializer(
                event, context={"tenant_map": tenant_map}
            ).data,
            status=status.HTTP_200_OK,
        )


class PlatformReconciliationDiscrepancyListView(APIView):
    """GET /api/platform/reconciliation-discrepancies/ — the immutable
    detection-only audit trail, unfiltered by default, newest first."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        discrepancies = ReconciliationDiscrepancy.objects.select_related(
            "tenant"
        ).order_by("-detected_at")

        tenant_param = request.query_params.get("tenant")
        if tenant_param:
            tenant_id = parse_uuid_or_none(tenant_param)
            discrepancies = (
                discrepancies.filter(tenant_id=tenant_id)
                if tenant_id
                else discrepancies.none()
            )

        category = request.query_params.get("category")
        if category:
            valid_categories = {c for c, _label in ReconciliationDiscrepancy.Category.choices}
            discrepancies = (
                discrepancies.filter(category=category)
                if category in valid_categories
                else discrepancies.none()
            )

        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(discrepancies, request, view=self)
        return paginator.get_paginated_response(
            PlatformReconciliationDiscrepancySerializer(page, many=True).data
        )


class PlatformUserListView(APIView):
    """GET /api/platform/users/ — every user in the system. Platform-staff
    only; never exposes a password."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        users = User.objects.order_by("email")

        is_staff = request.query_params.get("is_staff")
        if is_staff is not None:
            users = users.filter(is_staff=is_staff.strip().lower() == "true")

        search = request.query_params.get("search")
        if search:
            users = users.filter(email__icontains=search)

        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(users, request, view=self)
        return paginator.get_paginated_response(
            PlatformUserSerializer(page, many=True).data
        )


class PlatformUserDetailView(APIView):
    """
    GET /api/platform/users/detail/?id=<uuid> — Staff-tier: one user, plus
    which tenants they belong to and with what role (the flattened
    {**TenantSerializer(tenant).data, "role": ...} shape MyTenantsView
    already uses for the mirror-image "tenants I belong to" query).

    PATCH /api/platform/users/detail/?id=<uuid> — Phase 4, ROOT-tier ONLY
    (docs/operator-control-plane-spec.md §C): change a user's platform roles.
    The read and the write sit on one path with two tiers, so `get_permissions`
    resolves the tier per method rather than one class-level list — the
    alternative, a second URL for the write, would put "who may read a user"
    and "who may change one" in two places that could drift.

    The mutation is UserRoleService.update_roles, which owns its transaction,
    its critical audit row, and the last-root invariant. This view adds no
    guard of its own: a second copy of that rule here is exactly how the two
    would eventually disagree.
    """

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), IsPlatformRoot()]
        return [IsAuthenticated(), IsPlatformStaff()]

    def _get_user(self, request):
        user_id = parse_uuid_or_none(request.query_params.get("id"))
        if user_id is None:
            return None
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def get(self, request):
        user = self._get_user(request)
        if user is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        memberships = [
            {**TenantSerializer(m.tenant).data, "role": m.role}
            for m in Membership.objects.select_related("tenant").filter(user=user)
        ]
        return Response(
            PlatformUserDetailSerializer(
                user, context={"memberships": memberships}
            ).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        user = self._get_user(request)
        if user is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = PlatformUserRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = UserRoleService.update_roles(
                actor=request.user,
                user=user,
                changes=dict(serializer.validated_data),
            )
        except LastRootProtected as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(PlatformUserSerializer(user).data, status=status.HTTP_200_OK)


class PlatformWebhookEventRawView(APIView):
    """
    GET /api/platform/webhook-events/raw/?id=<uuid> — Phase 4, ROOT-tier ONLY
    (docs/operator-control-plane-spec.md §B "Webhook management — normalized
    surface, isolated raw diagnostic"): the normalized fields plus the
    provider's raw payload.

    This is the one surface in the whole control plane that returns provider
    data verbatim, which is exactly why it is a separate path with its own
    narrower gate rather than a `?include_raw=1` flag on the Staff-tier detail
    read — a query parameter that widens a response's audience is the kind of
    thing that gets copied into a URL and forgotten.

    A read, so the audit is observational (spec's own categorisation:
    "webhook raw payload viewed"). Best-effort by contract: a failed audit
    write must not deny a Root operator the diagnostic they came for, and the
    request itself changed nothing that the row would be the only record of.
    """

    permission_classes = [IsAuthenticated, IsPlatformRoot]

    def get(self, request):
        event_id = parse_uuid_or_none(request.query_params.get("id"))
        if event_id is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            event = WebhookEvent.objects.get(pk=event_id)
        except WebhookEvent.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        tenant_map = resolve_tenants_for_external_subscription_ids(
            [event.external_subscription_id]
        )
        AuditService.record_observational(
            actor=request.user,
            action="webhook.raw_payload_viewed",
            target_type="WebhookEvent",
            target_id=event.id,
            summary=f"Viewed raw gateway payload for event {event.external_event_id}",
            # The delivery id and event type only — never any part of the
            # payload itself, which is the entire thing this row exists to
            # record the VIEWING of.
            metadata={
                "external_event_id": event.external_event_id,
                "event_type": event.event_type,
            },
        )
        return Response(
            PlatformWebhookEventRawSerializer(
                event, context={"tenant_map": tenant_map}
            ).data,
            status=status.HTTP_200_OK,
        )


class PlatformSubscriptionDetailView(APIView):
    """
    PATCH /api/platform/subscriptions/detail/?id=<uuid> — an operator
    override of one tenant's subscription. Staff-tier (docs
    /operator-control-plane-spec.md §B: "subscription overrides" are
    routine, Staff-gated work, not Root).

    Reuses SubscriptionUpdateSerializer (apps.billing.serializers) verbatim
    — the same `{plan_id}` XOR `{status}` input contract and validation the
    tenant-facing PATCH /api/subscriptions/current/ already enforces, so
    there is exactly one place that decides what "ambiguous" or "empty"
    input means. Every state/plan change itself goes through
    SubscriptionService.change_plan / .transition_status — this view never
    assigns `.status` or `.plan` directly, and cannot express a transition
    those services don't already allow.

    Critical audit (docs/operator-control-plane-spec.md's list): the
    service call and AuditService.record_critical are wrapped in one
    `transaction.atomic()` block here, in the VIEW — not inside
    SubscriptionService, which stays completely unmodified. The service's
    own `@transaction.atomic` decorator nests as a savepoint inside this
    outer transaction, so a failed audit write rolls the subscription
    change back too.
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def _get_subscription(self, request):
        sub_id = parse_uuid_or_none(request.query_params.get("id"))
        if sub_id is None:
            return None
        try:
            return Subscription.objects.select_related("plan", "tenant").get(pk=sub_id)
        except Subscription.DoesNotExist:
            return None

    def patch(self, request):
        subscription = self._get_subscription(request)
        if subscription is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = SubscriptionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "plan_id" in data:
            try:
                plan = Plan.objects.get(id=data["plan_id"], is_active=True)
            except Plan.DoesNotExist:
                return Response(
                    {"plan_id": ["No active plan with this id."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            from_plan_code = subscription.plan.code
            tenant = subscription.tenant
            try:
                with transaction.atomic():
                    subscription = SubscriptionService.change_plan(subscription, plan)
                    AuditService.record_critical(
                        actor=request.user,
                        action="subscription.plan_changed",
                        target_type="Subscription",
                        target_id=subscription.id,
                        summary=(
                            f"Changed plan for tenant {tenant.slug} "
                            f"from {from_plan_code} to {plan.code}"
                        ),
                        metadata={
                            "tenant_id": str(tenant.id),
                            "from_plan": from_plan_code,
                            "to_plan": plan.code,
                        },
                    )
            except IllegalStateTransition as exc:
                return Response(
                    {"plan_id": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
                )
        else:
            from_status = subscription.status
            to_status = data["status"]
            tenant = subscription.tenant
            try:
                with transaction.atomic():
                    subscription = SubscriptionService.transition_status(
                        subscription, to_status
                    )
                    AuditService.record_critical(
                        actor=request.user,
                        action="subscription.transitioned",
                        target_type="Subscription",
                        target_id=subscription.id,
                        summary=(
                            f"Transitioned subscription for tenant {tenant.slug} "
                            f"from {from_status} to {to_status}"
                        ),
                        metadata={
                            "tenant_id": str(tenant.id),
                            "from_status": from_status,
                            "to_status": to_status,
                        },
                    )
            except IllegalStateTransition as exc:
                return Response(
                    {"status": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST
                )

        return Response(SubscriptionSerializer(subscription).data, status=status.HTTP_200_OK)


class _PlatformSweepView(APIView):
    """
    Shared shape for the three fallback sweep triggers — docs
    /operator-control-plane-spec.md §B "Fallback sweep controls — explicitly
    temporary". Each subclass calls exactly one existing sweep-all service
    entry point (no orchestration logic written here) and records an
    observational audit entry describing the outcome. None of these three
    service calls can raise under normal operation — each already catches
    its own per-row/per-subscription failures internally and reports them
    in its result object (see apps.billing.services) — so this base class
    does not add its own try/except around the sweep call: a genuinely
    unexpected exception must surface as a 500, never be swallowed to make
    the button appear successful.
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "platform-sweep"


class PlatformWebhookProcessPendingView(_PlatformSweepView):
    """POST /api/platform/webhook-events/process-pending/ — reuses
    WebhookProcessingService.process_pending() exactly."""

    def post(self, request):
        result = WebhookProcessingService.process_pending()
        body = {
            "total": result.total,
            "processed": len(result.processed),
            "deferred": len(result.deferred),
            "failed": len(result.failed),
        }
        AuditService.record_observational(
            actor=request.user,
            action="webhook.sweep_triggered",
            target_type="WebhookEvent",
            target_id="*",
            summary=(
                f"Webhook retry sweep: {body['total']} checked, "
                f"{body['processed']} processed, {body['deferred']} deferred, "
                f"{body['failed']} failed"
            ),
            metadata=body,
        )
        return Response(body, status=status.HTTP_200_OK)


class PlatformReconciliationRunView(_PlatformSweepView):
    """POST /api/platform/reconciliation/run/ — reuses
    ReconciliationService.reconcile_all() exactly."""

    def post(self, request):
        result = ReconciliationService.reconcile_all()
        body = {
            "total": result.total,
            "matched": len(result.matched),
            "discrepancies": len(result.discrepancies),
            "unavailable": len(result.unavailable),
            "skipped": len(result.skipped),
            "errors": len(result.errors),
        }
        AuditService.record_observational(
            actor=request.user,
            action="reconciliation.sweep_triggered",
            target_type="Subscription",
            target_id="*",
            summary=(
                f"Reconciliation sweep: {body['total']} checked, "
                f"{body['discrepancies']} discrepancies found"
            ),
            metadata=body,
        )
        return Response(body, status=status.HTTP_200_OK)


class PlatformUsageRunView(_PlatformSweepView):
    """POST /api/platform/usage/run/ — reuses
    UsageMeteringService.snapshot_all_subscribed() exactly."""

    def post(self, request):
        result = UsageMeteringService.snapshot_all_subscribed()
        body = {
            "total": result.total,
            "created": len(result.records),
            "existing": result.existing,
            "skipped": result.skipped,
        }
        AuditService.record_observational(
            actor=request.user,
            action="usage.sweep_triggered",
            target_type="Tenant",
            target_id="*",
            summary=(
                f"Usage snapshot sweep: {body['total']} tenants, "
                f"{body['created']} new snapshots, {body['existing']} already "
                f"existed, {body['skipped']} skipped"
            ),
            metadata=body,
        )
        return Response(body, status=status.HTTP_200_OK)


class PlatformAuditLogListView(APIView):
    """
    GET /api/platform/audit-log/ — every recorded operator action, newest
    first. Staff-tier (a read, like every other list in this module).
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        events = AuditEvent.objects.select_related("actor").order_by("-created_at")

        actor_param = request.query_params.get("actor")
        if actor_param:
            actor_id = parse_uuid_or_none(actor_param)
            events = events.filter(actor_id=actor_id) if actor_id else events.none()

        action = request.query_params.get("action")
        if action:
            events = events.filter(action=action)

        target_type = request.query_params.get("target_type")
        if target_type:
            events = events.filter(target_type=target_type)

        is_critical = request.query_params.get("is_critical")
        if is_critical is not None:
            normalized = is_critical.strip().lower()
            if normalized in ("true", "1"):
                events = events.filter(is_critical=True)
            elif normalized in ("false", "0"):
                events = events.filter(is_critical=False)

        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(events, request, view=self)
        return paginator.get_paginated_response(
            PlatformAuditEventSerializer(page, many=True).data
        )

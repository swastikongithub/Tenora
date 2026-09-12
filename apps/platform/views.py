"""
Platform-admin views — docs/platform-admin-spec.md, extended for Phase 1 of
docs/operator-control-plane-spec.md (read-only operator surfaces).

This module is the ONE place in the codebase that deliberately returns
cross-tenant data in a single response. Every query here runs against the
default manager and never calls `.for_tenant()` / reads `request.tenant` —
that is the whole point, and it is stated at each query site, not only in
the spec. Every view here is gated by IsPlatformStaff (a logged-in ordinary
user must get 403, not 200).

Phase 1 is read-only end to end: no view in this module writes anything.
Detail lookups are `?id=` query-parameter based on a STATIC path
(`.../detail/`), not a `<uuid:pk>` path segment — apps.tenants.authentication
.GLOBAL_PATHS is an exact-match frozenset of literal path strings (CLAUDE.md:
"never prefix matching... a security control"), which cannot represent a
dynamic segment without either violating that exact-match rule or extending
TenantJWTAuthentication itself — and docs/operator-control-plane-spec.md's own
migration strategy reserves the only change to that file for Phase 5. A static
`.../detail/` path with the id in the query string needs neither: it is one
more literal string added to the existing frozenset, exactly like every entry
already there.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
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
from apps.platform.pagination import PlatformPageNumberPagination
from apps.platform.permissions import IsPlatformStaff
from apps.platform.serializers import (
    PlatformPlanSerializer,
    PlatformReconciliationDiscrepancySerializer,
    PlatformTenantSerializer,
    PlatformUserDetailSerializer,
    PlatformUserSerializer,
    PlatformWebhookEventSerializer,
)
from apps.platform.services import resolve_tenants_for_external_subscription_ids
from apps.platform.utils import parse_uuid_or_none
from apps.tenants.models import Membership, Tenant
from apps.tenants.serializers import MembershipSerializer, TenantSerializer
from apps.billing.serializers import SubscriptionSerializer
from apps.users.models import User

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


class PlatformPlanListView(APIView):
    """
    GET /api/platform/plans/ — every Plan, active or not (unlike the
    tenant-facing GET /api/plans/, which only ever returns active plans).
    `subscriber_count` is a real annotation, not a Python loop.
    """

    permission_classes = [IsAuthenticated, IsPlatformStaff]

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
    """GET /api/platform/plans/detail/?id=<uuid> — one plan, including the
    fields the tenant-facing plan list deliberately omits."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]

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
    """GET /api/platform/users/detail/?id=<uuid> — one user, plus which
    tenants they belong to and with what role (the flattened
    {**TenantSerializer(tenant).data, "role": ...} shape MyTenantsView
    already uses for the mirror-image "tenants I belong to" query)."""

    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request):
        user_id = parse_uuid_or_none(request.query_params.get("id"))
        if user_id is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
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

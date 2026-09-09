"""
Platform-admin views — docs/platform-admin-spec.md.

This module is the ONE place in the codebase that deliberately returns
cross-tenant data in a single response. Every query here runs against the
default manager and never calls `.for_tenant()` / reads `request.tenant` —
that is the whole point, and it is stated at each query site, not only in
the spec. Both views are gated by IsPlatformStaff (a logged-in ordinary
user must get 403, not 200).
"""

from django.db.models import Count
from django.db.models.functions import TruncMonth
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Plan, Subscription
from apps.platform.permissions import IsPlatformStaff
from apps.platform.serializers import PlatformTenantSerializer
from apps.tenants.models import Tenant

# Marks the "tenant has no subscription at all" bucket in the status
# breakdown. Not a Subscription.Status value — deliberately outside that
# enum so it can never collide with a real status key.
NO_SUBSCRIPTION_KEY = "NONE"


class PlatformTenantListView(APIView):
    """
    GET /api/platform/tenants/ — every tenant in the system, regardless of
    who is asking. Global path (no X-Tenant-ID): there is no single tenant
    context for a platform-wide view.
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
        return Response(
            PlatformTenantSerializer(tenants, many=True).data,
            status=status.HTTP_200_OK,
        )


class PlatformStatsView(APIView):
    """
    GET /api/platform/stats/ — real aggregate counts, every one computed by
    the ORM (Count / annotate / TruncMonth), never hand-tallied in Python
    from a fetched list. Global path, IsPlatformStaff.
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

"""
Platform-admin PROPERTY BILLING visibility (property-billing plan §15, §16.3).

Like apps/platform/views.py, this module deliberately returns cross-workspace
data, and it is the only other place that does: every query here runs on the
default manager without `.for_tenant()`, stated at each site. Every read is
gated by IsPlatformStaff; the one mutation (workspace role promote/demote) by
IsPlatformRoot. No ordinary workspace endpoint gained cross-tenant access — the
owner/resident endpoints in apps/properties remain strictly tenant-scoped.

Detail lookups use the static `.../detail/?id=` convention for the same
GLOBAL_PATHS exact-match reason documented in apps/platform/views.py.

Aggregates reuse apps.properties.reporting / aging, so "billed", "collected",
"outstanding" and "overdue" mean exactly what they mean on an owner's dashboard.
"""

from django.db.models import Count, Q, Sum
from django.http import FileResponse
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Subscription
from apps.billing.serializers import SubscriptionSerializer
from apps.platform.pagination import PlatformPageNumberPagination
from apps.platform.permissions import IsPlatformRoot, IsPlatformStaff
from apps.platform.services import AuditService, LastWorkspaceOwnerProtected, WorkspaceRoleService
from apps.platform.utils import parse_uuid_or_none
from apps.properties import aging, reporting
from apps.properties.filters import filter_bills, filter_payments, filter_receipts
from apps.properties.models import (
    Bill,
    BillLineItem,
    Lease,
    MeterReading,
    Payment,
    Property,
    Receipt,
    Resident,
    Unit,
)
from apps.properties.serializers import (
    BillDetailSerializer,
    BillSerializer,
    LeaseSerializer,
    PaymentSerializer,
    PropertySerializer,
    ReceiptSerializer,
    ResidentSerializer,
    UnitSerializer,
)
from apps.properties.views import BILL_LIST_PREFETCH, aging_payload
from apps.tenants.models import Membership, Tenant
from apps.tenants.serializers import MembershipSerializer, TenantSerializer

ISSUED = reporting.ISSUED


def _not_found():
    return Response(status=status.HTTP_404_NOT_FOUND)


def _with_tenant_names(rows):
    names = dict(Tenant.objects.filter(pk__in={r["tenant_id"] for r in rows}).values_list("id", "name"))
    return [{**r, "tenant_name": names.get(parse_uuid_or_none(r["tenant_id"]), "")} for r in rows]


class _StaffView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformStaff]


class PlatformPropertyBillingSummaryView(_StaffView):
    """GET /api/platform/property-billing/summary/?tenant=&period=YYYY-MM"""

    def get(self, request):
        today = aging.server_today()
        # Cross-workspace by design: default managers, no for_tenant().
        bills = Bill.objects.all()
        payments = Payment.objects.all()
        tenants = Tenant.objects.all()
        tenant_param = request.query_params.get("tenant")
        if tenant_param:
            tenant_id = parse_uuid_or_none(tenant_param)
            bills = bills.filter(tenant_id=tenant_id) if tenant_id else bills.none()
            payments = payments.filter(tenant_id=tenant_id) if tenant_id else payments.none()
            tenants = tenants.filter(pk=tenant_id) if tenant_id else tenants.none()
        start, _ = reporting.period_from_param(request.query_params.get("period"), today)
        issued = bills.filter(status__in=ISSUED)
        totals = issued.aggregate(billed=Sum("total_cents"), collected=Sum("amount_paid_cents"))
        completed = payments.filter(status=Payment.Status.COMPLETED)
        aging_report = reporting.aging_summary(bills, today)
        units = BillLineItem.objects.filter(bill__in=issued, type=BillLineItem.Type.ELECTRICITY).aggregate(
            s=Sum("quantity")
        )["s"]
        return Response(
            {
                "workspaces": tenants.count(),
                "active_subscriptions": Subscription.objects.filter(
                    tenant__in=tenants, status=Subscription.Status.ACTIVE
                ).count(),
                "properties": Property.objects.filter(tenant__in=tenants).count(),
                "residents": Resident.objects.filter(tenant__in=tenants, status=Resident.Status.ACTIVE).count(),
                "total_bills": issued.count(),
                "total_billed_cents": totals["billed"] or 0,
                "total_collected_cents": totals["collected"] or 0,
                "total_outstanding_cents": aging_report["total_outstanding_cents"],
                "total_overdue_cents": aging_report["total_overdue_cents"],
                "total_payments": completed.count(),
                "total_payments_cents": completed.aggregate(s=Sum("amount_cents"))["s"] or 0,
                "electricity_units": str(units or 0),
                "aging": aging_report["buckets"],
                "current_period": reporting.period_summary(bills, start, today),
                "monthly": reporting.monthly_series(bills, payments, today, 12),
                "electricity_by_unit": _with_tenant_names(reporting.electricity_by_unit(bills, start)),
                "period": start.strftime("%Y-%m"),
            }
        )


class PlatformPropertyWorkspaceListView(_StaffView):
    """GET /api/platform/property-billing/workspaces/?search= — every workspace
    with its owner(s), Tenora subscription, and property-billing totals."""

    def get(self, request):
        today = aging.server_today()
        qs = Tenant.objects.select_related("subscription__plan").order_by("name")
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(slug__icontains=search))
        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        ids = [t.id for t in page]
        totals = {
            row["tenant_id"]: row
            for row in Bill.objects.filter(tenant_id__in=ids, status__in=ISSUED)
            .values("tenant_id")
            .annotate(billed=Sum("total_cents"), collected=Sum("amount_paid_cents"), bills=Count("id"))
        }
        overdue = {
            row["tenant_id"]: row
            for row in Bill.objects.filter(
                tenant_id__in=ids, status__in=aging.OPEN_STATUSES, due_date__lt=today
            )
            .values("tenant_id")
            .annotate(count=Count("id"), total=Sum("total_cents"), paid=Sum("amount_paid_cents"))
        }
        counts = {
            row["tenant_id"]: row["n"]
            for row in Property.objects.filter(tenant_id__in=ids).values("tenant_id").annotate(n=Count("id"))
        }
        residents = {
            row["tenant_id"]: row["n"]
            for row in Resident.objects.filter(tenant_id__in=ids, status=Resident.Status.ACTIVE)
            .values("tenant_id")
            .annotate(n=Count("id"))
        }
        owners = {}
        for m in Membership.objects.filter(
            tenant_id__in=ids, role=Membership.Role.OWNER, status=Membership.Status.ACTIVE
        ).select_related("user"):
            owners.setdefault(m.tenant_id, []).append(m.user.email)
        rows = []
        for t in page:
            total = totals.get(t.id, {})
            od = overdue.get(t.id, {})
            try:
                sub = t.subscription
            except Subscription.DoesNotExist:
                sub = None
            billed = total.get("billed") or 0
            collected = total.get("collected") or 0
            rows.append(
                {
                    **TenantSerializer(t).data,
                    "closed_at": t.closed_at,
                    "owners": owners.get(t.id, []),
                    "subscription_status": sub.status if sub else None,
                    "plan_name": sub.plan.name if sub else None,
                    "properties": counts.get(t.id, 0),
                    "residents": residents.get(t.id, 0),
                    "bills": total.get("bills") or 0,
                    "billed_cents": billed,
                    "collected_cents": collected,
                    "outstanding_cents": billed - collected,
                    "overdue_bills": od.get("count") or 0,
                    "overdue_cents": (od.get("total") or 0) - (od.get("paid") or 0),
                }
            )
        return paginator.get_paginated_response(rows)


class PlatformPropertyWorkspaceDetailView(_StaffView):
    """GET /api/platform/property-billing/workspaces/detail/?id= — one workspace's
    drill-down: owners, subscription, properties -> units -> residents/leases,
    residents with their balances, and the aging report."""

    def get(self, request):
        tenant_id = parse_uuid_or_none(request.query_params.get("id"))
        tenant = Tenant.objects.filter(pk=tenant_id).first() if tenant_id else None
        if tenant is None:
            return _not_found()
        today = aging.server_today()
        memberships = Membership.objects.filter(tenant=tenant).select_related("user").order_by("role", "created_at")
        subscription = Subscription.objects.filter(tenant=tenant).select_related("plan").first()
        properties = Property.objects.filter(tenant=tenant).order_by("name")
        units = Unit.objects.filter(tenant=tenant).select_related("property").order_by("identifier")
        leases = Lease.objects.filter(tenant=tenant).select_related("unit__property", "resident").order_by("-start_date")
        bills = Bill.objects.filter(tenant=tenant)
        residents = Resident.objects.filter(tenant=tenant).select_related("user").order_by("display_name")
        balances = {
            row["resident_id"]: row
            for row in bills.filter(status__in=ISSUED)
            .values("resident_id")
            .annotate(billed=Sum("total_cents"), paid=Sum("amount_paid_cents"), count=Count("id"))
        }
        unit_rows = {}
        for u in units:
            unit_rows.setdefault(u.property_id, []).append(
                {
                    **UnitSerializer(u).data,
                    "leases": [LeaseSerializer(l).data for l in leases if l.unit_id == u.id],
                }
            )
        return Response(
            {
                **TenantSerializer(tenant).data,
                "closed_at": tenant.closed_at,
                "memberships": MembershipSerializer(memberships, many=True).data,
                "subscription": SubscriptionSerializer(subscription).data if subscription else None,
                "properties": [
                    {**PropertySerializer(p).data, "units": unit_rows.get(p.id, [])} for p in properties
                ],
                "residents": [
                    {
                        **ResidentSerializer(r).data,
                        "bills": (balances.get(r.id) or {}).get("count") or 0,
                        "billed_cents": (balances.get(r.id) or {}).get("billed") or 0,
                        "paid_cents": (balances.get(r.id) or {}).get("paid") or 0,
                    }
                    for r in residents
                ],
                "aging": aging_payload(reporting.aging_summary(bills, today)),
                "current_period": reporting.period_summary(bills, reporting.month_start(today), today),
            }
        )


class PlatformPropertyBillListView(_StaffView):
    """GET /api/platform/property-billing/bills/ — global bill search. Filters:
    tenant, property, unit, resident, period, status, payment_status, overdue,
    aging, search (the same parameters as the owner's /api/bills/)."""

    def get(self, request):
        today = aging.server_today()
        qs = filter_bills(Bill.objects.all(), request.query_params, today)
        qs = qs.select_related("tenant").prefetch_related(BILL_LIST_PREFETCH).order_by("-period_start", "tenant__name")
        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = BillSerializer(page, many=True, context={"today": today}).data
        for row, bill in zip(data, page):
            row["tenant_id"] = str(bill.tenant_id)
            row["tenant_name"] = bill.tenant.name
        return paginator.get_paginated_response(data)


class PlatformPropertyBillDetailView(_StaffView):
    def get(self, request):
        bill_id = parse_uuid_or_none(request.query_params.get("id"))
        bill = Bill.objects.select_related("tenant").filter(pk=bill_id).first() if bill_id else None
        if bill is None:
            return _not_found()
        data = BillDetailSerializer(bill, context={"today": aging.server_today()}).data
        return Response({**data, "tenant_id": str(bill.tenant_id), "tenant_name": bill.tenant.name})


class PlatformPropertyPaymentListView(_StaffView):
    def get(self, request):
        qs = filter_payments(Payment.objects.all(), request.query_params)
        qs = qs.select_related("bill", "receipt", "tenant").order_by("-payment_date", "-created_at")
        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = PaymentSerializer(page, many=True).data
        for row, payment in zip(data, page):
            row["tenant_id"] = str(payment.tenant_id)
            row["tenant_name"] = payment.tenant.name
        return paginator.get_paginated_response(data)


class PlatformPropertyReceiptListView(_StaffView):
    def get(self, request):
        qs = filter_receipts(Receipt.objects.all(), request.query_params)
        qs = qs.select_related("payment", "bill", "tenant").order_by("-issued_at")
        paginator = PlatformPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = ReceiptSerializer(page, many=True).data
        for row, receipt in zip(data, page):
            row["tenant_id"] = str(receipt.tenant_id)
            row["tenant_name"] = receipt.tenant.name
        return paginator.get_paginated_response(data)


class PlatformReadingProofView(_StaffView):
    """GET /api/platform/property-billing/reading-proof/?id= — a meter-reading
    proof image for operator inspection. Observational audit: viewing a
    resident's evidence is worth a trail, not a transaction."""

    def get(self, request):
        reading_id = parse_uuid_or_none(request.query_params.get("id"))
        reading = MeterReading.objects.filter(pk=reading_id).first() if reading_id else None
        if reading is None or not reading.proof:
            return _not_found()
        AuditService.record_observational(
            actor=request.user,
            action="platform.reading_proof_viewed",
            target_type="MeterReading",
            target_id=reading.id,
            summary="Viewed a meter-reading proof image",
            metadata={"tenant_id": str(reading.tenant_id)},
        )
        response = FileResponse(reading.proof.open("rb"), content_type=reading.proof_content_type or "application/octet-stream")
        response["Content-Disposition"] = "inline"
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class PlatformMembershipRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices)


class PlatformMembershipDetailView(APIView):
    """PATCH /api/platform/memberships/detail/?id= — {role}. ROOT tier: promote a
    member to owner or demote an owner, regardless of plan (plan §4.1.1)."""

    permission_classes = [IsAuthenticated, IsPlatformRoot]

    def patch(self, request):
        membership_id = parse_uuid_or_none(request.query_params.get("id"))
        membership = (
            Membership.objects.select_related("user", "tenant").filter(pk=membership_id).first()
            if membership_id
            else None
        )
        if membership is None:
            return _not_found()
        serializer = PlatformMembershipRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = WorkspaceRoleService.set_role(
                actor=request.user, membership=membership, role=serializer.validated_data["role"]
            )
        except LastWorkspaceOwnerProtected:
            return Response(
                {
                    "detail": "This is the workspace's only active owner. Promote another member first.",
                    "code": "last_workspace_owner",
                },
                status=status.HTTP_409_CONFLICT,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(MembershipSerializer(membership).data)

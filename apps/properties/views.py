"""
Property billing endpoints — every one tenant-scoped: the workspace comes only
from X-Tenant-ID resolved to an ACTIVE membership by TenantJWTAuthentication,
never from a request body or query parameter.

Authorization is by capability (apps.tenants.permissions.ROLE_CAPABILITIES):

  * owner-only endpoints require the named capability for the method;
  * bills, payments, receipts, proof images and the residency endpoint are
    ROLE-AWARE reads: an owner sees the workspace, a resident sees only rows
    joined to their OWN Resident profile (resident__user = request.user) — the
    resident id is never taken from the client.

Object lookups always go through `.for_tenant(request.tenant)` (plus the
resident filter where relevant). An id from another workspace, or another
resident's bill, is therefore a 404 — never a 403 that would confirm it exists.
"""

from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.properties import aging, reporting
from apps.properties.filters import filter_bills, filter_payments, filter_receipts
from apps.properties.models import (
    Bill,
    BillingCycle,
    BillLineItem,
    Lease,
    Meter,
    MeterReading,
    Payment,
    Property,
    Receipt,
    Resident,
    Tariff,
    Unit,
)
from apps.properties.reminders import send_billing_reminders
from apps.properties.serializers import (
    BillCorrectionInputSerializer,
    BillCorrectionSerializer,
    BillDetailSerializer,
    BillingCycleSerializer,
    BillSerializer,
    CycleGenerateSerializer,
    CycleOpenSerializer,
    LeaseEndSerializer,
    LeaseInputSerializer,
    LeaseSerializer,
    LeaseUpdateSerializer,
    LineItemInputSerializer,
    LineItemSerializer,
    MeterInputSerializer,
    MeterReadingCorrectionInputSerializer,
    MeterReadingInputSerializer,
    MeterReadingSerializer,
    MeterSerializer,
    MeterUpdateSerializer,
    PaymentInputSerializer,
    PaymentSerializer,
    PropertyInputSerializer,
    PropertySerializer,
    ReasonSerializer,
    ReceiptSerializer,
    ResidentSerializer,
    ResidentUpdateSerializer,
    TariffInputSerializer,
    TariffSerializer,
    UnitInputSerializer,
    UnitSerializer,
    UnitUpdateSerializer,
    WorkspaceSettingsInputSerializer,
    WorkspaceSettingsSerializer,
)
from apps.properties.services import (
    BillCorrectionService,
    BillingCycleService,
    BillService,
    DomainError,
    LeaseService,
    MeterReadingService,
    MeterService,
    PaymentService,
    PropertyService,
    ResidentService,
    TariffService,
    UnitService,
    WorkspaceSettingsService,
)
from apps.tenants.models import Invitation
from apps.tenants.permissions import IsTenantMember, RequiresCapability, has_capability


def domain_error_response(exc):
    body = {"detail": exc.message, "code": exc.code}
    if exc.field:
        body[exc.field] = [exc.message]
    return Response(body, status=exc.status_code)


class PropertyPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class WorkspaceAPIView(APIView):
    """
    `capabilities` maps an HTTP method to the capability it requires; a method
    mapped to None is a role-aware read whose queryset does the narrowing.
    """

    capabilities = {}
    parser_classes = [JSONParser]

    def get_permissions(self):
        perms = [IsAuthenticated(), IsTenantMember()]
        capability = self.capabilities.get(self.request.method)
        if capability:
            perms.append(RequiresCapability(capability)())
        return perms

    def handle_exception(self, exc):
        if isinstance(exc, DomainError):
            return domain_error_response(exc)
        return super().handle_exception(exc)

    @property
    def today(self):
        return aging.server_today()

    def get_scoped(self, queryset, pk):
        obj = queryset.filter(pk=pk).first()
        if obj is None:
            raise Http404
        return obj

    def resolve(self, model, pk):
        """Resolve a client-supplied id inside the current workspace, or 404."""
        return self.get_scoped(model.objects.for_tenant(self.request.tenant), pk)

    def is_manager(self, capability="billing.manage"):
        return has_capability(self.request.membership, capability)

    def paginate(self, queryset, serializer_class, context=None):
        paginator = PropertyPagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        data = serializer_class(page, many=True, context=context or {}).data
        return paginator.get_paginated_response(data)


def visible_bills(request):
    qs = Bill.objects.for_tenant(request.tenant)
    if has_capability(request.membership, "billing.manage"):
        return qs
    if has_capability(request.membership, "billing.view_own"):
        return qs.filter(resident__user=request.user, published_at__isnull=False)
    return qs.none()


def visible_payments(request):
    qs = Payment.objects.for_tenant(request.tenant)
    if has_capability(request.membership, "payments.manage"):
        return qs
    if has_capability(request.membership, "billing.view_own"):
        return qs.filter(resident__user=request.user)
    return qs.none()


def visible_receipts(request):
    qs = Receipt.objects.for_tenant(request.tenant)
    if has_capability(request.membership, "payments.manage"):
        return qs
    if has_capability(request.membership, "billing.view_own"):
        return qs.filter(bill__resident__user=request.user)
    return qs.none()


BILL_LIST_PREFETCH = Prefetch("line_items", queryset=BillLineItem.objects.only(
    "id", "bill_id", "type", "amount_cents", "quantity", "sort_order", "created_at"
))


# --- workspace settings / overview ------------------------------------------


class WorkspaceSettingsView(WorkspaceAPIView):
    capabilities = {"GET": "workspace.manage", "PATCH": "workspace.manage"}

    def get(self, request):
        return Response(WorkspaceSettingsSerializer(WorkspaceSettingsService.get(request.tenant)).data)

    def patch(self, request):
        serializer = WorkspaceSettingsInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        row = WorkspaceSettingsService.update(
            actor=request.user, tenant=request.tenant, changes=serializer.validated_data
        )
        return Response(WorkspaceSettingsSerializer(row).data)


class WorkspaceOverviewView(WorkspaceAPIView):
    """GET /api/workspace/overview/ — the owner dashboard: portfolio counts, the
    current month's billing summary, overdue count and the onboarding checklist."""

    capabilities = {"GET": "reports.view"}

    def get(self, request):
        tenant = request.tenant
        today = self.today
        bills = Bill.objects.for_tenant(tenant)
        properties = Property.objects.for_tenant(tenant)
        units = Unit.objects.for_tenant(tenant)
        leases = Lease.objects.for_tenant(tenant)
        residents = Resident.objects.for_tenant(tenant).filter(status=Resident.Status.ACTIVE)
        month = reporting.month_start(today)
        steps = [
            {"key": "workspace", "label": "Create workspace", "done": True},
            {"key": "property", "label": "Create a property", "done": properties.exists()},
            {"key": "units", "label": "Add units", "done": units.exists()},
            {
                "key": "residents",
                "label": "Invite residents",
                "done": residents.exists() or Invitation.objects.for_tenant(tenant).exists(),
            },
            {
                "key": "tariff",
                "label": "Configure electricity rate",
                "done": Tariff.objects.for_tenant(tenant).filter(is_active=True).exists(),
            },
            {"key": "leases", "label": "Assign leases", "done": leases.exists()},
        ]
        done = sum(1 for s in steps if s["done"])
        overdue_count = bills.filter(status__in=aging.OPEN_STATUSES, due_date__lt=today).count()
        return Response(
            {
                "properties": properties.filter(is_active=True).count(),
                **reporting.occupancy(units, leases),
                "residents": residents.count(),
                "current_month": reporting.period_summary(bills, month, today, residents.count()),
                "overdue_bills": overdue_count,
                "open_cycle": BillingCycleSerializer(
                    BillingCycle.objects.for_tenant(tenant).filter(status=BillingCycle.Status.OPEN).first()
                ).data
                if BillingCycle.objects.for_tenant(tenant).filter(status=BillingCycle.Status.OPEN).exists()
                else None,
                "onboarding": {
                    "steps": steps,
                    "completed": done,
                    "total": len(steps),
                    "percent": round(done * 100 / len(steps)),
                    "ready_to_bill": all(s["done"] for s in steps),
                },
            }
        )


class ResidencyView(WorkspaceAPIView):
    """GET /api/residency/ — the caller's OWN resident profile, active lease,
    unit and property in this workspace (or `resident: null`)."""

    def get(self, request):
        resident = (
            Resident.objects.for_tenant(request.tenant)
            .filter(user=request.user)
            .prefetch_related("leases__unit__property")
            .first()
        )
        if resident is None:
            return Response({"resident": None, "lease": None})
        lease = next((l for l in resident.leases.all() if l.status == Lease.Status.ACTIVE), None)
        bills = visible_bills(request).prefetch_related(BILL_LIST_PREFETCH).order_by("-period_start")
        latest = bills.first()
        open_bills = list(bills.filter(status__in=aging.OPEN_STATUSES))
        return Response(
            {
                "resident": ResidentSerializer(resident).data,
                "lease": LeaseSerializer(lease).data if lease else None,
                "latest_bill": BillSerializer(latest, context={"today": self.today}).data if latest else None,
                "outstanding_cents": sum(b.total_cents - b.amount_paid_cents for b in open_bills),
                "overdue_bills": sum(1 for b in open_bills if aging.overdue_days(b, self.today) > 0),
            }
        )


# --- properties & units -----------------------------------------------------


class PropertyListView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "POST": "property.manage"}

    def get(self, request):
        qs = (
            Property.objects.for_tenant(request.tenant)
            .annotate(
                unit_count=Count("units", distinct=True),
                occupied_count=Count(
                    "units", filter=Q(units__leases__status=Lease.Status.ACTIVE), distinct=True
                ),
            )
            .order_by("name")
        )
        return Response(PropertySerializer(qs, many=True).data)

    def post(self, request):
        serializer = PropertyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prop = PropertyService.create(actor=request.user, tenant=request.tenant, **serializer.validated_data)
        return Response(PropertySerializer(prop).data, status=status.HTTP_201_CREATED)


class PropertyDetailView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "PATCH": "property.manage"}

    def get(self, request, pk):
        prop = self.resolve(Property, pk)
        units = Unit.objects.for_tenant(request.tenant).filter(property=prop).order_by("identifier")
        return Response({**PropertySerializer(prop).data, "units": UnitSerializer(units, many=True).data})

    def patch(self, request, pk):
        prop = self.resolve(Property, pk)
        serializer = PropertyInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        prop = PropertyService.update(actor=request.user, prop=prop, changes=serializer.validated_data)
        return Response(PropertySerializer(prop).data)


class UnitListView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "POST": "property.manage"}

    def get(self, request):
        qs = Unit.objects.for_tenant(request.tenant).select_related("property").order_by(
            "property__name", "identifier"
        )
        prop = request.query_params.get("property")
        if prop:
            qs = qs.filter(property_id=prop) if _is_uuid(prop) else qs.none()
        return Response(UnitSerializer(qs, many=True).data)

    def post(self, request):
        serializer = UnitInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        prop = self.resolve(Property, data["property_id"])
        unit = UnitService.create(
            actor=request.user,
            tenant=request.tenant,
            prop=prop,
            identifier=data["identifier"],
            floor=data["floor"],
            unit_type=data["unit_type"],
        )
        return Response(UnitSerializer(unit).data, status=status.HTTP_201_CREATED)


class UnitDetailView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "PATCH": "property.manage"}

    def get(self, request, pk):
        unit = self.get_scoped(Unit.objects.for_tenant(request.tenant).select_related("property"), pk)
        leases = Lease.objects.for_tenant(request.tenant).filter(unit=unit).select_related(
            "resident", "unit__property"
        ).order_by("-start_date")
        meters = Meter.objects.for_tenant(request.tenant).filter(unit=unit).select_related("unit__property")
        bills = (
            Bill.objects.for_tenant(request.tenant)
            .filter(unit=unit)
            .prefetch_related(BILL_LIST_PREFETCH)
            .order_by("-period_start")[:24]
        )
        return Response(
            {
                **UnitSerializer(unit).data,
                "leases": LeaseSerializer(leases, many=True).data,
                "meters": MeterSerializer(meters, many=True).data,
                "bills": BillSerializer(bills, many=True, context={"today": self.today}).data,
            }
        )

    def patch(self, request, pk):
        unit = self.resolve(Unit, pk)
        serializer = UnitUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        unit = UnitService.update(actor=request.user, unit=unit, changes=serializer.validated_data)
        return Response(UnitSerializer(unit).data)


def _is_uuid(value):
    from apps.platform.utils import parse_uuid_or_none

    return parse_uuid_or_none(value) is not None


# --- residents & leases -------------------------------------------------------


class ResidentListView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage"}

    def get(self, request):
        qs = (
            Resident.objects.for_tenant(request.tenant)
            .select_related("user")
            .prefetch_related(
                Prefetch(
                    "leases",
                    queryset=Lease.objects.filter(status=Lease.Status.ACTIVE).select_related("unit__property", "resident"),
                    to_attr="active_leases",
                )
            )
            .order_by("display_name")
        )
        status_param = request.query_params.get("status")
        if status_param in (Resident.Status.ACTIVE, Resident.Status.INACTIVE):
            qs = qs.filter(status=status_param)
        return Response(ResidentSerializer(qs, many=True).data)


class ResidentDetailView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "PATCH": "property.manage"}

    def get(self, request, pk):
        resident = self.get_scoped(Resident.objects.for_tenant(request.tenant).select_related("user"), pk)
        leases = Lease.objects.for_tenant(request.tenant).filter(resident=resident).select_related(
            "unit__property", "resident"
        ).order_by("-start_date")
        bills = (
            Bill.objects.for_tenant(request.tenant)
            .filter(resident=resident)
            .prefetch_related(BILL_LIST_PREFETCH)
            .order_by("-period_start")
        )
        payments = Payment.objects.for_tenant(request.tenant).filter(resident=resident).select_related(
            "bill", "receipt"
        ).order_by("-payment_date")
        today = self.today
        open_bills = [b for b in bills if aging.is_open(b)]
        return Response(
            {
                **ResidentSerializer(resident).data,
                "leases": LeaseSerializer(leases, many=True).data,
                "bills": BillSerializer(bills, many=True, context={"today": today}).data,
                "payments": PaymentSerializer(payments, many=True).data,
                "outstanding_cents": sum(b.total_cents - b.amount_paid_cents for b in open_bills),
                "overdue_cents": sum(
                    b.total_cents - b.amount_paid_cents for b in open_bills if aging.overdue_days(b, today) > 0
                ),
            }
        )

    def patch(self, request, pk):
        resident = self.resolve(Resident, pk)
        serializer = ResidentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resident = ResidentService.update(actor=request.user, resident=resident, changes=serializer.validated_data)
        return Response(ResidentSerializer(resident).data)


class LeaseListView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "POST": "property.manage"}

    def get(self, request):
        qs = Lease.objects.for_tenant(request.tenant).select_related("unit__property", "resident").order_by(
            "-start_date"
        )
        status_param = request.query_params.get("status")
        if status_param in Lease.Status.values:
            qs = qs.filter(status=status_param)
        return Response(LeaseSerializer(qs, many=True).data)

    def post(self, request):
        serializer = LeaseInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        unit = self.resolve(Unit, data["unit_id"])
        resident = self.resolve(Resident, data["resident_id"])
        lease = LeaseService.create(
            actor=request.user,
            tenant=request.tenant,
            unit=unit,
            resident=resident,
            start_date=data["start_date"],
            end_date=data["end_date"],
            monthly_rent_cents=data["monthly_rent_cents"],
            security_deposit_cents=data["security_deposit_cents"],
        )
        return Response(LeaseSerializer(lease).data, status=status.HTTP_201_CREATED)


class LeaseDetailView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "PATCH": "property.manage"}

    def get(self, request, pk):
        lease = self.get_scoped(
            Lease.objects.for_tenant(request.tenant).select_related("unit__property", "resident"), pk
        )
        return Response(LeaseSerializer(lease).data)

    def patch(self, request, pk):
        lease = self.resolve(Lease, pk)
        serializer = LeaseUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lease = LeaseService.update(actor=request.user, lease=lease, changes=serializer.validated_data)
        return Response(LeaseSerializer(lease).data)


class LeaseEndView(WorkspaceAPIView):
    capabilities = {"POST": "property.manage"}

    def post(self, request, pk):
        lease = self.resolve(Lease, pk)
        serializer = LeaseEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lease = LeaseService.end(actor=request.user, lease=lease, end_date=serializer.validated_data["end_date"])
        return Response(LeaseSerializer(lease).data)


# --- meters, readings, tariffs ----------------------------------------------


class MeterListView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "POST": "property.manage"}

    def get(self, request):
        qs = Meter.objects.for_tenant(request.tenant).select_related("unit__property").order_by("meter_number")
        unit = request.query_params.get("unit")
        if unit:
            qs = qs.filter(unit_id=unit) if _is_uuid(unit) else qs.none()
        return Response(MeterSerializer(qs, many=True).data)

    def post(self, request):
        serializer = MeterInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        unit = self.resolve(Unit, data["unit_id"])
        meter = MeterService.create(
            actor=request.user,
            tenant=request.tenant,
            unit=unit,
            meter_number=data["meter_number"].strip(),
            unit_of_measure=data["unit_of_measure"],
            multiplier=data["multiplier"],
            installed_at=data["installed_at"],
        )
        return Response(MeterSerializer(meter).data, status=status.HTTP_201_CREATED)


class MeterDetailView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "PATCH": "property.manage"}

    def get(self, request, pk):
        meter = self.get_scoped(Meter.objects.for_tenant(request.tenant).select_related("unit__property"), pk)
        readings = MeterReading.objects.for_tenant(request.tenant).filter(meter=meter).prefetch_related(
            "corrections__actor"
        ).select_related("meter__unit").order_by("-reading_date")
        return Response(
            {**MeterSerializer(meter).data, "readings": MeterReadingSerializer(readings, many=True).data}
        )

    def patch(self, request, pk):
        meter = self.resolve(Meter, pk)
        serializer = MeterUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meter = MeterService.update(actor=request.user, meter=meter, changes=serializer.validated_data)
        return Response(MeterSerializer(meter).data)


class MeterReadingListView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage", "POST": "property.manage"}
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        qs = (
            MeterReading.objects.for_tenant(request.tenant)
            .select_related("meter__unit")
            .prefetch_related("corrections__actor")
            .order_by("-reading_date", "meter__meter_number")
        )
        meter = request.query_params.get("meter")
        if meter:
            qs = qs.filter(meter_id=meter) if _is_uuid(meter) else qs.none()
        period = request.query_params.get("period")
        if period:
            start, end = reporting.period_from_param(period, self.today)
            qs = qs.filter(reading_date__gte=start, reading_date__lte=end)
        return self.paginate(qs, MeterReadingSerializer)

    def post(self, request):
        serializer = MeterReadingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        meter = self.resolve(Meter, data["meter_id"])
        reading = MeterReadingService.record(
            actor=request.user,
            tenant=request.tenant,
            meter=meter,
            reading_date=data["reading_date"],
            reading_value=data["reading_value"],
            notes=data["notes"],
            proof=data["proof"],
        )
        return Response(MeterReadingSerializer(reading).data, status=status.HTTP_201_CREATED)


class MeterReadingDetailView(WorkspaceAPIView):
    capabilities = {"GET": "property.manage"}

    def get(self, request, pk):
        reading = self.get_scoped(
            MeterReading.objects.for_tenant(request.tenant).select_related("meter__unit"), pk
        )
        return Response(MeterReadingSerializer(reading).data)


class MeterReadingCorrectView(WorkspaceAPIView):
    capabilities = {"POST": "property.manage"}

    def post(self, request, pk):
        reading = self.resolve(MeterReading, pk)
        serializer = MeterReadingCorrectionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        correction, affected = MeterReadingService.correct(
            actor=request.user,
            reading=reading,
            corrected_value=serializer.validated_data["corrected_value"],
            reason=serializer.validated_data["reason"],
        )
        reading.refresh_from_db()
        return Response(
            {
                "reading": MeterReadingSerializer(reading).data,
                # Issued bills keep the reading they were calculated from; the
                # owner decides whether each needs a bill correction.
                "affected_bills": [
                    {"id": str(b.id), "bill_number": b.bill_number, "status": b.status} for b in affected
                ],
            }
        )


class MeterReadingProofView(WorkspaceAPIView):
    """GET /api/meter-readings/<id>/proof/ — the evidence image, streamed through
    authorization (never a public media URL). An owner may view any reading's
    proof in the workspace; a resident only a reading that one of their own
    published bills was calculated from."""

    def get(self, request, pk):
        readings = MeterReading.objects.for_tenant(request.tenant)
        if not self.is_manager("property.manage"):
            bill_ids = visible_bills(request).values("id")
            line_filter = BillLineItem.objects.filter(bill_id__in=bill_ids)
            readings = readings.filter(
                Q(pk__in=line_filter.values("opening_reading_id"))
                | Q(pk__in=line_filter.values("closing_reading_id"))
            )
        reading = self.get_scoped(readings, pk)
        if not reading.proof:
            raise Http404
        response = FileResponse(reading.proof.open("rb"), content_type=reading.proof_content_type or "application/octet-stream")
        response["Content-Disposition"] = "inline"
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class TariffListView(WorkspaceAPIView):
    capabilities = {"GET": "billing.manage", "POST": "billing.manage"}

    def get(self, request):
        qs = Tariff.objects.for_tenant(request.tenant).order_by("-effective_from")
        current = TariffService.applicable(request.tenant, self.today)
        return Response(
            {
                "current": TariffSerializer(current).data if current else None,
                "results": TariffSerializer(qs, many=True).data,
            }
        )

    def post(self, request):
        serializer = TariffInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tariff = TariffService.create(
            actor=request.user,
            tenant=request.tenant,
            rate_per_unit_cents=serializer.validated_data["rate_per_unit_cents"],
            effective_from=serializer.validated_data["effective_from"],
        )
        return Response(TariffSerializer(tariff).data, status=status.HTTP_201_CREATED)


# --- billing cycles, summary, aging, reports ---------------------------------


class BillingCycleListView(WorkspaceAPIView):
    capabilities = {"GET": "billing.manage", "POST": "billing.manage"}

    def get(self, request):
        cycles = BillingCycle.objects.for_tenant(request.tenant).order_by("-period_start")
        return Response(BillingCycleSerializer(cycles, many=True).data)

    def post(self, request):
        serializer = CycleOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year, month = (int(p) for p in serializer.validated_data["period"].split("-"))
        cycle, created = BillingCycleService.open(actor=request.user, tenant=request.tenant, year=year, month=month)
        return Response(
            BillingCycleSerializer(cycle).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BillingCycleDetailView(WorkspaceAPIView):
    capabilities = {"GET": "billing.manage"}

    def get(self, request, pk):
        cycle = self.resolve(BillingCycle, pk)
        return Response({**BillingCycleSerializer(cycle).data, "progress": BillingCycleService.progress(cycle)})


class BillingCycleGenerateView(WorkspaceAPIView):
    capabilities = {"POST": "billing.manage"}

    def post(self, request, pk):
        cycle = self.resolve(BillingCycle, pk)
        serializer = CycleGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created, skipped = BillingCycleService.generate(
            actor=request.user, cycle=cycle, regenerate_drafts=serializer.validated_data["regenerate_drafts"]
        )
        return Response(
            {
                "created": len(created),
                "skipped": skipped,
                "progress": BillingCycleService.progress(cycle),
            }
        )


class BillingCyclePublishView(WorkspaceAPIView):
    capabilities = {"POST": "billing.manage"}

    def post(self, request, pk):
        cycle = self.resolve(BillingCycle, pk)
        published = BillingCycleService.publish_all(actor=request.user, cycle=cycle)
        return Response({"published": len(published), "progress": BillingCycleService.progress(cycle)})


class BillingCycleCloseView(WorkspaceAPIView):
    capabilities = {"POST": "billing.manage"}

    def post(self, request, pk):
        cycle = self.resolve(BillingCycle, pk)
        cycle = BillingCycleService.close(actor=request.user, cycle=cycle)
        return Response(BillingCycleSerializer(cycle).data)


class BillingSummaryView(WorkspaceAPIView):
    capabilities = {"GET": "reports.view"}

    def get(self, request):
        today = self.today
        start, _ = reporting.period_from_param(request.query_params.get("period"), today)
        residents = Resident.objects.for_tenant(request.tenant).filter(status=Resident.Status.ACTIVE).count()
        return Response(
            reporting.period_summary(Bill.objects.for_tenant(request.tenant), start, today, residents)
        )


def aging_payload(report):
    return {
        "total_outstanding_cents": report["total_outstanding_cents"],
        "total_overdue_cents": report["total_overdue_cents"],
        "buckets": report["buckets"],
        "rows": [
            {
                "bill_id": str(bill.id),
                "tenant_id": str(bill.tenant_id),
                "bill_number": bill.bill_number,
                "resident_id": str(bill.resident_id),
                "resident_name": bill.resident_name,
                "unit_identifier": bill.unit_identifier,
                "property_name": bill.property_name,
                "period_start": bill.period_start,
                "due_date": bill.due_date,
                "amount_due_cents": due,
                "currency": bill.currency,
                "overdue_days": days,
                "bucket": bucket,
                "status": bill.status,
            }
            for bill, days, bucket, due in report["rows"]
        ],
    }


class BillingAgingView(WorkspaceAPIView):
    capabilities = {"GET": "reports.view"}

    def get(self, request):
        qs = filter_bills(Bill.objects.for_tenant(request.tenant), request.query_params, self.today)
        return Response(aging_payload(reporting.aging_summary(qs, self.today)))


class BillingReportView(WorkspaceAPIView):
    capabilities = {"GET": "reports.view"}

    def get(self, request):
        today = self.today
        try:
            months = min(max(int(request.query_params.get("months", 12)), 1), 36)
        except ValueError:
            months = 12
        start, _ = reporting.period_from_param(request.query_params.get("period"), today)
        bills = Bill.objects.for_tenant(request.tenant)
        return Response(
            {
                "monthly": reporting.monthly_series(bills, Payment.objects.for_tenant(request.tenant), today, months),
                "electricity_by_unit": reporting.electricity_by_unit(bills, start),
                "period": start.strftime("%Y-%m"),
            }
        )


class BillingRemindersRunView(WorkspaceAPIView):
    capabilities = {"POST": "billing.manage"}

    def post(self, request):
        result = send_billing_reminders(tenant=request.tenant, today=self.today)
        return Response(result.as_dict())


# --- bills ----------------------------------------------------------------------


class BillListView(WorkspaceAPIView):
    def get(self, request):
        qs = filter_bills(visible_bills(request), request.query_params, self.today)
        if not self.is_manager():
            qs = qs.exclude(status=Bill.Status.DRAFT)
        qs = qs.prefetch_related(BILL_LIST_PREFETCH).order_by("-period_start", "property_name", "unit_identifier")
        return self.paginate(qs, BillSerializer, {"today": self.today})


class BillDetailView(WorkspaceAPIView):
    def get(self, request, pk):
        bill = self.get_scoped(
            visible_bills(request).prefetch_related(
                Prefetch(
                    "line_items",
                    queryset=BillLineItem.objects.select_related("opening_reading", "closing_reading"),
                ),
                Prefetch("payments", queryset=Payment.objects.select_related("receipt", "bill").order_by("payment_date")),
                "corrections__actor",
            ),
            pk,
        )
        return Response(BillDetailSerializer(bill, context={"today": self.today}).data)


class BillLineItemListView(WorkspaceAPIView):
    capabilities = {"POST": "billing.manage"}

    def post(self, request, pk):
        bill = self.resolve(Bill, pk)
        serializer = LineItemInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        line = BillService.add_line_item(
            actor=request.user,
            bill=bill,
            type=data["type"],
            description=data["description"],
            amount_cents=data["amount_cents"],
        )
        return Response(LineItemSerializer(line).data, status=status.HTTP_201_CREATED)


class BillLineItemDetailView(WorkspaceAPIView):
    capabilities = {"DELETE": "billing.manage"}

    def delete(self, request, pk, line_id):
        bill = self.resolve(Bill, pk)
        BillService.remove_line_item(actor=request.user, bill=bill, line_item_id=line_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BillPublishView(WorkspaceAPIView):
    capabilities = {"POST": "billing.manage"}

    def post(self, request, pk):
        bill = BillService.publish(actor=request.user, bill=self.resolve(Bill, pk))
        return Response(BillSerializer(bill, context={"today": self.today}).data)


class BillCancelView(WorkspaceAPIView):
    capabilities = {"POST": "billing.manage"}

    def post(self, request, pk):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bill = BillService.cancel(
            actor=request.user, bill=self.resolve(Bill, pk), reason=serializer.validated_data["reason"]
        )
        return Response(BillSerializer(bill, context={"today": self.today}).data)


class BillCorrectionView(WorkspaceAPIView):
    capabilities = {"POST": "billing.manage"}

    def post(self, request, pk):
        bill = self.resolve(Bill, pk)
        serializer = BillCorrectionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["kind"] == "AMOUNT_ADJUSTMENT":
            correction = BillCorrectionService.adjust_amount(
                actor=request.user,
                bill=bill,
                amount_delta_cents=data["amount_cents"],
                reason=data["reason"],
                description=data["description"],
            )
        else:
            correction = BillCorrectionService.correct_reading(
                actor=request.user,
                bill=bill,
                line_item_id=data["line_item_id"],
                corrected_closing_value=data["corrected_closing_value"],
                reason=data["reason"],
            )
        return Response(BillCorrectionSerializer(correction).data, status=status.HTTP_201_CREATED)


# --- payments & receipts ----------------------------------------------------------


class PaymentListView(WorkspaceAPIView):
    capabilities = {"POST": "payments.manage"}

    def get(self, request):
        qs = filter_payments(visible_payments(request), request.query_params)
        qs = qs.select_related("bill", "receipt").order_by("-payment_date", "-created_at")
        return self.paginate(qs, PaymentSerializer)

    def post(self, request):
        serializer = PaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        bill = self.resolve(Bill, data["bill_id"])
        payment, created = PaymentService.record(
            actor=request.user,
            tenant=request.tenant,
            bill=bill,
            amount_cents=data["amount_cents"],
            payment_date=data["payment_date"],
            method=data["method"],
            reference=data["reference"].strip(),
            notes=data["notes"],
            idempotency_key=data["idempotency_key"],
        )
        payment = Payment.objects.select_related("bill", "receipt").get(pk=payment.pk)
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PaymentDetailView(WorkspaceAPIView):
    def get(self, request, pk):
        payment = self.get_scoped(visible_payments(request).select_related("bill", "receipt"), pk)
        return Response(PaymentSerializer(payment).data)


class PaymentVoidView(WorkspaceAPIView):
    capabilities = {"POST": "payments.manage"}

    def post(self, request, pk):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = PaymentService.void(
            actor=request.user, payment=self.resolve(Payment, pk), reason=serializer.validated_data["reason"]
        )
        payment = Payment.objects.select_related("bill", "receipt").get(pk=payment.pk)
        return Response(PaymentSerializer(payment).data)


class ReceiptListView(WorkspaceAPIView):
    def get(self, request):
        qs = filter_receipts(visible_receipts(request), request.query_params)
        qs = qs.select_related("payment", "bill").order_by("-issued_at")
        return self.paginate(qs, ReceiptSerializer)


class ReceiptDetailView(WorkspaceAPIView):
    def get(self, request, pk):
        receipt = self.get_scoped(visible_receipts(request).select_related("payment", "bill"), pk)
        settings_row = WorkspaceSettingsService.get(request.tenant)
        return Response(
            {
                **ReceiptSerializer(receipt).data,
                "issuer": {
                    "name": settings_row.display_name or request.tenant.name,
                    "contact_email": settings_row.contact_email,
                    "contact_phone": settings_row.contact_phone,
                    "address": settings_row.address,
                    "footer": settings_row.receipt_footer,
                },
            }
        )

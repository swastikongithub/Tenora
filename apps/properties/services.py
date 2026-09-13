"""
Property billing services — every mutation in the property domain goes through
this module (CLAUDE.md: "All mutations go through services"). Views validate
input shape and translate `DomainError` into a response; they never compute a
charge, change a status, or write a row themselves.

Concurrency, by operation:

    bill generation   partial UNIQUE(unit, resident, period_start) — a second
                      concurrent generation collides and is reported skipped
    publish / cancel  select_for_update on the bill; repeated publish is a no-op
    payment           select_for_update on the bill + amount <= due check +
                      UNIQUE(tenant, idempotency_key) / (tenant, reference)
    receipt number    select_for_update on the workspace sequence row
    lease             select_for_update on the unit + partial UNIQUE(one ACTIVE)
    meter reading     select_for_update on the meter + UNIQUE(meter, date)
    tariff            select_for_update on the workspace (Tenant) row

Audit: financially meaningful actions write an AuditEvent through the existing
`AuditService.record_critical`, inside the same transaction as the change.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.platform.services import AuditService
from apps.properties import calculations
from apps.properties.aging import server_today
from apps.properties.models import (
    Bill,
    BillCorrection,
    BillingCycle,
    BillLineItem,
    Lease,
    Meter,
    MeterReading,
    MeterReadingCorrection,
    Payment,
    Property,
    Receipt,
    Resident,
    Tariff,
    Unit,
    WorkspaceSequence,
    WorkspaceSettings,
)
from apps.tenants.models import Membership, Tenant


class DomainError(Exception):
    """A business rule refused the operation. `code` is stable for clients and
    tests; `message` is safe to show; `field` keys a form error when set."""

    def __init__(self, code, message, *, field=None, status_code=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.status_code = status_code


def _audit(*, actor, tenant, action, target_type, target_id, summary, metadata=None):
    AuditService.record_critical(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary[:255],
        metadata={"tenant_id": str(tenant.id if hasattr(tenant, "id") else tenant), **(metadata or {})},
    )


def _month_label(d):
    return d.strftime("%B %Y")


def _owners(tenant, exclude=None):
    qs = Membership.objects.for_tenant(tenant).filter(
        role=Membership.Role.OWNER, status=Membership.Status.ACTIVE
    ).select_related("user")
    return [m.user for m in qs if exclude is None or m.user_id != exclude.id]


def _require(value, code, message, field=None):
    if not value:
        raise DomainError(code, message, field=field)


# --------------------------------------------------------------------------
# Numbering, settings
# --------------------------------------------------------------------------


class SequenceService:
    @staticmethod
    def next_value(tenant, name):
        """Allocate the next number for (workspace, name). Must run inside the
        caller's transaction; the row lock serialises concurrent allocations."""
        WorkspaceSequence.objects.get_or_create(tenant=tenant, name=name)
        seq = WorkspaceSequence.objects.select_for_update().get(tenant=tenant, name=name)
        value = seq.next_value
        seq.next_value = value + 1
        seq.save(update_fields=["next_value"])
        return value


class WorkspaceSettingsService:
    FIELDS = (
        "display_name",
        "contact_email",
        "contact_phone",
        "address",
        "receipt_footer",
        "currency",
        "due_days_after_period_end",
        "default_maintenance_cents",
    )
    BILLING_FIELDS = frozenset(
        {"currency", "due_days_after_period_end", "default_maintenance_cents"}
    )

    @staticmethod
    def get(tenant):
        settings_row, _ = WorkspaceSettings.objects.get_or_create(
            tenant=tenant, defaults={"display_name": tenant.name}
        )
        return settings_row

    @staticmethod
    def update(*, actor, tenant, changes):
        with transaction.atomic():
            WorkspaceSettingsService.get(tenant)
            row = WorkspaceSettings.objects.for_tenant(tenant).select_for_update().get()
            before, after = {}, {}
            for field in WorkspaceSettingsService.FIELDS:
                if field in changes and getattr(row, field) != changes[field]:
                    before[field] = getattr(row, field)
                    after[field] = changes[field]
            if "currency" in after and Bill.objects.for_tenant(tenant).exclude(
                status=Bill.Status.CANCELLED
            ).exists():
                raise DomainError(
                    "CURRENCY_LOCKED",
                    "The billing currency cannot change once bills exist in this workspace.",
                    field="currency",
                )
            if not after:
                return row
            for field, value in after.items():
                setattr(row, field, value)
            row.save()
            _audit(
                actor=actor,
                tenant=tenant,
                action="workspace_settings.updated",
                target_type="WorkspaceSettings",
                target_id=row.id,
                summary="Updated workspace settings"
                + (" (billing defaults — future bills only)" if WorkspaceSettingsService.BILLING_FIELDS & after.keys() else ""),
                metadata={"before": {k: str(v) for k, v in before.items()}, "after": {k: str(v) for k, v in after.items()}},
            )
        return row


# --------------------------------------------------------------------------
# Properties, units, residents, leases
# --------------------------------------------------------------------------


class PropertyService:
    FIELDS = (
        "name",
        "code",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "postal_code",
        "country",
        "is_active",
    )

    @staticmethod
    def create(*, actor, tenant, **fields):
        with transaction.atomic():
            prop = Property.objects.create(
                tenant=tenant, **{k: v for k, v in fields.items() if k in PropertyService.FIELDS}
            )
            _audit(
                actor=actor,
                tenant=tenant,
                action="property.created",
                target_type="Property",
                target_id=prop.id,
                summary=f"Created property {prop.name}",
            )
        return prop

    @staticmethod
    def update(*, actor, prop, changes):
        with transaction.atomic():
            prop = Property.objects.select_for_update().get(pk=prop.pk)
            if changes.get("is_active") is False and Lease.objects.for_tenant(prop.tenant).filter(
                unit__property=prop, status=Lease.Status.ACTIVE
            ).exists():
                raise DomainError(
                    "PROPERTY_HAS_ACTIVE_LEASES",
                    "End the active leases in this property before deactivating it.",
                    field="is_active",
                )
            for field in PropertyService.FIELDS:
                if field in changes:
                    setattr(prop, field, changes[field])
            prop.save()
            _audit(
                actor=actor,
                tenant=prop.tenant,
                action="property.updated",
                target_type="Property",
                target_id=prop.id,
                summary=f"Updated property {prop.name}",
                metadata={"fields": sorted(changes)},
            )
        return prop


class UnitService:
    MANUAL_STATUSES = frozenset({"VACANT", "MAINTENANCE", "INACTIVE"})

    @staticmethod
    def create(*, actor, tenant, prop, identifier, floor="", unit_type=""):
        if prop.tenant_id != tenant.id:
            raise DomainError("NOT_FOUND", "Property not found.", status_code=404)
        if not prop.is_active:
            raise DomainError("PROPERTY_INACTIVE", "This property is inactive.", field="property_id")
        try:
            with transaction.atomic():
                unit = Unit.objects.create(
                    tenant=tenant,
                    property=prop,
                    identifier=identifier,
                    floor=floor,
                    unit_type=unit_type,
                )
                _audit(
                    actor=actor,
                    tenant=tenant,
                    action="unit.created",
                    target_type="Unit",
                    target_id=unit.id,
                    summary=f"Created unit {identifier} in {prop.name}",
                )
        except IntegrityError:
            raise DomainError(
                "DUPLICATE_UNIT",
                "A unit with this identifier already exists in this property.",
                field="identifier",
            )
        return unit

    @staticmethod
    def update(*, actor, unit, changes):
        try:
            with transaction.atomic():
                unit = Unit.objects.select_for_update().get(pk=unit.pk)
                new_status = changes.get("status")
                if new_status is not None and new_status != unit.status:
                    if new_status not in UnitService.MANUAL_STATUSES:
                        raise DomainError(
                            "INVALID_UNIT_STATUS",
                            "Occupancy is set by creating a lease.",
                            field="status",
                        )
                    if Lease.objects.for_tenant(unit.tenant).filter(
                        unit=unit, status=Lease.Status.ACTIVE
                    ).exists():
                        raise DomainError(
                            "UNIT_HAS_ACTIVE_LEASE",
                            "End the active lease before changing this unit's status.",
                            field="status",
                        )
                for field in ("identifier", "floor", "unit_type", "status"):
                    if field in changes:
                        setattr(unit, field, changes[field])
                unit.save()
                _audit(
                    actor=actor,
                    tenant=unit.tenant,
                    action="unit.updated",
                    target_type="Unit",
                    target_id=unit.id,
                    summary=f"Updated unit {unit.identifier}",
                    metadata={"fields": sorted(changes)},
                )
        except IntegrityError:
            raise DomainError(
                "DUPLICATE_UNIT",
                "A unit with this identifier already exists in this property.",
                field="identifier",
            )
        return unit


class ResidentService:
    @staticmethod
    def update(*, actor, resident, changes):
        with transaction.atomic():
            resident = Resident.objects.select_for_update().get(pk=resident.pk)
            for field in ("display_name", "phone", "reference"):
                if field in changes:
                    setattr(resident, field, changes[field])
            resident.save()
            _audit(
                actor=actor,
                tenant=resident.tenant,
                action="resident.updated",
                target_type="Resident",
                target_id=resident.id,
                summary=f"Updated resident {resident.display_name}",
                metadata={"fields": sorted(changes)},
            )
        return resident


class LeaseService:
    @staticmethod
    def create(
        *,
        actor,
        tenant,
        unit,
        resident,
        start_date,
        monthly_rent_cents,
        end_date=None,
        security_deposit_cents=None,
    ):
        if unit.tenant_id != tenant.id or resident.tenant_id != tenant.id:
            raise DomainError("NOT_FOUND", "Unit or resident not found.", status_code=404)
        if resident.status != Resident.Status.ACTIVE:
            raise DomainError(
                "RESIDENT_INACTIVE",
                "Only an active resident can be given a lease.",
                field="resident_id",
            )
        if end_date is not None and end_date < start_date:
            raise DomainError(
                "LEASE_DATES_INVALID", "The end date must be on or after the start date.", field="end_date"
            )
        today = server_today()
        status = (
            Lease.Status.ENDED if end_date is not None and end_date < today else Lease.Status.ACTIVE
        )
        try:
            with transaction.atomic():
                unit = Unit.objects.select_for_update().get(pk=unit.pk)
                if unit.status == Unit.Status.INACTIVE:
                    raise DomainError("UNIT_INACTIVE", "This unit is inactive.", field="unit_id")
                far_future = date.max
                overlapping = (
                    Lease.objects.for_tenant(tenant)
                    .filter(unit=unit)
                    .exclude(status__in=[Lease.Status.CANCELLED, Lease.Status.DRAFT])
                    .filter(start_date__lte=end_date or far_future)
                    .filter(Q(end_date__isnull=True) | Q(end_date__gte=start_date))
                )
                if overlapping.exists():
                    raise DomainError(
                        "LEASE_OVERLAP",
                        "This unit already has a lease covering these dates.",
                        field="start_date",
                    )
                lease = Lease.objects.create(
                    tenant=tenant,
                    unit=unit,
                    resident=resident,
                    start_date=start_date,
                    end_date=end_date,
                    monthly_rent_cents=monthly_rent_cents,
                    security_deposit_cents=security_deposit_cents,
                    status=status,
                )
                if status == Lease.Status.ACTIVE:
                    unit.status = Unit.Status.OCCUPIED
                    unit.save(update_fields=["status", "updated_at"])
                _audit(
                    actor=actor,
                    tenant=tenant,
                    action="lease.created",
                    target_type="Lease",
                    target_id=lease.id,
                    summary=f"Lease for {resident.display_name} in unit {unit.identifier}",
                    metadata={
                        "monthly_rent_cents": monthly_rent_cents,
                        "start_date": str(start_date),
                        "end_date": str(end_date) if end_date else None,
                    },
                )
        except IntegrityError:
            raise DomainError(
                "LEASE_OVERLAP",
                "This unit already has an active lease.",
                field="start_date",
            )
        return lease

    @staticmethod
    def update(*, actor, lease, changes):
        with transaction.atomic():
            lease = Lease.objects.select_for_update().get(pk=lease.pk)
            if lease.status not in (Lease.Status.ACTIVE, Lease.Status.DRAFT):
                raise DomainError("LEASE_NOT_ACTIVE", "Only an active lease can be changed.")
            before = {}
            for field in ("monthly_rent_cents", "security_deposit_cents"):
                if field in changes and getattr(lease, field) != changes[field]:
                    before[field] = getattr(lease, field)
                    setattr(lease, field, changes[field])
            if not before:
                return lease
            lease.save()
            _audit(
                actor=actor,
                tenant=lease.tenant,
                action="lease.rent_changed" if "monthly_rent_cents" in before else "lease.updated",
                target_type="Lease",
                target_id=lease.id,
                summary="Changed lease terms (applies to bills generated from now on)",
                metadata={
                    "before": before,
                    "after": {k: getattr(lease, k) for k in before},
                },
            )
        return lease

    @staticmethod
    def end(*, actor, lease, end_date):
        with transaction.atomic():
            lease = Lease.objects.select_for_update(of=("self",)).select_related("unit").get(pk=lease.pk)
            if lease.status != Lease.Status.ACTIVE:
                raise DomainError("LEASE_NOT_ACTIVE", "Only an active lease can be ended.")
            if end_date < lease.start_date:
                raise DomainError(
                    "LEASE_DATES_INVALID",
                    "The end date must be on or after the start date.",
                    field="end_date",
                )
            lease.end_date = end_date
            lease.status = Lease.Status.ENDED
            lease.save(update_fields=["end_date", "status", "updated_at"])
            unit = Unit.objects.select_for_update().get(pk=lease.unit_id)
            if unit.status == Unit.Status.OCCUPIED:
                unit.status = Unit.Status.VACANT
                unit.save(update_fields=["status", "updated_at"])
            _audit(
                actor=actor,
                tenant=lease.tenant,
                action="lease.ended",
                target_type="Lease",
                target_id=lease.id,
                summary=f"Ended lease on {end_date}",
            )
        return lease


# --------------------------------------------------------------------------
# Meters, readings, tariffs
# --------------------------------------------------------------------------

PROOF_MAX_BYTES = 5 * 1024 * 1024
# Content type is decided from the file's own leading bytes, never from the
# client-supplied header or filename.
PROOF_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"%PDF-", "application/pdf", "pdf"),
)


def sniff_proof(upload):
    if upload.size > PROOF_MAX_BYTES:
        raise DomainError("PROOF_TOO_LARGE", "The proof file must be 5 MB or smaller.", field="proof")
    head = upload.read(16)
    upload.seek(0)
    for signature, content_type, extension in PROOF_SIGNATURES:
        if head.startswith(signature):
            return content_type, extension
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise DomainError(
        "PROOF_TYPE_UNSUPPORTED",
        "Proof must be a JPEG, PNG or WebP image, or a PDF.",
        field="proof",
    )


class MeterService:
    @staticmethod
    def create(*, actor, tenant, unit, meter_number, unit_of_measure="kWh", multiplier=Decimal("1"), installed_at=None):
        if unit.tenant_id != tenant.id:
            raise DomainError("NOT_FOUND", "Unit not found.", status_code=404)
        try:
            with transaction.atomic():
                meter = Meter.objects.create(
                    tenant=tenant,
                    unit=unit,
                    meter_number=meter_number,
                    unit_of_measure=unit_of_measure,
                    multiplier=multiplier,
                    installed_at=installed_at,
                )
                _audit(
                    actor=actor,
                    tenant=tenant,
                    action="meter.created",
                    target_type="Meter",
                    target_id=meter.id,
                    summary=f"Created meter {meter_number} for unit {unit.identifier}",
                    metadata={"multiplier": str(multiplier)},
                )
        except IntegrityError:
            raise DomainError(
                "DUPLICATE_METER", "A meter with this number already exists.", field="meter_number"
            )
        return meter

    @staticmethod
    def update(*, actor, meter, changes):
        with transaction.atomic():
            meter = Meter.objects.select_for_update().get(pk=meter.pk)
            before = {}
            for field in ("is_active", "multiplier", "unit_of_measure", "installed_at"):
                if field in changes and getattr(meter, field) != changes[field]:
                    before[field] = str(getattr(meter, field))
                    setattr(meter, field, changes[field])
            if not before:
                return meter
            meter.save()
            _audit(
                actor=actor,
                tenant=meter.tenant,
                action="meter.updated",
                target_type="Meter",
                target_id=meter.id,
                summary=f"Updated meter {meter.meter_number}",
                metadata={"before": before, "after": {k: str(getattr(meter, k)) for k in before}},
            )
        return meter


class MeterReadingService:
    @staticmethod
    def _check_chronology(meter, reading_date, value, exclude_pk=None):
        readings = MeterReading.objects.for_tenant(meter.tenant).filter(meter=meter)
        if exclude_pk is not None:
            readings = readings.exclude(pk=exclude_pk)
        previous = readings.filter(reading_date__lt=reading_date).order_by("-reading_date").first()
        following = readings.filter(reading_date__gt=reading_date).order_by("reading_date").first()
        if previous is not None and value < previous.reading_value:
            raise DomainError(
                "READING_BELOW_PREVIOUS",
                f"The reading is below the previous reading ({previous.reading_value} on {previous.reading_date}).",
                field="reading_value",
            )
        if following is not None and value > following.reading_value:
            raise DomainError(
                "READING_ABOVE_NEXT",
                f"The reading is above the later reading ({following.reading_value} on {following.reading_date}).",
                field="reading_value",
            )

    @staticmethod
    def record(*, actor, tenant, meter, reading_date, reading_value, notes="", proof=None, source=MeterReading.Source.MANUAL):
        if meter.tenant_id != tenant.id:
            raise DomainError("NOT_FOUND", "Meter not found.", status_code=404)
        if not meter.is_active:
            raise DomainError("METER_INACTIVE", "This meter is inactive.", field="meter_id")
        if reading_value < 0:
            raise DomainError("READING_NEGATIVE", "A reading cannot be negative.", field="reading_value")
        if reading_date > server_today():
            raise DomainError(
                "READING_IN_FUTURE", "A reading cannot be dated in the future.", field="reading_date"
            )
        content_type = ""
        if proof is not None:
            content_type, _ = sniff_proof(proof)
        try:
            with transaction.atomic():
                Meter.objects.select_for_update().get(pk=meter.pk)
                MeterReadingService._check_chronology(meter, reading_date, reading_value)
                reading = MeterReading(
                    tenant=tenant,
                    meter=meter,
                    reading_date=reading_date,
                    reading_value=reading_value,
                    notes=notes,
                    source=source,
                    recorded_by=actor,
                    proof_content_type=content_type,
                )
                if proof is not None:
                    reading.proof = proof
                with transaction.atomic():
                    reading.save()
                _audit(
                    actor=actor,
                    tenant=tenant,
                    action="meter_reading.recorded",
                    target_type="MeterReading",
                    target_id=reading.id,
                    summary=f"Reading {reading_value} on {reading_date} for meter {meter.meter_number}",
                    metadata={"has_proof": proof is not None},
                )
        except IntegrityError:
            raise DomainError(
                "DUPLICATE_READING",
                "This meter already has a reading on that date. Use a correction to change it.",
                field="reading_date",
            )
        return reading

    @staticmethod
    def correct(*, actor, reading, corrected_value, reason):
        _require(reason and reason.strip(), "REASON_REQUIRED", "A reason is required.", field="reason")
        if corrected_value < 0:
            raise DomainError("READING_NEGATIVE", "A reading cannot be negative.", field="corrected_value")
        with transaction.atomic():
            meter = Meter.objects.select_for_update().get(pk=reading.meter_id)
            reading = MeterReading.objects.select_for_update().get(pk=reading.pk)
            if corrected_value == reading.reading_value:
                raise DomainError(
                    "CORRECTION_UNCHANGED", "The corrected value equals the current value.", field="corrected_value"
                )
            MeterReadingService._check_chronology(meter, reading.reading_date, corrected_value, exclude_pk=reading.pk)
            correction = MeterReadingCorrection.objects.create(
                tenant=reading.tenant,
                reading=reading,
                original_value=reading.reading_value,
                corrected_value=corrected_value,
                reason=reason.strip(),
                actor=actor,
            )
            original = reading.reading_value
            reading.reading_value = corrected_value
            reading.save(update_fields=["reading_value", "updated_at"])
            _audit(
                actor=actor,
                tenant=reading.tenant,
                action="meter_reading.corrected",
                target_type="MeterReading",
                target_id=reading.id,
                summary=f"Corrected reading {original} → {corrected_value}: {reason.strip()}",
                metadata={"original": str(original), "corrected": str(corrected_value)},
            )
        affected = (
            Bill.objects.for_tenant(reading.tenant)
            .filter(Q(line_items__opening_reading=reading) | Q(line_items__closing_reading=reading))
            .exclude(status__in=[Bill.Status.CANCELLED])
            .distinct()
        )
        return correction, list(affected)


class TariffService:
    @staticmethod
    def applicable(tenant, on_date, utility_type=Meter.UtilityType.ELECTRICITY):
        return (
            Tariff.objects.for_tenant(tenant)
            .filter(is_active=True, utility_type=utility_type, effective_from__lte=on_date)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
            .order_by("-effective_from")
            .first()
        )

    @staticmethod
    def create(*, actor, tenant, rate_per_unit_cents, effective_from, utility_type=Meter.UtilityType.ELECTRICITY):
        if rate_per_unit_cents < 0:
            raise DomainError("RATE_NEGATIVE", "The rate cannot be negative.", field="rate_per_unit_cents")
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            latest = (
                Tariff.objects.for_tenant(tenant)
                .filter(is_active=True, utility_type=utility_type)
                .order_by("-effective_from")
                .first()
            )
            if latest is not None:
                if effective_from <= latest.effective_from:
                    raise DomainError(
                        "TARIFF_NOT_AFTER_CURRENT",
                        f"A new rate must start after the current one (effective {latest.effective_from}).",
                        field="effective_from",
                    )
                if latest.effective_to is None or latest.effective_to >= effective_from:
                    latest.effective_to = effective_from - timedelta(days=1)
                    latest.save(update_fields=["effective_to", "updated_at"])
            tariff = Tariff.objects.create(
                tenant=tenant,
                utility_type=utility_type,
                rate_per_unit_cents=rate_per_unit_cents,
                effective_from=effective_from,
                created_by=actor,
            )
            _audit(
                actor=actor,
                tenant=tenant,
                action="tariff.created",
                target_type="Tariff",
                target_id=tariff.id,
                summary=f"Electricity rate {rate_per_unit_cents} minor units/unit from {effective_from}",
                metadata={
                    "previous_rate": str(latest.rate_per_unit_cents) if latest else None,
                    "rate": str(rate_per_unit_cents),
                },
            )
        return tariff


# --------------------------------------------------------------------------
# Billing engine
# --------------------------------------------------------------------------


def electricity_for_period(meter, period_start, period_end):
    """
    Reading selection rule for one meter and one period:

      closing = the latest reading dated within [period_start, period_end]
      opening = the latest reading dated before period_start; for a meter with
                no earlier reading (a first month), the earliest reading within
                the period that precedes the closing one

    Raises DomainError MISSING_READING / MISSING_OPENING_READING /
    NEGATIVE_CONSUMPTION — reported as cycle exceptions, never silently billed.
    """
    readings = MeterReading.objects.for_tenant(meter.tenant).filter(meter=meter)
    closing = (
        readings.filter(reading_date__gte=period_start, reading_date__lte=period_end)
        .order_by("-reading_date")
        .first()
    )
    if closing is None:
        raise DomainError(
            "MISSING_READING",
            f"Meter {meter.meter_number} has no reading for {_month_label(period_start)}.",
        )
    opening = readings.filter(reading_date__lt=period_start).order_by("-reading_date").first()
    if opening is None:
        opening = (
            readings.filter(reading_date__gte=period_start, reading_date__lt=closing.reading_date)
            .order_by("reading_date")
            .first()
        )
    if opening is None:
        raise DomainError(
            "MISSING_OPENING_READING",
            f"Meter {meter.meter_number} needs an opening reading before {closing.reading_date}.",
        )
    try:
        units = calculations.billed_units(opening.reading_value, closing.reading_value, meter.multiplier)
        raw = calculations.consumption(opening.reading_value, closing.reading_value)
    except calculations.NegativeConsumption:
        raise DomainError(
            "NEGATIVE_CONSUMPTION",
            f"Meter {meter.meter_number}: the closing reading is below the opening reading.",
        )
    return {"opening": opening, "closing": closing, "units": units, "consumption": raw}


def month_bounds(year, month):
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        raise DomainError("INVALID_PERIOD", "Choose a valid month.", field="period")
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


OPEN_BILL_STATUSES = (Bill.Status.PUBLISHED, Bill.Status.PARTIALLY_PAID)
ISSUED_BILL_STATUSES = (Bill.Status.PUBLISHED, Bill.Status.PARTIALLY_PAID, Bill.Status.PAID)


class BillService:
    MANUAL_LINE_TYPES = frozenset({"MAINTENANCE", "OTHER_CHARGE", "DISCOUNT", "ADJUSTMENT", "LATE_FEE"})

    @staticmethod
    def recompute_totals(bill):
        charges = bill.line_items.filter(type__in=BillLineItem.CHARGE_TYPES).aggregate(s=Sum("amount_cents"))["s"] or 0
        adjustments = bill.line_items.filter(type__in=BillLineItem.ADJUSTMENT_TYPES).aggregate(s=Sum("amount_cents"))["s"] or 0
        total = charges + adjustments
        if total < 0:
            raise DomainError("NEGATIVE_TOTAL", "Discounts and adjustments cannot exceed the charges.")
        bill.subtotal_cents = charges
        bill.adjustments_cents = adjustments
        bill.total_cents = total

    @staticmethod
    def settle_status(bill):
        if bill.status in (Bill.Status.DRAFT, Bill.Status.CANCELLED):
            return
        if bill.amount_paid_cents <= 0:
            bill.status = Bill.Status.PAID if bill.total_cents == 0 else Bill.Status.PUBLISHED
        elif bill.amount_paid_cents >= bill.total_cents:
            bill.status = Bill.Status.PAID
        else:
            bill.status = Bill.Status.PARTIALLY_PAID

    @staticmethod
    def lease_prerequisites(lease, period_start, period_end):
        """Compute (electricity lines, issues) for a lease without writing."""
        issues, lines = [], []
        meters = list(
            Meter.objects.for_tenant(lease.tenant).filter(unit=lease.unit, is_active=True).order_by("meter_number")
        )
        tariff = TariffService.applicable(lease.tenant, period_end) if meters else None
        if meters and tariff is None:
            issues.append(
                {"code": "MISSING_TARIFF", "message": f"No electricity rate is effective on {period_end}.", "blocking": True}
            )
        for meter in meters:
            try:
                usage = electricity_for_period(meter, period_start, period_end)
            except DomainError as exc:
                issues.append({"code": exc.code, "message": exc.message, "blocking": True, "meter_id": str(meter.id)})
                continue
            if tariff is not None:
                lines.append((meter, usage, tariff))
        if lease.monthly_rent_cents == 0:
            issues.append({"code": "MISSING_RENT", "message": "The lease rent is zero.", "blocking": False})
        return lines, issues

    @staticmethod
    def generate_for_lease(*, actor, cycle, lease):
        tenant = cycle.tenant
        settings_row = WorkspaceSettingsService.get(tenant)
        electricity, issues = BillService.lease_prerequisites(lease, cycle.period_start, cycle.period_end)
        blocking = [i for i in issues if i["blocking"]]
        if blocking:
            raise DomainError(blocking[0]["code"], blocking[0]["message"])
        unit = lease.unit
        resident = lease.resident
        label = _month_label(cycle.period_start)
        with transaction.atomic():
            bill = Bill.objects.create(
                tenant=tenant,
                cycle=cycle,
                property=unit.property,
                unit=unit,
                resident=resident,
                lease=lease,
                period_start=cycle.period_start,
                period_end=cycle.period_end,
                due_date=cycle.period_end + timedelta(days=settings_row.due_days_after_period_end),
                currency=settings_row.currency,
                property_name=unit.property.name,
                unit_identifier=unit.identifier,
                resident_name=resident.display_name,
                resident_email=resident.user.email,
                generated_by=actor,
            )
            order = 0
            if lease.monthly_rent_cents > 0:
                BillLineItem.objects.create(
                    bill=bill,
                    type=BillLineItem.Type.RENT,
                    description=f"Rent — {label}",
                    quantity=Decimal("1"),
                    unit_price_cents=Decimal(lease.monthly_rent_cents),
                    amount_cents=lease.monthly_rent_cents,
                    sort_order=order,
                )
                order += 1
            for meter, usage, tariff in electricity:
                BillLineItem.objects.create(
                    bill=bill,
                    type=BillLineItem.Type.ELECTRICITY,
                    description=f"Electricity — {label} (meter {meter.meter_number})",
                    quantity=usage["units"],
                    unit_price_cents=tariff.rate_per_unit_cents,
                    amount_cents=calculations.charge_cents(usage["units"], tariff.rate_per_unit_cents),
                    meter=meter,
                    meter_number=meter.meter_number,
                    opening_reading=usage["opening"],
                    closing_reading=usage["closing"],
                    opening_reading_value=usage["opening"].reading_value,
                    closing_reading_value=usage["closing"].reading_value,
                    opening_reading_date=usage["opening"].reading_date,
                    closing_reading_date=usage["closing"].reading_date,
                    multiplier=meter.multiplier,
                    units_consumed=usage["consumption"],
                    tariff=tariff,
                    sort_order=order,
                )
                order += 1
            if settings_row.default_maintenance_cents > 0:
                BillLineItem.objects.create(
                    bill=bill,
                    type=BillLineItem.Type.MAINTENANCE,
                    description=f"Maintenance — {label}",
                    quantity=Decimal("1"),
                    unit_price_cents=Decimal(settings_row.default_maintenance_cents),
                    amount_cents=settings_row.default_maintenance_cents,
                    sort_order=order,
                )
            BillService.recompute_totals(bill)
            bill.save()
        return bill

    @staticmethod
    def add_line_item(*, actor, bill, type, description, amount_cents, quantity=None, unit_price_cents=None):
        if type not in BillService.MANUAL_LINE_TYPES:
            raise DomainError("LINE_TYPE_NOT_MANUAL", "This charge type cannot be added manually.", field="type")
        if type == BillLineItem.Type.ADJUSTMENT:
            if amount_cents == 0:
                raise DomainError("AMOUNT_REQUIRED", "An adjustment cannot be zero.", field="amount_cents")
        elif amount_cents <= 0:
            raise DomainError("AMOUNT_POSITIVE", "Enter an amount greater than zero.", field="amount_cents")
        stored = -abs(amount_cents) if type == BillLineItem.Type.DISCOUNT else amount_cents
        with transaction.atomic():
            bill = Bill.objects.select_for_update().get(pk=bill.pk)
            if bill.status != Bill.Status.DRAFT:
                raise DomainError(
                    "BILL_NOT_DRAFT",
                    "A published bill cannot be edited. Use a correction instead.",
                    status_code=409,
                )
            last = bill.line_items.order_by("-sort_order").first()
            line = BillLineItem.objects.create(
                bill=bill,
                type=type,
                description=description,
                amount_cents=stored,
                quantity=quantity,
                unit_price_cents=unit_price_cents,
                sort_order=(last.sort_order + 1) if last else 0,
            )
            BillService.recompute_totals(bill)
            bill.save()
            _audit(
                actor=actor,
                tenant=bill.tenant,
                action="bill.line_item_added",
                target_type="Bill",
                target_id=bill.id,
                summary=f"Added {type} {stored} to draft bill",
                metadata={"line_item_id": str(line.id), "amount_cents": stored},
            )
        return line

    @staticmethod
    def remove_line_item(*, actor, bill, line_item_id):
        with transaction.atomic():
            bill = Bill.objects.select_for_update().get(pk=bill.pk)
            if bill.status != Bill.Status.DRAFT:
                raise DomainError(
                    "BILL_NOT_DRAFT",
                    "A published bill cannot be edited. Use a correction instead.",
                    status_code=409,
                )
            try:
                line = bill.line_items.get(pk=line_item_id)
            except BillLineItem.DoesNotExist:
                raise DomainError("NOT_FOUND", "Line item not found.", status_code=404)
            snapshot = {"type": line.type, "amount_cents": line.amount_cents}
            line.delete()
            BillService.recompute_totals(bill)
            bill.save()
            _audit(
                actor=actor,
                tenant=bill.tenant,
                action="bill.line_item_removed",
                target_type="Bill",
                target_id=bill.id,
                summary=f"Removed {snapshot['type']} from draft bill",
                metadata=snapshot,
            )
        return bill

    @staticmethod
    def publish(*, actor, bill):
        with transaction.atomic():
            bill = Bill.objects.select_for_update(of=("self",)).select_related("resident__user").get(pk=bill.pk)
            if bill.status in ISSUED_BILL_STATUSES:
                return bill  # idempotent: publishing twice changes nothing
            if bill.status == Bill.Status.CANCELLED:
                raise DomainError("BILL_CANCELLED", "A cancelled bill cannot be published.", status_code=409)
            number = SequenceService.next_value(bill.tenant, "bill")
            bill.bill_number = f"BILL-{bill.period_start.year}-{number:06d}"
            bill.published_at = timezone.now()
            bill.status = Bill.Status.PUBLISHED
            BillService.settle_status(bill)
            bill.save()
            _audit(
                actor=actor,
                tenant=bill.tenant,
                action="bill.published",
                target_type="Bill",
                target_id=bill.id,
                summary=f"Published {bill.bill_number} for {bill.resident_name} ({bill.total_cents} {bill.currency})",
                metadata={"total_cents": bill.total_cents, "bill_number": bill.bill_number},
            )
            NotificationService.notify(
                recipient=bill.resident.user,
                kind=Notification.Kind.BILL_PUBLISHED,
                tenant=bill.tenant,
                title=f"Your {_month_label(bill.period_start)} bill is ready",
                body=f"Unit {bill.unit_identifier} · due {bill.due_date:%d %b %Y}.",
                data={"bill_id": str(bill.id)},
            )
        return bill

    @staticmethod
    def cancel(*, actor, bill, reason):
        _require(reason and reason.strip(), "REASON_REQUIRED", "A reason is required.", field="reason")
        with transaction.atomic():
            bill = Bill.objects.select_for_update(of=("self",)).select_related("resident__user").get(pk=bill.pk)
            if bill.status == Bill.Status.CANCELLED:
                return bill
            if bill.amount_paid_cents > 0 or bill.payments.filter(status=Payment.Status.COMPLETED).exists():
                raise DomainError(
                    "BILL_HAS_PAYMENTS",
                    "A bill with recorded payments cannot be cancelled. Void the payments or issue a correction.",
                    status_code=409,
                )
            was_published = bill.published_at is not None
            bill.status = Bill.Status.CANCELLED
            bill.cancelled_at = timezone.now()
            bill.cancellation_reason = reason.strip()
            bill.save()
            _audit(
                actor=actor,
                tenant=bill.tenant,
                action="bill.cancelled",
                target_type="Bill",
                target_id=bill.id,
                summary=f"Cancelled bill for {bill.resident_name}: {reason.strip()}",
                metadata={"was_published": was_published, "total_cents": bill.total_cents},
            )
            if was_published:
                NotificationService.notify(
                    recipient=bill.resident.user,
                    kind=Notification.Kind.BILL_CANCELLED,
                    tenant=bill.tenant,
                    title=f"Your {_month_label(bill.period_start)} bill was cancelled",
                    body=reason.strip(),
                    data={"bill_id": str(bill.id)},
                )
        return bill


class BillCorrectionService:
    @staticmethod
    def _apply(*, actor, bill, kind, reason, delta, description, original, corrected, quantity=None, unit_price=None):
        new_total = bill.total_cents + delta
        if new_total < 0 or new_total < bill.amount_paid_cents:
            raise DomainError(
                "CORRECTION_BELOW_PAID",
                "A correction cannot reduce the bill below the amount already paid.",
                field="amount_cents",
            )
        correction = BillCorrection.objects.create(
            tenant=bill.tenant,
            bill=bill,
            kind=kind,
            reason=reason,
            original_values=original,
            corrected_values=corrected,
            amount_delta_cents=delta,
            actor=actor,
        )
        if delta != 0:
            last = bill.line_items.order_by("-sort_order").first()
            BillLineItem.objects.create(
                bill=bill,
                type=BillLineItem.Type.ADJUSTMENT,
                description=description[:255],
                amount_cents=delta,
                quantity=quantity,
                unit_price_cents=unit_price,
                correction=correction,
                sort_order=(last.sort_order + 1) if last else 0,
            )
        BillService.recompute_totals(bill)
        BillService.settle_status(bill)
        bill.save()
        _audit(
            actor=actor,
            tenant=bill.tenant,
            action="bill.corrected",
            target_type="Bill",
            target_id=bill.id,
            summary=f"Correction on {bill.bill_number or 'bill'}: {reason}",
            metadata={"kind": kind, "delta_cents": delta, "original": original, "corrected": corrected},
        )
        NotificationService.notify(
            recipient=bill.resident.user,
            kind=Notification.Kind.BILL_CORRECTED,
            tenant=bill.tenant,
            title=f"Your {_month_label(bill.period_start)} bill was corrected",
            body=reason,
            data={"bill_id": str(bill.id)},
        )
        return correction

    @staticmethod
    def adjust_amount(*, actor, bill, amount_delta_cents, reason, description=""):
        _require(reason and reason.strip(), "REASON_REQUIRED", "A reason is required.", field="reason")
        if amount_delta_cents == 0:
            raise DomainError("AMOUNT_REQUIRED", "A correction cannot be zero.", field="amount_cents")
        with transaction.atomic():
            bill = Bill.objects.select_for_update(of=("self",)).select_related("resident__user").get(pk=bill.pk)
            if bill.status not in ISSUED_BILL_STATUSES:
                raise DomainError(
                    "BILL_NOT_PUBLISHED", "Only a published bill is corrected; edit a draft directly.", status_code=409
                )
            return BillCorrectionService._apply(
                actor=actor,
                bill=bill,
                kind=BillCorrection.Kind.AMOUNT_ADJUSTMENT,
                reason=reason.strip(),
                delta=amount_delta_cents,
                description=description or f"Correction: {reason.strip()}",
                original={"total_cents": bill.total_cents},
                corrected={"total_cents": bill.total_cents + amount_delta_cents},
            )

    @staticmethod
    def correct_reading(*, actor, bill, line_item_id, corrected_closing_value, reason):
        _require(reason and reason.strip(), "REASON_REQUIRED", "A reason is required.", field="reason")
        with transaction.atomic():
            bill = Bill.objects.select_for_update(of=("self",)).select_related("resident__user").get(pk=bill.pk)
            if bill.status not in ISSUED_BILL_STATUSES:
                raise DomainError(
                    "BILL_NOT_PUBLISHED", "Only a published bill is corrected; regenerate a draft instead.", status_code=409
                )
            try:
                line = bill.line_items.get(pk=line_item_id, type=BillLineItem.Type.ELECTRICITY)
            except BillLineItem.DoesNotExist:
                raise DomainError("NOT_FOUND", "Electricity line not found.", status_code=404)
            previous = (
                BillCorrection.objects.filter(
                    bill=bill,
                    kind=BillCorrection.Kind.READING_CORRECTION,
                    corrected_values__line_item_id=str(line.id),
                )
                .order_by("-created_at")
                .first()
            )
            if previous is not None:
                effective_closing = Decimal(previous.corrected_values["closing_reading_value"])
                effective_amount = int(previous.corrected_values["amount_cents"])
                effective_units = Decimal(previous.corrected_values["units"])
            else:
                effective_closing = line.closing_reading_value
                effective_amount = line.amount_cents
                effective_units = line.quantity
            try:
                new_units = calculations.billed_units(
                    line.opening_reading_value, corrected_closing_value, line.multiplier
                )
            except calculations.NegativeConsumption:
                raise DomainError(
                    "NEGATIVE_CONSUMPTION",
                    "The corrected closing reading is below the opening reading.",
                    field="corrected_closing_value",
                )
            if corrected_closing_value == effective_closing:
                raise DomainError(
                    "CORRECTION_UNCHANGED", "The corrected reading equals the billed reading.", field="corrected_closing_value"
                )
            new_amount = calculations.charge_cents(new_units, line.unit_price_cents)
            delta = new_amount - effective_amount
            return BillCorrectionService._apply(
                actor=actor,
                bill=bill,
                kind=BillCorrection.Kind.READING_CORRECTION,
                reason=reason.strip(),
                delta=delta,
                description=(
                    f"Electricity correction — meter {line.meter_number}: closing reading "
                    f"{effective_closing} → {corrected_closing_value}"
                ),
                original={
                    "line_item_id": str(line.id),
                    "closing_reading_value": str(effective_closing),
                    "units": str(effective_units),
                    "amount_cents": effective_amount,
                },
                corrected={
                    "line_item_id": str(line.id),
                    "closing_reading_value": str(corrected_closing_value),
                    "units": str(new_units),
                    "amount_cents": new_amount,
                },
                quantity=new_units - effective_units,
                unit_price=line.unit_price_cents,
            )


class BillingCycleService:
    @staticmethod
    def open(*, actor, tenant, year, month):
        period_start, period_end = month_bounds(year, month)
        existing = BillingCycle.objects.for_tenant(tenant).filter(period_start=period_start).first()
        if existing is not None:
            return existing, False
        try:
            with transaction.atomic():
                cycle = BillingCycle.objects.create(
                    tenant=tenant, period_start=period_start, period_end=period_end, opened_by=actor
                )
                _audit(
                    actor=actor,
                    tenant=tenant,
                    action="billing_cycle.opened",
                    target_type="BillingCycle",
                    target_id=cycle.id,
                    summary=f"Opened billing cycle {_month_label(period_start)}",
                )
        except IntegrityError:
            return BillingCycle.objects.for_tenant(tenant).get(period_start=period_start), False
        return cycle, True

    @staticmethod
    def billable_leases(cycle):
        return (
            Lease.objects.for_tenant(cycle.tenant)
            .filter(status__in=[Lease.Status.ACTIVE, Lease.Status.ENDED], start_date__lte=cycle.period_end)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=cycle.period_start))
            .select_related("unit", "unit__property", "resident", "resident__user")
            .order_by("unit__property__name", "unit__identifier")
        )

    @staticmethod
    def progress(cycle):
        leases = list(BillingCycleService.billable_leases(cycle))
        bills = list(cycle.bills.exclude(status=Bill.Status.CANCELLED))
        bill_keys = {(b.unit_id, b.resident_id): b for b in bills}
        meters = list(
            Meter.objects.for_tenant(cycle.tenant).filter(
                unit_id__in={lease.unit_id for lease in leases}, is_active=True
            )
        )
        read_meter_ids = set(
            MeterReading.objects.for_tenant(cycle.tenant)
            .filter(
                meter__in=meters,
                reading_date__gte=cycle.period_start,
                reading_date__lte=cycle.period_end,
            )
            .values_list("meter_id", flat=True)
        )
        exceptions = []
        for lease in leases:
            existing = bill_keys.get((lease.unit_id, lease.resident_id))
            if existing is not None and existing.status != Bill.Status.DRAFT:
                continue
            _, issues = BillService.lease_prerequisites(lease, cycle.period_start, cycle.period_end)
            for issue in issues:
                exceptions.append(
                    {
                        **issue,
                        "lease_id": str(lease.id),
                        "unit_id": str(lease.unit_id),
                        "unit_identifier": lease.unit.identifier,
                        "property_name": lease.unit.property.name,
                        "resident_name": lease.resident.display_name,
                    }
                )
        issued = [b for b in bills if b.status in ISSUED_BILL_STATUSES]
        return {
            "expected_bills": len(leases),
            "meters_expected": len(meters),
            "readings_entered": len(read_meter_ids),
            "bills_generated": len(bills),
            "bills_draft": sum(1 for b in bills if b.status == Bill.Status.DRAFT),
            "bills_published": len(issued),
            "bills_paid": sum(1 for b in bills if b.status == Bill.Status.PAID),
            "billed_cents": sum(b.total_cents for b in issued),
            "collected_cents": sum(b.amount_paid_cents for b in issued),
            "exceptions": exceptions,
        }

    @staticmethod
    def generate(*, actor, cycle, regenerate_drafts=False):
        if cycle.status != BillingCycle.Status.OPEN:
            raise DomainError("CYCLE_CLOSED", "This billing cycle is closed.", status_code=409)
        created, skipped = [], []
        for lease in BillingCycleService.billable_leases(cycle):
            label = {"lease_id": str(lease.id), "unit_identifier": lease.unit.identifier, "resident_name": lease.resident.display_name}
            existing = (
                Bill.objects.for_tenant(cycle.tenant)
                .filter(unit=lease.unit, resident=lease.resident, period_start=cycle.period_start)
                .exclude(status=Bill.Status.CANCELLED)
                .first()
            )
            if existing is not None:
                if existing.status == Bill.Status.DRAFT and regenerate_drafts:
                    with transaction.atomic():
                        Bill.objects.filter(pk=existing.pk, status=Bill.Status.DRAFT).delete()
                else:
                    skipped.append({**label, "code": "BILL_EXISTS", "message": "A bill already exists."})
                    continue
            try:
                bill = BillService.generate_for_lease(actor=actor, cycle=cycle, lease=lease)
            except DomainError as exc:
                skipped.append({**label, "code": exc.code, "message": exc.message})
                continue
            except IntegrityError:
                # A concurrent generation won the unique constraint.
                skipped.append({**label, "code": "BILL_EXISTS", "message": "A bill already exists."})
                continue
            created.append(bill)
        if created:
            _audit(
                actor=actor,
                tenant=cycle.tenant,
                action="bills.generated",
                target_type="BillingCycle",
                target_id=cycle.id,
                summary=f"Generated {len(created)} draft bill(s) for {_month_label(cycle.period_start)}",
                metadata={"bill_ids": [str(b.id) for b in created][:200], "skipped": len(skipped)},
            )
        return created, skipped

    @staticmethod
    def publish_all(*, actor, cycle):
        published = []
        for bill in cycle.bills.filter(status=Bill.Status.DRAFT):
            published.append(BillService.publish(actor=actor, bill=bill))
        return published

    @staticmethod
    def close(*, actor, cycle):
        with transaction.atomic():
            cycle = BillingCycle.objects.select_for_update().get(pk=cycle.pk)
            if cycle.status == BillingCycle.Status.CLOSED:
                return cycle
            if cycle.bills.filter(status=Bill.Status.DRAFT).exists():
                raise DomainError(
                    "CYCLE_HAS_DRAFTS", "Publish or cancel the remaining draft bills before closing.", status_code=409
                )
            cycle.status = BillingCycle.Status.CLOSED
            cycle.closed_at = timezone.now()
            cycle.save(update_fields=["status", "closed_at", "updated_at"])
            _audit(
                actor=actor,
                tenant=cycle.tenant,
                action="billing_cycle.closed",
                target_type="BillingCycle",
                target_id=cycle.id,
                summary=f"Closed billing cycle {_month_label(cycle.period_start)}",
            )
        return cycle


# --------------------------------------------------------------------------
# Payments and receipts
# --------------------------------------------------------------------------


class ReceiptService:
    @staticmethod
    def issue(*, payment, bill):
        issued_at = timezone.now()
        number = SequenceService.next_value(bill.tenant, "receipt")
        return Receipt.objects.create(
            tenant=bill.tenant,
            bill=bill,
            payment=payment,
            receipt_number=f"REC-{issued_at.year}-{number:06d}",
            issued_at=issued_at,
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            resident_name=bill.resident_name,
            unit_identifier=bill.unit_identifier,
            property_name=bill.property_name,
            bill_number=bill.bill_number,
            payment_method=payment.method,
        )


class PaymentService:
    @staticmethod
    def _existing_for_key(tenant, key, bill, amount_cents):
        existing = Payment.objects.for_tenant(tenant).filter(idempotency_key=key).first()
        if existing is None:
            return None
        if existing.bill_id != bill.id or existing.amount_cents != amount_cents:
            raise DomainError(
                "IDEMPOTENCY_KEY_REUSED",
                "This request key was already used for a different payment.",
                status_code=409,
            )
        return existing

    @staticmethod
    def record(*, actor, tenant, bill, amount_cents, payment_date, method, reference="", notes="", idempotency_key=""):
        """
        Record money received. Returns (payment, created). A retried request with
        the same `idempotency_key` returns the original payment with created=False
        instead of crediting the bill twice.

        Overpayment policy: refused. The amount may not exceed what is due.
        """
        if bill.tenant_id != tenant.id:
            raise DomainError("NOT_FOUND", "Bill not found.", status_code=404)
        if idempotency_key:
            existing = PaymentService._existing_for_key(tenant, idempotency_key, bill, amount_cents)
            if existing is not None:
                return existing, False
        if amount_cents <= 0:
            raise DomainError("AMOUNT_POSITIVE", "Enter an amount greater than zero.", field="amount_cents")
        if payment_date > server_today():
            raise DomainError("PAYMENT_DATE_IN_FUTURE", "A payment cannot be dated in the future.", field="payment_date")
        try:
            with transaction.atomic():
                bill = Bill.objects.select_for_update(of=("self",)).select_related("resident__user").get(pk=bill.pk)
                if bill.status not in OPEN_BILL_STATUSES:
                    raise DomainError(
                        "BILL_NOT_PAYABLE",
                        "Payments can be recorded only against a published bill with an amount due.",
                        status_code=409,
                    )
                due = bill.total_cents - bill.amount_paid_cents
                if amount_cents > due:
                    raise DomainError(
                        "OVERPAYMENT",
                        f"The amount exceeds what is due ({due}).",
                        field="amount_cents",
                    )
                with transaction.atomic():
                    payment = Payment.objects.create(
                        tenant=tenant,
                        bill=bill,
                        resident=bill.resident,
                        amount_cents=amount_cents,
                        currency=bill.currency,
                        payment_date=payment_date,
                        method=method,
                        reference=reference,
                        notes=notes,
                        idempotency_key=idempotency_key,
                        recorded_by=actor,
                    )
                bill.amount_paid_cents += amount_cents
                BillService.settle_status(bill)
                bill.save()
                receipt = ReceiptService.issue(payment=payment, bill=bill)
                _audit(
                    actor=actor,
                    tenant=tenant,
                    action="payment.recorded",
                    target_type="Payment",
                    target_id=payment.id,
                    summary=f"Recorded {amount_cents} {bill.currency} by {method} against {bill.bill_number}",
                    metadata={"bill_id": str(bill.id), "amount_cents": amount_cents, "method": method},
                )
                _audit(
                    actor=actor,
                    tenant=tenant,
                    action="receipt.issued",
                    target_type="Receipt",
                    target_id=receipt.id,
                    summary=f"Issued {receipt.receipt_number}",
                    metadata={"payment_id": str(payment.id)},
                )
                resident_user = bill.resident.user
                NotificationService.notify(
                    recipient=resident_user,
                    kind=Notification.Kind.PAYMENT_RECORDED,
                    tenant=tenant,
                    title=f"Payment received for your {_month_label(bill.period_start)} bill",
                    body=f"Bill status: {bill.get_status_display()}.",
                    data={"bill_id": str(bill.id), "payment_id": str(payment.id)},
                )
                NotificationService.notify(
                    recipient=resident_user,
                    kind=Notification.Kind.RECEIPT_ISSUED,
                    tenant=tenant,
                    title=f"Receipt {receipt.receipt_number} issued",
                    data={"receipt_id": str(receipt.id), "bill_id": str(bill.id)},
                )
                for owner in _owners(tenant, exclude=actor):
                    NotificationService.notify(
                        recipient=owner,
                        kind=Notification.Kind.PAYMENT_RECORDED,
                        tenant=tenant,
                        title=f"Payment recorded from {bill.resident_name}",
                        body=f"Receipt {receipt.receipt_number}.",
                        data={"bill_id": str(bill.id), "payment_id": str(payment.id)},
                    )
        except IntegrityError:
            if idempotency_key:
                existing = PaymentService._existing_for_key(tenant, idempotency_key, bill, amount_cents)
                if existing is not None:
                    return existing, False
            raise DomainError(
                "DUPLICATE_PAYMENT_REFERENCE",
                "A payment with this reference has already been recorded.",
                field="reference",
                status_code=409,
            )
        return payment, True

    @staticmethod
    def void(*, actor, payment, reason):
        _require(reason and reason.strip(), "REASON_REQUIRED", "A reason is required.", field="reason")
        with transaction.atomic():
            bill = Bill.objects.select_for_update(of=("self",)).select_related("resident__user").get(pk=payment.bill_id)
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status == Payment.Status.VOIDED:
                return payment
            payment.status = Payment.Status.VOIDED
            payment.voided_at = timezone.now()
            payment.void_reason = reason.strip()
            payment.save()
            bill.amount_paid_cents -= payment.amount_cents
            BillService.settle_status(bill)
            bill.save()
            _audit(
                actor=actor,
                tenant=bill.tenant,
                action="payment.voided",
                target_type="Payment",
                target_id=payment.id,
                summary=f"Voided payment of {payment.amount_cents}: {reason.strip()}",
                metadata={"bill_id": str(bill.id), "amount_cents": payment.amount_cents},
            )
            NotificationService.notify(
                recipient=bill.resident.user,
                kind=Notification.Kind.PAYMENT_VOIDED,
                tenant=bill.tenant,
                title=f"A payment on your {_month_label(bill.period_start)} bill was voided",
                body=reason.strip(),
                data={"bill_id": str(bill.id)},
            )
        return payment

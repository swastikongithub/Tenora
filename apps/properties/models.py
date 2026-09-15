"""
Property billing domain — docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md.

Two financial domains live in this codebase and they never share a table:

    TENORA SUBSCRIPTION   workspace owner -> Tenora     apps.billing
    PROPERTY BILLING      resident -> workspace owner   apps.properties (here)

Nothing in this module references `Plan`, `Subscription` or the payment gateway.

Ownership. Every model here carries an explicit `tenant` foreign key (the
existing `Tenant` model IS the workspace — the plan's terminology table) and
uses `TenantScopedManager`, so every read goes through `.for_tenant(tenant)`.
Where a child also points at a parent that has its own tenant (a Unit's
Property, a Bill's Unit), the service layer is the single writer and asserts
`child.tenant == parent.tenant` at creation; the isolation tests pin that
invariant.

Deletion. Financial rows are PROTECTed, never CASCADEd: a property, unit,
resident, lease or meter that has billing history cannot be removed out from
under it. Lifecycle is expressed with status / is_active instead.

Money. Integer minor units (`*_cents`, the project convention — paise for INR)
plus a currency code, never floats. Meter readings, multipliers and per-unit
rates need fractional precision, so they are `Decimal`s with explicit places;
the ONE rounding to integer minor units happens in
`apps.properties.calculations`, ROUND_HALF_UP, and is documented there.
"""

import builtins
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.tenants.managers import TenantScopedManager
from apps.tenants.models import Tenant


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class WorkspaceSettings(TimestampedModel):
    """
    Workspace profile + billing defaults (plan §14.1 "Owner settings"). One row
    per workspace, created lazily on first read.

    Every value here affects FUTURE bills only: a bill snapshots what it used
    (currency, due date, maintenance charge) when it is generated, so changing a
    default can never rewrite an issued document.
    """

    tenant = models.OneToOneField(
        Tenant, on_delete=models.PROTECT, related_name="property_settings"
    )
    display_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=500, blank=True)
    receipt_footer = models.CharField(max_length=500, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    # Due date = billing period end + this many days.
    due_days_after_period_end = models.PositiveSmallIntegerField(default=10)
    # Added as a MAINTENANCE line to every generated bill when non-zero.
    default_maintenance_cents = models.PositiveIntegerField(default=0)

    objects = TenantScopedManager()


class Property(TimestampedModel):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="properties"
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, default="IN")
    is_active = models.BooleanField(default=True)

    objects = TenantScopedManager()

    class Meta:
        verbose_name_plural = "properties"
        indexes = [models.Index(fields=["tenant", "is_active"])]

    def __str__(self):
        return self.name


class Unit(TimestampedModel):
    class Status(models.TextChoices):
        VACANT = "VACANT", "Vacant"
        OCCUPIED = "OCCUPIED", "Occupied"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        INACTIVE = "INACTIVE", "Inactive"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    property = models.ForeignKey(
        Property, on_delete=models.PROTECT, related_name="units"
    )
    identifier = models.CharField(max_length=50)
    floor = models.CharField(max_length=20, blank=True)
    unit_type = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.VACANT
    )

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "identifier"], name="unique_unit_per_property"
            )
        ]
        indexes = [models.Index(fields=["tenant", "property"])]

    def __str__(self):
        return f"{self.property.name} / {self.identifier}"


class Resident(TimestampedModel):
    """
    The property-domain profile of a person living in a workspace's units. The
    identity is the existing `User` — no second password, no second login.

    Created only by InvitationService.accept (i.e. with the person's consent).
    Status follows the membership: INACTIVE once they leave or are removed, but
    the row stays because leases, bills and receipts point at it.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="residencies"
    )
    display_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, blank=True)
    reference = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"], name="unique_resident_per_workspace"
            )
        ]

    def __str__(self):
        return self.display_name


class Lease(TimestampedModel):
    """
    A resident's occupancy of a unit over time. Rent here is the CURRENT rent —
    bills copy it into a RENT line when generated, so changing it later never
    touches an issued bill.

    At most one ACTIVE lease per unit, as a partial unique constraint. Date
    overlap against historical (ENDED) leases is checked by LeaseService under a
    row lock on the unit.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        ENDED = "ENDED", "Ended"
        CANCELLED = "CANCELLED", "Cancelled"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="leases")
    resident = models.ForeignKey(
        Resident, on_delete=models.PROTECT, related_name="leases"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    monthly_rent_cents = models.PositiveBigIntegerField()
    security_deposit_cents = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["unit"],
                condition=Q(status="ACTIVE"),
                name="one_active_lease_per_unit",
            ),
            models.CheckConstraint(
                check=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="lease_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["resident"]),
        ]


class Meter(TimestampedModel):
    class UtilityType(models.TextChoices):
        ELECTRICITY = "ELECTRICITY", "Electricity"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="meters")
    meter_number = models.CharField(max_length=64)
    utility_type = models.CharField(
        max_length=16, choices=UtilityType.choices, default=UtilityType.ELECTRICITY
    )
    unit_of_measure = models.CharField(max_length=16, default="kWh")
    multiplier = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=1,
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(default=True)
    installed_at = models.DateField(null=True, blank=True)

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "meter_number"], name="unique_meter_number"
            ),
            models.CheckConstraint(check=Q(multiplier__gt=0), name="meter_multiplier_positive"),
        ]
        indexes = [models.Index(fields=["tenant", "unit"])]

    def __str__(self):
        return self.meter_number


def reading_proof_path(instance, filename):
    # The stored name never contains the uploader's filename: it is not needed,
    # and a user-chosen name in a storage path is an avoidable foot-gun.
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"meter-proofs/{instance.tenant_id}/{uuid.uuid4().hex}.{extension}"


class MeterReading(TimestampedModel):
    """
    One timestamped measurement. Values are never silently edited: a change is
    `MeterReadingService.correct`, which writes a `MeterReadingCorrection` with
    the original value, the corrected value, the reason and the actor.

    The optional `proof` image is evidence only — no OCR (plan §43.4). It is
    served through an authorized endpoint, never a public media URL.
    """

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual entry"
        IMPORT = "IMPORT", "Import"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    meter = models.ForeignKey(Meter, on_delete=models.PROTECT, related_name="readings")
    reading_date = models.DateField()
    reading_value = models.DecimalField(max_digits=14, decimal_places=3)
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.MANUAL
    )
    notes = models.CharField(max_length=500, blank=True)
    proof = models.FileField(upload_to=reading_proof_path, null=True, blank=True)
    proof_content_type = models.CharField(max_length=64, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["meter", "reading_date"], name="unique_reading_per_meter_day"
            ),
            models.CheckConstraint(
                check=Q(reading_value__gte=0), name="reading_value_non_negative"
            ),
        ]
        indexes = [models.Index(fields=["tenant", "meter", "reading_date"])]


class MeterReadingCorrection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    reading = models.ForeignKey(
        MeterReading, on_delete=models.PROTECT, related_name="corrections"
    )
    original_value = models.DecimalField(max_digits=14, decimal_places=3)
    corrected_value = models.DecimalField(max_digits=14, decimal_places=3)
    reason = models.CharField(max_length=500)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedManager()


class Tariff(TimestampedModel):
    """
    A per-unit utility rate with an effective date range. `rate_per_unit_cents`
    is in MINOR units per unit consumed (825.0000 = ₹8.25/kWh) with four decimal
    places, so fractional rates are exact until the one documented rounding.

    Applicable tariff for a billing period = the one effective on the period's
    last day. Ranges never overlap per (workspace, utility) — TariffService
    closes the previous open-ended tariff when a new one starts.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    utility_type = models.CharField(
        max_length=16,
        choices=Meter.UtilityType.choices,
        default=Meter.UtilityType.ELECTRICITY,
    )
    rate_per_unit_cents = models.DecimalField(max_digits=14, decimal_places=4)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "utility_type", "effective_from"],
                condition=Q(is_active=True),
                name="unique_tariff_start",
            ),
            models.CheckConstraint(
                check=Q(rate_per_unit_cents__gte=0), name="tariff_rate_non_negative"
            ),
        ]


class BillingCycle(TimestampedModel):
    """
    One calendar month of property billing for a workspace (plan §43.3). The
    cycle is the operational frame — progress and exceptions are computed from
    real rows (leases, readings, bills, payments), never stored counters.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.OPEN
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "period_start"], name="unique_cycle_per_month"
            )
        ]
        ordering = ["-period_start"]


class WorkspaceSequence(models.Model):
    """Gap-tolerant, collision-free per-workspace counters for document numbers
    (BILL-2026-000001, REC-2026-000183). Incremented under select_for_update."""

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=32)
    next_value = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="unique_workspace_sequence"
            )
        ]


class Bill(TimestampedModel):
    """
    What one resident owes the workspace owner for one unit and one month.

    Historical truth: the rent, readings, rate and totals shown for a bill come
    from its own line items and snapshot columns — never from the current lease,
    tariff, meter or resident. A published bill changes only through
    `BillCorrectionService` (an explicit, reasoned, audited adjustment line) or
    `PaymentService` (amount paid), and every total is derivable from its
    visible line items.

    OVERDUE is not stored: it is derived deterministically from `due_date`, the
    amount still due and the server's date (see apps.properties.aging), so it
    can never go stale.

    Duplicate protection is a partial unique constraint: one non-cancelled bill
    per (unit, resident, period_start).
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    cycle = models.ForeignKey(
        BillingCycle, on_delete=models.PROTECT, related_name="bills"
    )
    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="bills")
    resident = models.ForeignKey(
        Resident, on_delete=models.PROTECT, related_name="bills"
    )
    lease = models.ForeignKey(
        Lease, on_delete=models.PROTECT, null=True, blank=True, related_name="bills"
    )
    bill_number = models.CharField(max_length=32, blank=True)
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    currency = models.CharField(max_length=3)
    # Snapshots — the names as they were when the bill was generated.
    property_name = models.CharField(max_length=255)
    unit_identifier = models.CharField(max_length=50)
    resident_name = models.CharField(max_length=255)
    resident_email = models.EmailField()
    subtotal_cents = models.BigIntegerField(default=0)
    adjustments_cents = models.BigIntegerField(default=0)
    total_cents = models.BigIntegerField(default=0)
    amount_paid_cents = models.BigIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=500, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "resident", "period_start"],
                condition=~Q(status="CANCELLED"),
                name="unique_bill_per_unit_resident_period",
            ),
            models.UniqueConstraint(
                fields=["tenant", "bill_number"],
                condition=~Q(bill_number=""),
                name="unique_bill_number",
            ),
            models.CheckConstraint(
                check=Q(amount_paid_cents__gte=0), name="bill_paid_non_negative"
            ),
            models.CheckConstraint(
                check=Q(amount_paid_cents__lte=models.F("total_cents"))
                | Q(amount_paid_cents=0),
                name="bill_paid_not_above_total",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "period_start"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "due_date"]),
            models.Index(fields=["resident"]),
        ]

    # uiltins.property: this class body defines a property field, which
    # shadows the builtin decorator name from here down.
    @builtins.property
    def amount_due_cents(self):
        if self.status in (self.Status.DRAFT, self.Status.CANCELLED):
            return 0
        return max(self.total_cents - self.amount_paid_cents, 0)


class BillCorrection(models.Model):
    """
    An explicit, reasoned change to a PUBLISHED bill (plan §43.5). The original
    lines stay untouched; the correction adds one ADJUSTMENT line whose amount is
    `amount_delta_cents`, and this row records what was wrong, what it should
    have been, who decided, and why.
    """

    class Kind(models.TextChoices):
        AMOUNT_ADJUSTMENT = "AMOUNT_ADJUSTMENT", "Amount adjustment"
        READING_CORRECTION = "READING_CORRECTION", "Meter reading correction"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="corrections")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    reason = models.CharField(max_length=500)
    original_values = models.JSONField(default=dict)
    corrected_values = models.JSONField(default=dict)
    amount_delta_cents = models.BigIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedManager()


class BillLineItem(models.Model):
    """
    One visible component of a bill. Positive amounts are charges; DISCOUNT is
    stored negative; ADJUSTMENT is signed. Electricity lines carry the full
    calculation snapshot (readings, dates, multiplier, units, rate) so the
    amount is explainable forever without consulting the meter or tariff again.
    """

    class Type(models.TextChoices):
        RENT = "RENT", "Rent"
        ELECTRICITY = "ELECTRICITY", "Electricity"
        MAINTENANCE = "MAINTENANCE", "Maintenance"
        OTHER_CHARGE = "OTHER_CHARGE", "Other charge"
        DISCOUNT = "DISCOUNT", "Discount"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        LATE_FEE = "LATE_FEE", "Late fee"

    CHARGE_TYPES = frozenset({"RENT", "ELECTRICITY", "MAINTENANCE", "OTHER_CHARGE", "LATE_FEE"})
    ADJUSTMENT_TYPES = frozenset({"DISCOUNT", "ADJUSTMENT"})

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="line_items")
    type = models.CharField(max_length=16, choices=Type.choices)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    unit_price_cents = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True
    )
    amount_cents = models.BigIntegerField()
    # Electricity snapshot.
    meter = models.ForeignKey(
        Meter, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    meter_number = models.CharField(max_length=64, blank=True)
    opening_reading = models.ForeignKey(
        MeterReading, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    closing_reading = models.ForeignKey(
        MeterReading, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    opening_reading_value = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True
    )
    closing_reading_value = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True
    )
    opening_reading_date = models.DateField(null=True, blank=True)
    closing_reading_date = models.DateField(null=True, blank=True)
    multiplier = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    units_consumed = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True
    )
    tariff = models.ForeignKey(
        Tariff, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    correction = models.ForeignKey(
        BillCorrection,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="line_items",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]


class Payment(TimestampedModel):
    """
    Money a resident paid the workspace owner against one bill — recorded by the
    owner (offline methods are first-class). NOT a Tenora subscription payment,
    and never evidence of one.

    Duplicate protection: an optional client `idempotency_key` and an optional
    `reference`, each unique per workspace when present; the bill row is locked
    while the payment is applied, and an amount above what is due is refused.
    """

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
        UPI = "UPI", "UPI"
        CARD = "CARD", "Card"
        ONLINE = "ONLINE", "Online"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        VOIDED = "VOIDED", "Voided"

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="payments")
    resident = models.ForeignKey(
        Resident, on_delete=models.PROTECT, related_name="payments"
    )
    amount_cents = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    payment_date = models.DateField()
    method = models.CharField(max_length=16, choices=Method.choices)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.COMPLETED
    )
    reference = models.CharField(max_length=128, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    idempotency_key = models.CharField(max_length=64, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=500, blank=True)

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(amount_cents__gt=0), name="payment_amount_positive"),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="unique_payment_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=["tenant", "reference"],
                condition=~Q(reference=""),
                name="unique_payment_reference",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "payment_date"]),
            models.Index(fields=["bill"]),
        ]


class Receipt(models.Model):
    """
    Proof that one payment was recorded — one receipt per payment (the strategy
    plan §12 asks to choose and document). The number is allocated once, inside
    the payment's transaction, from a per-workspace sequence, and never changes;
    rendering a receipt reads these snapshot columns and recalculates nothing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="receipts")
    payment = models.OneToOneField(
        Payment, on_delete=models.PROTECT, related_name="receipt"
    )
    receipt_number = models.CharField(max_length=32)
    issued_at = models.DateTimeField()
    amount_cents = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    resident_name = models.CharField(max_length=255)
    unit_identifier = models.CharField(max_length=50)
    property_name = models.CharField(max_length=255)
    bill_number = models.CharField(max_length=32, blank=True)
    payment_method = models.CharField(max_length=16)

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "receipt_number"], name="unique_receipt_number"
            )
        ]
        indexes = [models.Index(fields=["tenant", "issued_at"])]


class OnlinePaymentAttempt(TimestampedModel):
    """
    One resident checkout of one bill through the property-payment gateway (P9).

    Transient provider state lives here, never on `Payment`: an attempt can be
    created, expire, fail, be retried, or capture money that can no longer be
    applied. Only a verified capture that still fits the bill turns into the
    canonical `Payment` (method ONLINE) + `Receipt`, via `PaymentService.record`,
    and this row points at it.

    Invariants enforced by the database, not by check-then-insert:
      * `provider_order_id` is unique      — one provider order <-> one attempt.
      * `idempotency_key` is unique        — the create-order retry key is stable.
      * one open (CREATED/ACTIVE) attempt per bill.
      * `provider_payment_id` unique when set — a provider payment settles once.
      * `payment` is one-to-one            — an attempt settles a bill at most once
        (and Payment.idempotency_key / reference add the same guard on that side).

    Status:
      CREATED      row written, provider order not confirmed yet (retry-safe)
      ACTIVE       provider order exists; resident can pay until expires_at
      SUCCEEDED    verified capture applied -> Payment + Receipt
      FAILED       the provider refused to create the order
      EXPIRED      not paid before expiry (or superseded); cannot settle
      UNAPPLIED    money captured but not applicable (bill already settled,
                   cancelled, changed, or amount/currency mismatch) -> refund
      REFUND_PENDING / REFUNDED   provider refund of an UNAPPLIED capture
    """

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        ACTIVE = "ACTIVE", "Awaiting payment"
        SUCCEEDED = "SUCCEEDED", "Paid"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"
        UNAPPLIED = "UNAPPLIED", "Needs refund"
        REFUND_PENDING = "REFUND_PENDING", "Refund pending"
        REFUNDED = "REFUNDED", "Refunded"

    OPEN_STATUSES = ("CREATED", "ACTIVE")

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="online_payment_attempts")
    resident = models.ForeignKey(Resident, on_delete=models.PROTECT, related_name="online_payment_attempts")
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    provider = models.CharField(max_length=20)
    provider_order_id = models.CharField(max_length=45, unique=True)
    provider_order_ref = models.CharField(max_length=64, blank=True)
    idempotency_key = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    payment_session_id = models.TextField(blank=True)
    amount_cents = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    expires_at = models.DateTimeField()
    provider_payment_id = models.CharField(max_length=64, blank=True)
    last_payment_status = models.CharField(max_length=20, blank=True)
    failure_message = models.CharField(max_length=255, blank=True)
    unapplied_reason = models.CharField(max_length=40, blank=True)
    payment = models.OneToOneField(
        Payment, on_delete=models.PROTECT, null=True, blank=True, related_name="online_attempt"
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    refund_id = models.CharField(max_length=40, blank=True)
    refund_status = models.CharField(max_length=20, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(amount_cents__gt=0), name="online_attempt_amount_positive"),
            models.UniqueConstraint(
                fields=["bill"],
                condition=Q(status__in=["CREATED", "ACTIVE"]),
                name="one_open_online_attempt_per_bill",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_payment_id"],
                condition=~Q(provider_payment_id=""),
                name="unique_online_provider_payment",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]


class PropertyPaymentWebhookEvent(models.Model):
    """
    A signature-verified property-payment webhook delivery (P9). Not tenant-owned:
    the provider calls with no tenant context; the attempt it names carries the
    tenant. `dedupe_key` (a digest of the verified raw body) is unique, so an
    at-least-once redelivery collides instead of being processed twice.

    `payload` is kept for support/audit and is never exposed to residents or
    workspace users.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=20)
    dedupe_key = models.CharField(max_length=64)
    event_type = models.CharField(max_length=64)
    provider_order_id = models.CharField(max_length=64, blank=True, db_index=True)
    provider_payment_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=40, blank=True)
    processing_error = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "dedupe_key"], name="unique_property_webhook_delivery")
        ]

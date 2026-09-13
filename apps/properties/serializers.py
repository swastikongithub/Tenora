"""
Property billing serializers.

Input serializers are plain `Serializer`s: they validate shape only, so a body
carrying `tenant`, `tenant_id`, `status`, `amount_paid_cents` or any other field
the service owns binds to nothing. Related objects arrive as ids and are
resolved by the VIEW through `.for_tenant(request.tenant)` — an id from another
workspace is a 404, never a cross-workspace write.

Output serializers render stored values only. A bill's money comes from its own
columns and line items; nothing here recomputes a charge from a lease, tariff or
meter. Overdue fields are derived from the server date passed in context.
"""

from decimal import Decimal

from rest_framework import serializers

from apps.properties import aging
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
    WorkspaceSettings,
)

MONEY_MAX = 10**13


# --- inputs ---------------------------------------------------------------


class PropertyInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    address_line_1 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country = serializers.RegexField(r"^[A-Z]{2}$", required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter a name.")
        return value


class UnitInputSerializer(serializers.Serializer):
    property_id = serializers.UUIDField()
    identifier = serializers.CharField(max_length=50)
    floor = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    unit_type = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")

    def validate_identifier(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter a unit identifier.")
        return value


class UnitUpdateSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=50, required=False)
    floor = serializers.CharField(max_length=20, required=False, allow_blank=True)
    unit_type = serializers.CharField(max_length=50, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Unit.Status.choices, required=False)


class ResidentUpdateSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=255, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    reference = serializers.CharField(max_length=50, required=False, allow_blank=True)


class LeaseInputSerializer(serializers.Serializer):
    unit_id = serializers.UUIDField()
    resident_id = serializers.UUIDField()
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True, default=None)
    monthly_rent_cents = serializers.IntegerField(min_value=0, max_value=MONEY_MAX)
    security_deposit_cents = serializers.IntegerField(
        min_value=0, max_value=MONEY_MAX, required=False, allow_null=True, default=None
    )


class LeaseUpdateSerializer(serializers.Serializer):
    monthly_rent_cents = serializers.IntegerField(min_value=0, max_value=MONEY_MAX, required=False)
    security_deposit_cents = serializers.IntegerField(
        min_value=0, max_value=MONEY_MAX, required=False, allow_null=True
    )


class LeaseEndSerializer(serializers.Serializer):
    end_date = serializers.DateField()


class MeterInputSerializer(serializers.Serializer):
    unit_id = serializers.UUIDField()
    meter_number = serializers.CharField(max_length=64)
    unit_of_measure = serializers.CharField(max_length=16, required=False, default="kWh")
    multiplier = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False, default=Decimal("1"), min_value=Decimal("0.0001")
    )
    installed_at = serializers.DateField(required=False, allow_null=True, default=None)


class MeterUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    multiplier = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False, min_value=Decimal("0.0001")
    )
    unit_of_measure = serializers.CharField(max_length=16, required=False)
    installed_at = serializers.DateField(required=False, allow_null=True)


class MeterReadingInputSerializer(serializers.Serializer):
    meter_id = serializers.UUIDField()
    reading_date = serializers.DateField()
    reading_value = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0"))
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    proof = serializers.FileField(required=False, allow_null=True, default=None)


class MeterReadingCorrectionInputSerializer(serializers.Serializer):
    corrected_value = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0"))
    reason = serializers.CharField(max_length=500)


class TariffInputSerializer(serializers.Serializer):
    rate_per_unit_cents = serializers.DecimalField(
        max_digits=14, decimal_places=4, min_value=Decimal("0")
    )
    effective_from = serializers.DateField()


class WorkspaceSettingsInputSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    receipt_footer = serializers.CharField(max_length=500, required=False, allow_blank=True)
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    due_days_after_period_end = serializers.IntegerField(min_value=0, max_value=90, required=False)
    default_maintenance_cents = serializers.IntegerField(min_value=0, max_value=MONEY_MAX, required=False)


class CycleOpenSerializer(serializers.Serializer):
    period = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$")


class CycleGenerateSerializer(serializers.Serializer):
    regenerate_drafts = serializers.BooleanField(required=False, default=False)


class LineItemInputSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=[(t, t) for t in ("MAINTENANCE", "OTHER_CHARGE", "DISCOUNT", "ADJUSTMENT", "LATE_FEE")]
    )
    description = serializers.CharField(max_length=255)
    amount_cents = serializers.IntegerField(min_value=-MONEY_MAX, max_value=MONEY_MAX)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class BillCorrectionInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=BillCorrection.Kind.choices)
    reason = serializers.CharField(max_length=500)
    amount_cents = serializers.IntegerField(min_value=-MONEY_MAX, max_value=MONEY_MAX, required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    line_item_id = serializers.UUIDField(required=False)
    corrected_closing_value = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0"), required=False
    )

    def validate(self, attrs):
        if attrs["kind"] == BillCorrection.Kind.AMOUNT_ADJUSTMENT and "amount_cents" not in attrs:
            raise serializers.ValidationError({"amount_cents": ["Enter the adjustment amount."]})
        if attrs["kind"] == BillCorrection.Kind.READING_CORRECTION and (
            "line_item_id" not in attrs or "corrected_closing_value" not in attrs
        ):
            raise serializers.ValidationError(
                {"corrected_closing_value": ["Choose the electricity line and the corrected reading."]}
            )
        return attrs


class PaymentInputSerializer(serializers.Serializer):
    bill_id = serializers.UUIDField()
    amount_cents = serializers.IntegerField(min_value=1, max_value=MONEY_MAX)
    payment_date = serializers.DateField()
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    reference = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


# --- outputs --------------------------------------------------------------


class WorkspaceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceSettings
        fields = [
            "display_name",
            "contact_email",
            "contact_phone",
            "address",
            "receipt_footer",
            "currency",
            "due_days_after_period_end",
            "default_maintenance_cents",
            "updated_at",
        ]


class PropertySerializer(serializers.ModelSerializer):
    unit_count = serializers.IntegerField(read_only=True, default=None)
    occupied_count = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "code",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country",
            "is_active",
            "unit_count",
            "occupied_count",
            "created_at",
        ]


class UnitSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source="property.name", read_only=True)

    class Meta:
        model = Unit
        fields = ["id", "property_id", "property_name", "identifier", "floor", "unit_type", "status", "created_at"]


class LeaseSerializer(serializers.ModelSerializer):
    unit_identifier = serializers.CharField(source="unit.identifier", read_only=True)
    property_id = serializers.UUIDField(source="unit.property_id", read_only=True)
    property_name = serializers.CharField(source="unit.property.name", read_only=True)
    resident_name = serializers.CharField(source="resident.display_name", read_only=True)

    class Meta:
        model = Lease
        fields = [
            "id",
            "unit_id",
            "unit_identifier",
            "property_id",
            "property_name",
            "resident_id",
            "resident_name",
            "start_date",
            "end_date",
            "monthly_rent_cents",
            "security_deposit_cents",
            "status",
            "created_at",
        ]


class ResidentSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    active_lease = serializers.SerializerMethodField()

    class Meta:
        model = Resident
        fields = ["id", "user_id", "email", "display_name", "phone", "reference", "status", "active_lease", "created_at"]

    def get_active_lease(self, obj):
        leases = getattr(obj, "active_leases", None)
        if leases is None:
            leases = [l for l in obj.leases.all() if l.status == Lease.Status.ACTIVE]
        return LeaseSerializer(leases[0]).data if leases else None


class MeterSerializer(serializers.ModelSerializer):
    unit_identifier = serializers.CharField(source="unit.identifier", read_only=True)
    property_name = serializers.CharField(source="unit.property.name", read_only=True)
    latest_reading = serializers.SerializerMethodField()

    class Meta:
        model = Meter
        fields = [
            "id",
            "unit_id",
            "unit_identifier",
            "property_name",
            "meter_number",
            "utility_type",
            "unit_of_measure",
            "multiplier",
            "is_active",
            "installed_at",
            "latest_reading",
            "created_at",
        ]

    def get_latest_reading(self, obj):
        reading = obj.readings.order_by("-reading_date").first()
        if reading is None:
            return None
        return {"reading_date": reading.reading_date, "reading_value": str(reading.reading_value)}


class MeterReadingCorrectionSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", default=None, read_only=True)

    class Meta:
        model = MeterReadingCorrection
        fields = ["id", "original_value", "corrected_value", "reason", "actor_email", "created_at"]


class MeterReadingSerializer(serializers.ModelSerializer):
    meter_number = serializers.CharField(source="meter.meter_number", read_only=True)
    unit_identifier = serializers.CharField(source="meter.unit.identifier", read_only=True)
    has_proof = serializers.SerializerMethodField()
    corrections = MeterReadingCorrectionSerializer(many=True, read_only=True)

    class Meta:
        model = MeterReading
        fields = [
            "id",
            "meter_id",
            "meter_number",
            "unit_identifier",
            "reading_date",
            "reading_value",
            "source",
            "notes",
            "has_proof",
            "proof_content_type",
            "corrections",
            "created_at",
        ]

    def get_has_proof(self, obj):
        return bool(obj.proof)


class TariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tariff
        fields = ["id", "utility_type", "rate_per_unit_cents", "effective_from", "effective_to", "is_active", "created_at"]


class BillingCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingCycle
        fields = ["id", "period_start", "period_end", "status", "closed_at", "created_at"]


class LineItemSerializer(serializers.ModelSerializer):
    opening_reading_id = serializers.UUIDField(read_only=True)
    closing_reading_id = serializers.UUIDField(read_only=True)
    opening_has_proof = serializers.SerializerMethodField()
    closing_has_proof = serializers.SerializerMethodField()
    rate_per_unit_cents = serializers.DecimalField(
        source="unit_price_cents", max_digits=14, decimal_places=4, read_only=True
    )

    class Meta:
        model = BillLineItem
        fields = [
            "id",
            "type",
            "description",
            "quantity",
            "unit_price_cents",
            "rate_per_unit_cents",
            "amount_cents",
            "meter_number",
            "opening_reading_id",
            "closing_reading_id",
            "opening_reading_value",
            "closing_reading_value",
            "opening_reading_date",
            "closing_reading_date",
            "multiplier",
            "units_consumed",
            "opening_has_proof",
            "closing_has_proof",
            "correction_id",
        ]

    def get_opening_has_proof(self, obj):
        return bool(obj.opening_reading and obj.opening_reading.proof)

    def get_closing_has_proof(self, obj):
        return bool(obj.closing_reading and obj.closing_reading.proof)


class PaymentSerializer(serializers.ModelSerializer):
    receipt_id = serializers.SerializerMethodField()
    receipt_number = serializers.SerializerMethodField()
    bill_number = serializers.CharField(source="bill.bill_number", read_only=True)
    resident_name = serializers.CharField(source="bill.resident_name", read_only=True)
    unit_identifier = serializers.CharField(source="bill.unit_identifier", read_only=True)
    period_start = serializers.DateField(source="bill.period_start", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "bill_id",
            "bill_number",
            "resident_name",
            "unit_identifier",
            "period_start",
            "amount_cents",
            "currency",
            "payment_date",
            "method",
            "status",
            "reference",
            "notes",
            "voided_at",
            "void_reason",
            "receipt_id",
            "receipt_number",
            "created_at",
        ]

    def _receipt(self, obj):
        try:
            return obj.receipt
        except Receipt.DoesNotExist:
            return None

    def get_receipt_id(self, obj):
        r = self._receipt(obj)
        return str(r.id) if r else None

    def get_receipt_number(self, obj):
        r = self._receipt(obj)
        return r.receipt_number if r else None


class ReceiptSerializer(serializers.ModelSerializer):
    payment_status = serializers.CharField(source="payment.status", read_only=True)
    payment_date = serializers.DateField(source="payment.payment_date", read_only=True)
    payment_reference = serializers.CharField(source="payment.reference", read_only=True)
    period_start = serializers.DateField(source="bill.period_start", read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "receipt_number",
            "issued_at",
            "amount_cents",
            "currency",
            "resident_name",
            "unit_identifier",
            "property_name",
            "bill_id",
            "bill_number",
            "payment_id",
            "payment_method",
            "payment_status",
            "payment_date",
            "payment_reference",
            "period_start",
        ]


class BillCorrectionSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", default=None, read_only=True)

    class Meta:
        model = BillCorrection
        fields = [
            "id",
            "kind",
            "reason",
            "original_values",
            "corrected_values",
            "amount_delta_cents",
            "actor_email",
            "created_at",
        ]


class BillSerializer(serializers.ModelSerializer):
    amount_due_cents = serializers.IntegerField(read_only=True)
    display_status = serializers.SerializerMethodField()
    overdue_days = serializers.SerializerMethodField()
    aging_bucket = serializers.SerializerMethodField()
    rent_cents = serializers.SerializerMethodField()
    electricity_cents = serializers.SerializerMethodField()
    electricity_units = serializers.SerializerMethodField()
    other_cents = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = [
            "id",
            "bill_number",
            "status",
            "display_status",
            "period_start",
            "period_end",
            "due_date",
            "currency",
            "property_id",
            "property_name",
            "unit_id",
            "unit_identifier",
            "resident_id",
            "resident_name",
            "subtotal_cents",
            "adjustments_cents",
            "total_cents",
            "amount_paid_cents",
            "amount_due_cents",
            "overdue_days",
            "aging_bucket",
            "rent_cents",
            "electricity_cents",
            "electricity_units",
            "other_cents",
            "published_at",
            "created_at",
        ]

    def _today(self):
        return self.context.get("today") or aging.server_today()

    def _lines(self, obj):
        return list(obj.line_items.all())

    def get_display_status(self, obj):
        return aging.display_status(obj, self._today())

    def get_overdue_days(self, obj):
        return aging.overdue_days(obj, self._today())

    def get_aging_bucket(self, obj):
        if not aging.is_open(obj):
            return None
        return aging.bucket_for_days(aging.overdue_days(obj, self._today()))

    def get_rent_cents(self, obj):
        return sum(l.amount_cents for l in self._lines(obj) if l.type == BillLineItem.Type.RENT)

    def get_electricity_cents(self, obj):
        return sum(l.amount_cents for l in self._lines(obj) if l.type == BillLineItem.Type.ELECTRICITY)

    def get_electricity_units(self, obj):
        return str(sum((l.quantity or 0) for l in self._lines(obj) if l.type == BillLineItem.Type.ELECTRICITY))

    def get_other_cents(self, obj):
        return sum(
            l.amount_cents
            for l in self._lines(obj)
            if l.type not in (BillLineItem.Type.RENT, BillLineItem.Type.ELECTRICITY)
        )


class BillDetailSerializer(BillSerializer):
    line_items = LineItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    receipts = serializers.SerializerMethodField()
    corrections = BillCorrectionSerializer(many=True, read_only=True)

    class Meta(BillSerializer.Meta):
        fields = BillSerializer.Meta.fields + [
            "cycle_id",
            "lease_id",
            "resident_email",
            "cancelled_at",
            "cancellation_reason",
            "line_items",
            "payments",
            "receipts",
            "corrections",
        ]

    def get_receipts(self, obj):
        return ReceiptSerializer(obj.receipts.select_related("payment", "bill").order_by("issued_at"), many=True).data

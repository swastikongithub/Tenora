from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from apps.properties import calculations
from apps.properties.models import Bill, BillLineItem, Receipt
from apps.properties.services import (
    BillCorrectionService,
    BillingCycleService,
    BillService,
    DomainError,
    LeaseService,
    TariffService,
)
from apps.properties.tests.factories import Scenario


class CalculationTests(SimpleTestCase):
    def test_plan_example_integer_readings(self):
        units = calculations.billed_units(Decimal("12450"), Decimal("12610"))
        self.assertEqual(units, Decimal("160.000"))
        self.assertEqual(calculations.charge_cents(units, Decimal("800")), 128000)

    def test_plan_example_decimal_readings_and_rate(self):
        units = calculations.billed_units("12000.5", "12150.5")
        self.assertEqual(units, Decimal("150.000"))
        self.assertEqual(calculations.charge_cents(units, Decimal("825")), 123750)  # ₹1,237.50

    def test_multiplier_applies_before_rounding_to_three_places(self):
        self.assertEqual(calculations.billed_units("100.001", "100.004", "2.5"), Decimal("0.008"))  # 0.0075 half-up

    def test_minor_unit_rounding_is_half_up(self):
        self.assertEqual(calculations.charge_cents(Decimal("0.500"), Decimal("1")), 1)
        self.assertEqual(calculations.charge_cents(Decimal("1.499"), Decimal("1")), 1)

    def test_zero_usage(self):
        self.assertEqual(calculations.charge_cents(calculations.billed_units(5, 5), Decimal("800")), 0)

    def test_negative_consumption_is_refused(self):
        with self.assertRaises(calculations.NegativeConsumption):
            calculations.billed_units(10, 9)


class BillGenerationTests(TestCase):
    def lines(self, bill):
        return {l.type: l for l in bill.line_items.all()}

    def test_rent_electricity_and_maintenance_totals_13780(self):
        s = Scenario()
        bill = s.march_bill()
        lines = self.lines(bill)
        self.assertEqual(lines["RENT"].amount_cents, 1_200_000)
        elec = lines["ELECTRICITY"]
        self.assertEqual(elec.amount_cents, 128_000)
        self.assertEqual(elec.opening_reading_value, Decimal("12450"))
        self.assertEqual(elec.closing_reading_value, Decimal("12610"))
        self.assertEqual(elec.quantity, Decimal("160"))
        self.assertEqual(elec.unit_price_cents, Decimal("800"))
        self.assertEqual(lines["MAINTENANCE"].amount_cents, 50_000)
        self.assertEqual(bill.total_cents, 1_378_000)
        self.assertEqual(bill.status, Bill.Status.PUBLISHED)
        self.assertTrue(bill.bill_number.startswith("BILL-2026-"))
        self.assertEqual(bill.currency, "INR")

    def test_rent_only_when_unit_has_no_meter(self):
        s = Scenario(maintenance=0)
        s.meter.is_active = False
        s.meter.save()
        created, _ = BillingCycleService.generate(actor=s.owner, cycle=s.cycle())
        self.assertEqual(set(self.lines(created[0])), {"RENT"})
        self.assertEqual(created[0].total_cents, 1_200_000)

    def test_electricity_only_when_rent_is_zero(self):
        s = Scenario(rent=0, maintenance=0)
        bill = s.march_bill(publish=False)
        self.assertEqual(set(self.lines(bill)), {"ELECTRICITY"})
        self.assertEqual(bill.total_cents, 128_000)

    def test_zero_usage_bills_zero_electricity(self):
        s = Scenario(maintenance=0)
        s.reading(date(2026, 2, 28), "500")
        s.reading(date(2026, 3, 31), "500")
        created, _ = BillingCycleService.generate(actor=s.owner, cycle=s.cycle())
        self.assertEqual(self.lines(created[0])["ELECTRICITY"].amount_cents, 0)

    def test_decimal_readings(self):
        s = Scenario(rate="825", maintenance=0, rent=0)
        s.reading(date(2026, 2, 28), "12000.5")
        s.reading(date(2026, 3, 31), "12150.5")
        created, _ = BillingCycleService.generate(actor=s.owner, cycle=s.cycle())
        self.assertEqual(created[0].total_cents, 123_750)

    def test_discount_and_adjustment_on_draft(self):
        s = Scenario()
        bill = s.march_bill(publish=False)
        BillService.add_line_item(actor=s.owner, bill=bill, type="DISCOUNT", description="Loyalty", amount_cents=10_000)
        BillService.add_line_item(actor=s.owner, bill=bill, type="ADJUSTMENT", description="Credit", amount_cents=-5_000)
        BillService.add_line_item(actor=s.owner, bill=bill, type="OTHER_CHARGE", description="Parking", amount_cents=20_000)
        bill.refresh_from_db()
        self.assertEqual(bill.subtotal_cents, 1_378_000 + 20_000)
        self.assertEqual(bill.adjustments_cents, -15_000)
        self.assertEqual(bill.total_cents, 1_383_000)
        self.assertEqual(
            bill.total_cents, sum(l.amount_cents for l in bill.line_items.all())
        )

    def test_discount_cannot_exceed_charges(self):
        s = Scenario()
        bill = s.march_bill(publish=False)
        with self.assertRaises(DomainError) as ctx:
            BillService.add_line_item(actor=s.owner, bill=bill, type="DISCOUNT", description="x", amount_cents=99_999_999)
        self.assertEqual(ctx.exception.code, "NEGATIVE_TOTAL")

    def test_missing_reading_is_an_exception_not_a_bill(self):
        s = Scenario()
        cycle = s.cycle()
        created, skipped = BillingCycleService.generate(actor=s.owner, cycle=cycle)
        self.assertEqual(created, [])
        self.assertEqual(skipped[0]["code"], "MISSING_READING")
        codes = {e["code"] for e in BillingCycleService.progress(cycle)["exceptions"]}
        self.assertIn("MISSING_READING", codes)

    def test_missing_tariff_is_an_exception(self):
        s = Scenario(rate=None)
        s.reading(date(2026, 2, 28), "1")
        s.reading(date(2026, 3, 31), "2")
        _, skipped = BillingCycleService.generate(actor=s.owner, cycle=s.cycle())
        self.assertEqual(skipped[0]["code"], "MISSING_TARIFF")

    def test_first_month_uses_earliest_in_period_reading_as_opening(self):
        s = Scenario(maintenance=0, rent=0)
        s.reading(date(2026, 3, 1), "100")
        s.reading(date(2026, 3, 31), "110")
        created, _ = BillingCycleService.generate(actor=s.owner, cycle=s.cycle())
        self.assertEqual(created[0].total_cents, 8_000)


class DuplicateAndPublicationTests(TestCase):
    def test_second_generation_skips_existing_bill(self):
        s = Scenario()
        s.march_bill(publish=False)
        created, skipped = BillingCycleService.generate(actor=s.owner, cycle=s.cycle())
        self.assertEqual(created, [])
        self.assertEqual(skipped[0]["code"], "BILL_EXISTS")
        self.assertEqual(Bill.objects.filter(tenant=s.tenant).count(), 1)

    def test_database_constraint_rejects_a_duplicate_monthly_bill(self):
        s = Scenario()
        bill = s.march_bill(publish=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Bill.objects.create(
                tenant=s.tenant, cycle=bill.cycle, property=s.property, unit=s.unit, resident=s.resident,
                period_start=bill.period_start, period_end=bill.period_end, due_date=bill.due_date,
                currency="INR", property_name="x", unit_identifier="x", resident_name="x", resident_email="x@x.io",
            )

    def test_regenerate_replaces_only_drafts(self):
        s = Scenario()
        draft = s.march_bill(publish=False)
        created, _ = BillingCycleService.generate(actor=s.owner, cycle=s.cycle(), regenerate_drafts=True)
        self.assertEqual(len(created), 1)
        self.assertFalse(Bill.objects.filter(pk=draft.pk).exists())

    def test_publishing_twice_is_a_noop(self):
        s = Scenario()
        bill = s.march_bill()
        again = BillService.publish(actor=s.owner, bill=bill)
        self.assertEqual(again.bill_number, bill.bill_number)
        self.assertEqual(again.published_at, bill.published_at)

    def test_published_bill_cannot_be_edited(self):
        s = Scenario()
        bill = s.march_bill()
        with self.assertRaises(DomainError) as ctx:
            BillService.add_line_item(actor=s.owner, bill=bill, type="OTHER_CHARGE", description="x", amount_cents=1)
        self.assertEqual(ctx.exception.code, "BILL_NOT_DRAFT")
        line = bill.line_items.first()
        with self.assertRaises(DomainError):
            BillService.remove_line_item(actor=s.owner, bill=bill, line_item_id=line.id)

    def test_cancel_unpaid_published_bill_then_regenerate(self):
        s = Scenario()
        bill = s.march_bill()
        BillService.cancel(actor=s.owner, bill=bill, reason="Wrong unit")
        bill.refresh_from_db()
        self.assertEqual(bill.status, Bill.Status.CANCELLED)
        created, _ = BillingCycleService.generate(actor=s.owner, cycle=s.cycle())
        self.assertEqual(len(created), 1)

    def test_cannot_cancel_bill_with_payments(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 1000)
        with self.assertRaises(DomainError) as ctx:
            BillService.cancel(actor=s.owner, bill=bill, reason="x")
        self.assertEqual(ctx.exception.code, "BILL_HAS_PAYMENTS")

    def test_close_cycle_requires_no_drafts(self):
        s = Scenario()
        bill = s.march_bill(publish=False)
        with self.assertRaises(DomainError):
            BillingCycleService.close(actor=s.owner, cycle=bill.cycle)
        BillingCycleService.publish_all(actor=s.owner, cycle=bill.cycle)
        self.assertEqual(BillingCycleService.close(actor=s.owner, cycle=bill.cycle).status, "CLOSED")


class HistoricalSnapshotTests(TestCase):
    def test_rent_and_tariff_changes_do_not_rewrite_march(self):
        s = Scenario()
        march = s.march_bill()
        LeaseService.update(actor=s.owner, lease=s.lease, changes={"monthly_rent_cents": 1_300_000})
        TariffService.create(actor=s.owner, tenant=s.tenant, rate_per_unit_cents=Decimal("1000"), effective_from=date(2026, 4, 1))
        s.reading(date(2026, 4, 30), "12710")
        april_cycle = s.cycle(2026, 4)
        created, skipped = BillingCycleService.generate(actor=s.owner, cycle=april_cycle)
        april = created[0]

        march.refresh_from_db()
        m_lines = {l.type: l for l in march.line_items.all()}
        self.assertEqual(m_lines["RENT"].amount_cents, 1_200_000)
        self.assertEqual(m_lines["ELECTRICITY"].unit_price_cents, Decimal("800"))
        self.assertEqual(march.total_cents, 1_378_000)

        a_lines = {l.type: l for l in april.line_items.all()}
        self.assertEqual(a_lines["RENT"].amount_cents, 1_300_000)
        self.assertEqual(a_lines["ELECTRICITY"].unit_price_cents, Decimal("1000"))
        self.assertEqual(a_lines["ELECTRICITY"].amount_cents, 100_000)  # 100 units × ₹10
        self.assertEqual(a_lines["ELECTRICITY"].opening_reading_value, Decimal("12610"))

    def test_resident_name_snapshot_survives_profile_change(self):
        s = Scenario()
        bill = s.march_bill()
        s.resident.display_name = "Someone Else"
        s.resident.save()
        bill.refresh_from_db()
        self.assertNotEqual(bill.resident_name, "Someone Else")

    def test_tariff_must_start_after_current_and_closes_previous(self):
        s = Scenario()
        with self.assertRaises(DomainError):
            TariffService.create(actor=s.owner, tenant=s.tenant, rate_per_unit_cents=Decimal("900"), effective_from=date(2026, 1, 1))
        TariffService.create(actor=s.owner, tenant=s.tenant, rate_per_unit_cents=Decimal("900"), effective_from=date(2026, 6, 1))
        s.tariff.refresh_from_db()
        self.assertEqual(s.tariff.effective_to, date(2026, 5, 31))
        self.assertEqual(TariffService.applicable(s.tenant, date(2026, 5, 31)).rate_per_unit_cents, Decimal("800"))
        self.assertEqual(TariffService.applicable(s.tenant, date(2026, 6, 1)).rate_per_unit_cents, Decimal("900"))


class CorrectionTests(TestCase):
    def test_amount_adjustment_keeps_original_lines_and_records_reason(self):
        s = Scenario()
        bill = s.march_bill()
        original = list(bill.line_items.values_list("id", "amount_cents"))
        correction = BillCorrectionService.adjust_amount(actor=s.owner, bill=bill, amount_delta_cents=-8_000, reason="Goodwill")
        bill.refresh_from_db()
        self.assertEqual(bill.total_cents, 1_370_000)
        for line_id, amount in original:
            self.assertEqual(BillLineItem.objects.get(pk=line_id).amount_cents, amount)
        self.assertEqual(correction.original_values["total_cents"], 1_378_000)
        self.assertEqual(correction.actor, s.owner)
        self.assertEqual(bill.line_items.get(correction=correction).amount_cents, -8_000)

    def test_reading_correction_adds_delta_line(self):
        s = Scenario()
        bill = s.march_bill()
        elec = bill.line_items.get(type="ELECTRICITY")
        correction = BillCorrectionService.correct_reading(
            actor=s.owner, bill=bill, line_item_id=elec.id, corrected_closing_value=Decimal("12560"), reason="Misread"
        )
        bill.refresh_from_db()
        self.assertEqual(correction.amount_delta_cents, -40_000)  # 110 units instead of 160
        self.assertEqual(bill.total_cents, 1_338_000)
        elec.refresh_from_db()
        self.assertEqual(elec.closing_reading_value, Decimal("12610"))  # original preserved
        # A second correction is relative to the first, not the original.
        second = BillCorrectionService.correct_reading(
            actor=s.owner, bill=bill, line_item_id=elec.id, corrected_closing_value=Decimal("12570"), reason="Again"
        )
        self.assertEqual(second.amount_delta_cents, 8_000)

    def test_correction_cannot_go_below_amount_paid(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 1_378_000)
        with self.assertRaises(DomainError) as ctx:
            BillCorrectionService.adjust_amount(actor=s.owner, bill=bill, amount_delta_cents=-1, reason="x")
        self.assertEqual(ctx.exception.code, "CORRECTION_BELOW_PAID")

    def test_upward_correction_on_paid_bill_reopens_it(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 1_378_000)
        BillCorrectionService.adjust_amount(actor=s.owner, bill=bill, amount_delta_cents=5_000, reason="Missed charge")
        bill.refresh_from_db()
        self.assertEqual(bill.status, Bill.Status.PARTIALLY_PAID)
        self.assertEqual(Receipt.objects.filter(bill=bill).count(), 1)

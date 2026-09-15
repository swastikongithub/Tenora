"""Owner and platform reports (plan §16): monthly billed / collected by charge
type, electricity by unit, all derived from issued bills and payments."""

from datetime import date
from unittest import mock

from rest_framework.test import APITestCase

from apps.properties.services import BillingCycleService, BillService
from apps.properties.tests.factories import Scenario, bearer, make_user

TODAY = date(2026, 5, 15)


def april_bill(s):
    s.reading(date(2026, 4, 30), "12700")  # 90 units x INR 8
    cycle = s.cycle(month=4)
    created, _ = BillingCycleService.generate(actor=s.owner, cycle=cycle)
    return BillService.publish(actor=s.owner, bill=created[0])


class OwnerReportTests(APITestCase):
    def setUp(self):
        self.s = Scenario()
        self.march = self.s.march_bill()  # 12,000 rent + 1,280 electricity + 500 maintenance
        self.s.pay(self.march, 1_378_000)  # PAID
        self.april = april_bill(self.s)  # 12,000 + 720 + 500 = 13,220
        self.s.pay(self.april, 500_000)  # partly paid

    def report(self, user=None, period="2026-03"):
        bearer(self.client, user or self.s.owner, self.s.tenant)
        with mock.patch("apps.properties.aging.server_today", return_value=TODAY):
            return self.client.get("/api/billing/reports/", {"months": "3", "period": period})

    def test_collected_is_split_by_type_only_for_paid_bills(self):
        resp = self.report()
        self.assertEqual(resp.status_code, 200)
        rows = {r["period"]: r for r in resp.data["monthly"]}
        self.assertEqual(set(rows), {"2026-03", "2026-04", "2026-05"})

        march = rows["2026-03"]
        self.assertEqual(
            (march["rent_collected_cents"], march["electricity_collected_cents"], march["other_collected_cents"]),
            (1_200_000, 128_000, 50_000),
        )
        self.assertEqual(march["collected_unallocated_cents"], 0)

        april = rows["2026-04"]
        self.assertEqual(april["billed_cents"], 1_322_000)
        self.assertEqual(april["rent_billed_cents"], 1_200_000)
        self.assertEqual(april["collected_cents"], 500_000)
        self.assertEqual(
            (april["rent_collected_cents"], april["electricity_collected_cents"], april["other_collected_cents"]),
            (0, 0, 0),
        )
        self.assertEqual(april["collected_unallocated_cents"], 500_000)

    def test_collected_parts_always_add_up(self):
        for row in self.report().data["monthly"]:
            with self.subTest(period=row["period"]):
                parts = (
                    row["rent_collected_cents"]
                    + row["electricity_collected_cents"]
                    + row["other_collected_cents"]
                    + row["collected_unallocated_cents"]
                )
                self.assertEqual(parts, row["collected_cents"])

    def test_adjustments_on_a_paid_bill_stay_reconciled(self):
        from apps.properties.services import BillCorrectionService

        s = Scenario(slug="adjusted")
        bill = s.march_bill()
        BillCorrectionService.adjust_amount(actor=s.owner, bill=bill, amount_delta_cents=-50_000, reason="Waived")
        bill.refresh_from_db()
        s.pay(bill, bill.total_cents)
        bearer(self.client, s.owner, s.tenant)
        with mock.patch("apps.properties.aging.server_today", return_value=TODAY):
            march = self.client.get("/api/billing/reports/", {"months": "3"}).data["monthly"][0]
        self.assertEqual(march["collected_cents"], 1_328_000)
        self.assertEqual(march["other_collected_cents"], 0)  # +500 maintenance, -500 waiver
        self.assertEqual(march["rent_collected_cents"] + march["electricity_collected_cents"], 1_328_000)

    def test_electricity_by_unit_and_month(self):
        march = self.report(period="2026-03").data
        [unit] = march["electricity_by_unit"]
        self.assertEqual((unit["unit_identifier"], unit["units"], unit["amount_cents"]), ("203", "160.000", 128_000))
        rows = {r["period"]: r for r in march["monthly"]}
        self.assertEqual((rows["2026-03"]["electricity_units"], rows["2026-04"]["electricity_units"]), ("160.000", "90.000"))

    def test_residents_cannot_read_reports(self):
        self.assertEqual(self.report(user=self.s.user).status_code, 403)


class PlatformReportTests(APITestCase):
    def setUp(self):
        self.a = Scenario(slug="sunrise")
        self.b = Scenario(slug="green-valley")
        self.a.pay(self.a.march_bill(), 1_378_000)
        self.b.march_bill()
        self.staff = make_user("staff@example.com", is_staff=True)

    def summary(self, **params):
        bearer(self.client, self.staff)
        with mock.patch("apps.properties.aging.server_today", return_value=TODAY):
            return self.client.get("/api/platform/property-billing/summary/", {"period": "2026-03", **params}).data

    def test_same_metrics_globally(self):
        data = self.summary()
        march = next(r for r in data["monthly"] if r["period"] == "2026-03")
        self.assertEqual(march["billed_cents"], 2 * 1_378_000)
        self.assertEqual(march["rent_collected_cents"], 1_200_000)
        self.assertEqual(march["collected_unallocated_cents"], 0)
        # Two workspaces each have a "Building A / 203": two separate rows.
        self.assertEqual(len(data["electricity_by_unit"]), 2)
        self.assertEqual(
            {r["tenant_name"] for r in data["electricity_by_unit"]}, {self.a.tenant.name, self.b.tenant.name}
        )

    def test_filterable_by_workspace(self):
        data = self.summary(tenant=str(self.b.tenant.id))
        march = next(r for r in data["monthly"] if r["period"] == "2026-03")
        self.assertEqual((march["billed_cents"], march["collected_cents"]), (1_378_000, 0))
        self.assertEqual([r["tenant_name"] for r in data["electricity_by_unit"]], [self.b.tenant.name])

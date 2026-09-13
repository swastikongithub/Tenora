"""
Property billing isolation, attacked through the real API with real JWTs (so
TenantJWTAuthentication runs): workspace A vs workspace B, and resident A vs
resident B inside one workspace. Every foreign id must be a 404 — indistinguishable
from an id that does not exist — never a 403 or a 200.
"""

import uuid
from datetime import date

from rest_framework.test import APITestCase

from apps.properties.models import Bill, Payment, Property
from apps.properties.services import BillingCycleService, BillService, LeaseService, UnitService
from apps.properties.tests.factories import Scenario, add_resident, bearer


class WorkspaceIsolationTests(APITestCase):
    def setUp(self):
        self.a = Scenario(slug="sunrise")
        self.b = Scenario(slug="green-valley")
        self.bill_a = self.a.march_bill()
        self.bill_b = self.b.march_bill()
        self.payment_b, _ = self.b.pay(self.bill_b, 1000)
        self.receipt_b = self.payment_b.receipt

    def test_owner_a_cannot_read_workspace_b_objects(self):
        bearer(self.client, self.a.owner, self.a.tenant)
        for url in (
            f"/api/properties/{self.b.property.id}/",
            f"/api/units/{self.b.unit.id}/",
            f"/api/residents/{self.b.resident.id}/",
            f"/api/leases/{self.b.lease.id}/",
            f"/api/meters/{self.b.meter.id}/",
            f"/api/bills/{self.bill_b.id}/",
            f"/api/payments/{self.payment_b.id}/",
            f"/api/receipts/{self.receipt_b.id}/",
            f"/api/billing/cycles/{self.bill_b.cycle_id}/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        missing = self.client.get(f"/api/bills/{uuid.uuid4()}/")
        self.assertEqual(missing.status_code, 404)

    def test_owner_a_lists_contain_only_workspace_a(self):
        bearer(self.client, self.a.owner, self.a.tenant)
        bills = self.client.get("/api/bills/").data["results"]
        self.assertEqual({b["id"] for b in bills}, {str(self.bill_a.id)})
        self.assertEqual(self.client.get("/api/payments/").data["count"], 0)
        self.assertEqual({p["id"] for p in self.client.get("/api/properties/").data}, {str(self.a.property.id)})

    def test_owner_a_cannot_mutate_workspace_b(self):
        bearer(self.client, self.a.owner, self.a.tenant)
        attempts = [
            ("patch", f"/api/properties/{self.b.property.id}/", {"name": "hijack"}),
            ("post", f"/api/bills/{self.bill_b.id}/cancel/", {"reason": "x"}),
            ("post", f"/api/bills/{self.bill_b.id}/corrections/", {"kind": "AMOUNT_ADJUSTMENT", "amount_cents": -1, "reason": "x"}),
            ("post", "/api/payments/", {"bill_id": str(self.bill_b.id), "amount_cents": 1, "payment_date": "2026-04-01", "method": "CASH"}),
            ("post", f"/api/payments/{self.payment_b.id}/void/", {"reason": "x"}),
            ("post", "/api/units/", {"property_id": str(self.b.property.id), "identifier": "X"}),
            ("post", "/api/leases/", {"unit_id": str(self.b.unit.id), "resident_id": str(self.b.resident.id), "start_date": "2027-01-01", "monthly_rent_cents": 1}),
            ("post", "/api/meter-readings/", {"meter_id": str(self.b.meter.id), "reading_date": "2026-04-01", "reading_value": "99999"}),
        ]
        for method, url, body in attempts:
            with self.subTest(url=url):
                resp = getattr(self.client, method)(url, body, format="json")
                self.assertEqual(resp.status_code, 404, resp.data)
        self.b.property.refresh_from_db()
        self.assertNotEqual(self.b.property.name, "hijack")
        self.assertEqual(Payment.objects.filter(bill=self.bill_b).count(), 1)

    def test_tenant_in_body_cannot_redirect_writes(self):
        bearer(self.client, self.a.owner, self.a.tenant)
        resp = self.client.post(
            "/api/properties/", {"name": "Mine", "tenant": str(self.b.tenant.id), "tenant_id": str(self.b.tenant.id)}, format="json"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Property.objects.get(pk=resp.data["id"]).tenant, self.a.tenant)

    def test_header_for_foreign_workspace_is_403(self):
        bearer(self.client, self.a.owner, self.b.tenant)
        self.assertEqual(self.client.get("/api/bills/").status_code, 403)


class ResidentIsolationTests(APITestCase):
    def setUp(self):
        self.s = Scenario()
        self.bill_rahul = self.s.march_bill()
        self.unit2 = UnitService.create(actor=self.s.owner, tenant=self.s.tenant, prop=self.s.property, identifier="104")
        self.aman, self.aman_res = add_resident(self.s.tenant, self.s.owner, "aman@example.com")
        LeaseService.create(
            actor=self.s.owner, tenant=self.s.tenant, unit=self.unit2, resident=self.aman_res,
            start_date=date(2026, 1, 1), monthly_rent_cents=900_000,
        )
        created, _ = BillingCycleService.generate(actor=self.s.owner, cycle=self.s.cycle())
        self.bill_aman = created[0]  # rent only — no meter on 104
        self.payment_aman, _ = self.s.pay(BillService.publish(actor=self.s.owner, bill=self.bill_aman), 1000)

    def test_resident_sees_only_own_bills(self):
        bearer(self.client, self.s.user, self.s.tenant)
        bills = self.client.get("/api/bills/").data["results"]
        self.assertEqual([b["id"] for b in bills], [str(self.bill_rahul.id)])
        self.assertEqual(self.client.get(f"/api/bills/{self.bill_aman.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/payments/{self.payment_aman.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/receipts/{self.payment_aman.receipt.id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/receipts/").data["count"], 0)

    def test_resident_filter_param_cannot_widen_scope(self):
        bearer(self.client, self.s.user, self.s.tenant)
        resp = self.client.get(f"/api/bills/?resident={self.aman_res.id}")
        self.assertEqual(resp.data["count"], 0)

    def test_resident_does_not_see_drafts(self):
        draft_cycle = self.s.cycle(2026, 4)
        self.s.reading(date(2026, 4, 30), "12700")
        BillingCycleService.generate(actor=self.s.owner, cycle=draft_cycle)
        bearer(self.client, self.s.user, self.s.tenant)
        statuses = {b["status"] for b in self.client.get("/api/bills/").data["results"]}
        self.assertNotIn(Bill.Status.DRAFT, statuses)

    def test_resident_cannot_use_owner_endpoints(self):
        bearer(self.client, self.s.user, self.s.tenant)
        for method, url in (
            ("get", "/api/properties/"),
            ("get", "/api/residents/"),
            ("get", "/api/billing/aging/"),
            ("get", "/api/billing/summary/"),
            ("get", "/api/workspace/settings/"),
            ("get", "/api/workspace/overview/"),
            ("get", "/api/invitations/"),
            ("get", "/api/subscriptions/current/"),
            ("post", f"/api/bills/{self.bill_rahul.id}/publish/"),
            ("post", "/api/payments/"),
        ):
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, method)(url, {}, format="json").status_code, 403)

    def test_resident_bill_detail_is_explainable(self):
        bearer(self.client, self.s.user, self.s.tenant)
        data = self.client.get(f"/api/bills/{self.bill_rahul.id}/").data
        elec = next(l for l in data["line_items"] if l["type"] == "ELECTRICITY")
        self.assertEqual(elec["opening_reading_value"], "12450.000")
        self.assertEqual(elec["closing_reading_value"], "12610.000")
        self.assertEqual(elec["rate_per_unit_cents"], "800.0000")
        self.assertEqual(data["total_cents"], 1_378_000)
        residency = self.client.get("/api/residency/").data
        self.assertEqual(residency["lease"]["unit_identifier"], "203")

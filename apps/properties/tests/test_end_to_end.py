"""
The plan's §39 scenario, driven entirely through the HTTP API with real JWTs:
owner sets up Sunrise, invites Rahul (who accepts), leases unit 203 at ₹12,000,
records meter readings, sets ₹8/unit, bills March (₹13,780), publishes, Rahul
sees it, the owner records a UPI payment, a receipt is issued, April rent rises
to ₹13,000 without touching March, and a second workspace stays isolated while
the platform admin sees both.
"""

from types import SimpleNamespace

from rest_framework.test import APITestCase

from apps.properties.tests.factories import bearer, make_user
from apps.users.models import User


class SunriseScenarioTests(APITestCase):
    def post(self, url, body=None, expect=201):
        resp = self.client.post(url, body or {}, format="json")
        self.assertEqual(resp.status_code, expect, (url, resp.data))
        return resp.data

    def test_full_lifecycle(self):
        owner = make_user("owner@sunrise.test")
        rahul = make_user("rahul@example.com", first_name="Rahul", last_name="Sharma")

        bearer(self.client, owner)
        tenant = self.post("/api/tenants/", {"name": "Sunrise Apartments", "slug": "sunrise"})
        bearer(self.client, owner, SimpleNamespace(id=tenant["id"]))
        self.client.patch("/api/workspace/settings/", {"default_maintenance_cents": 50000}, format="json")
        prop = self.post("/api/properties/", {"name": "Sunrise Apartments Building A"})
        unit = self.post("/api/units/", {"property_id": prop["id"], "identifier": "203"})
        invitation = self.post("/api/invitations/", {"email": "rahul@example.com", "unit_id": unit["id"]})

        bearer(self.client, rahul)
        self.post("/api/invitations/respond/", {"id": invitation["id"], "action": "accept"}, expect=200)

        bearer(self.client, owner, SimpleNamespace(id=tenant["id"]))
        resident = self.client.get("/api/residents/").data[0]
        self.assertEqual(resident["display_name"], "Rahul Sharma")
        lease = self.post(
            "/api/leases/",
            {"unit_id": unit["id"], "resident_id": resident["id"], "start_date": "2026-01-01", "monthly_rent_cents": 1200000},
        )
        meter = self.post("/api/meters/", {"unit_id": unit["id"], "meter_number": "ELEC-203"})
        self.post("/api/meter-readings/", {"meter_id": meter["id"], "reading_date": "2026-02-28", "reading_value": "12450"})
        self.post("/api/meter-readings/", {"meter_id": meter["id"], "reading_date": "2026-03-31", "reading_value": "12610"})
        self.post("/api/billing/tariffs/", {"rate_per_unit_cents": "800", "effective_from": "2026-01-01"})
        cycle = self.post("/api/billing/cycles/", {"period": "2026-03"})
        progress = self.client.get(f"/api/billing/cycles/{cycle['id']}/").data["progress"]
        self.assertEqual((progress["readings_entered"], progress["meters_expected"]), (1, 1))
        generated = self.post(f"/api/billing/cycles/{cycle['id']}/generate/", expect=200)
        self.assertEqual(generated["created"], 1)
        published = self.post(f"/api/billing/cycles/{cycle['id']}/publish/", expect=200)
        self.assertEqual(published["published"], 1)

        bills = self.client.get("/api/bills/?period=2026-03").data["results"]
        self.assertEqual(len(bills), 1)
        march = bills[0]
        self.assertEqual(
            (march["rent_cents"], march["electricity_cents"], march["other_cents"], march["total_cents"]),
            (1200000, 128000, 50000, 1378000),
        )

        bearer(self.client, rahul, SimpleNamespace(id=tenant["id"]))
        mine = self.client.get(f"/api/bills/{march['id']}/")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.data["total_cents"], 1378000)

        bearer(self.client, owner, SimpleNamespace(id=tenant["id"]))
        payment = self.post(
            "/api/payments/",
            {"bill_id": march["id"], "amount_cents": 1378000, "payment_date": "2026-04-05", "method": "UPI", "idempotency_key": "e2e-1"},
        )
        self.assertTrue(payment["receipt_number"].startswith("REC-"))
        self.assertEqual(self.client.get(f"/api/bills/{march['id']}/").data["status"], "PAID")

        self.client.patch(f"/api/leases/{lease['id']}/", {"monthly_rent_cents": 1300000}, format="json")
        self.post("/api/meter-readings/", {"meter_id": meter["id"], "reading_date": "2026-04-30", "reading_value": "12700"})
        april_cycle = self.post("/api/billing/cycles/", {"period": "2026-04"})
        self.post(f"/api/billing/cycles/{april_cycle['id']}/generate/", expect=200)
        april = self.client.get("/api/bills/?period=2026-04").data["results"][0]
        self.assertEqual(april["rent_cents"], 1300000)
        self.assertEqual(self.client.get(f"/api/bills/{march['id']}/").data["rent_cents"], 1200000)

        # Green Valley: a separate owner and workspace.
        gv_owner = make_user("owner@greenvalley.test")
        bearer(self.client, gv_owner)
        gv = self.post("/api/tenants/", {"name": "Green Valley Apartments", "slug": "green-valley"})
        bearer(self.client, gv_owner, SimpleNamespace(id=gv["id"]))
        self.assertEqual(self.client.get(f"/api/bills/{march['id']}/").status_code, 404)
        self.assertEqual(self.client.get("/api/bills/").data["count"], 0)
        bearer(self.client, owner, SimpleNamespace(id=gv["id"]))
        self.assertEqual(self.client.get("/api/bills/").status_code, 403)

        admin = User.objects.create_user(email="root@tenora.test", password="x-Strong-pass-1", is_staff=True, is_superuser=True)
        bearer(self.client, admin)
        workspaces = self.client.get("/api/platform/property-billing/workspaces/").data
        self.assertEqual({w["name"] for w in workspaces["results"]}, {"Sunrise Apartments", "Green Valley Apartments"})
        detail = self.client.get(f"/api/platform/property-billing/bills/detail/?id={march['id']}").data
        self.assertEqual(detail["total_cents"], 1378000)

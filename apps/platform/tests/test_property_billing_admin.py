"""Platform-admin property billing visibility and workspace role control."""

from rest_framework.test import APITestCase

from apps.platform.models import AuditEvent
from apps.properties.tests.factories import Scenario, bearer, make_user
from apps.tenants.authentication import GLOBAL_PATHS
from apps.tenants.models import Membership


class PlatformPropertyBillingTests(APITestCase):
    def setUp(self):
        self.a = Scenario(slug="sunrise")
        self.b = Scenario(slug="green-valley")
        self.bill_a = self.a.march_bill()
        self.bill_b = self.b.march_bill()
        self.a.pay(self.bill_a, 1_378_000)
        self.staff = make_user("staff@example.com", is_staff=True)
        self.root = make_user("root@example.com", is_staff=True, is_superuser=True)

    def test_ordinary_users_and_residents_are_refused(self):
        for user in (self.a.owner, self.a.user):
            bearer(self.client, user)
            for url in (
                "/api/platform/property-billing/summary/",
                "/api/platform/property-billing/bills/",
                "/api/platform/property-billing/workspaces/",
            ):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_staff_sees_all_workspaces_and_can_filter(self):
        bearer(self.client, self.staff)
        summary = self.client.get("/api/platform/property-billing/summary/").data
        self.assertEqual(summary["total_bills"], 2)
        self.assertEqual(summary["total_billed_cents"], 2 * 1_378_000)
        self.assertEqual(summary["total_collected_cents"], 1_378_000)
        bills = self.client.get("/api/platform/property-billing/bills/").data
        self.assertEqual(bills["count"], 2)
        only_b = self.client.get(f"/api/platform/property-billing/bills/?tenant={self.b.tenant.id}").data
        self.assertEqual([r["id"] for r in only_b["results"]], [str(self.bill_b.id)])
        unpaid = self.client.get("/api/platform/property-billing/bills/?payment_status=UNPAID").data
        self.assertEqual([r["tenant_name"] for r in unpaid["results"]], [self.b.tenant.name])

    def test_workspace_drilldown_and_bill_detail(self):
        bearer(self.client, self.staff)
        detail = self.client.get(f"/api/platform/property-billing/workspaces/detail/?id={self.a.tenant.id}").data
        self.assertEqual(detail["properties"][0]["units"][0]["identifier"], "203")
        self.assertEqual(detail["residents"][0]["paid_cents"], 1_378_000)
        bill = self.client.get(f"/api/platform/property-billing/bills/detail/?id={self.bill_b.id}").data
        self.assertEqual(bill["tenant_name"], self.b.tenant.name)
        self.assertEqual(len(bill["line_items"]), 3)
        self.assertEqual(self.client.get("/api/platform/property-billing/receipts/").data["count"], 1)

    def test_root_promotes_and_demotes_regardless_of_plan_keeping_one_owner(self):
        member = Membership.objects.get(user=self.a.user, tenant=self.a.tenant)
        owner = Membership.objects.get(user=self.a.owner, tenant=self.a.tenant)
        bearer(self.client, self.staff)
        self.assertEqual(
            self.client.patch(f"/api/platform/memberships/detail/?id={member.id}", {"role": "OWNER"}, format="json").status_code,
            403,
        )
        bearer(self.client, self.root)
        blocked = self.client.patch(f"/api/platform/memberships/detail/?id={owner.id}", {"role": "MEMBER"}, format="json")
        self.assertEqual(blocked.status_code, 409)
        promoted = self.client.patch(f"/api/platform/memberships/detail/?id={member.id}", {"role": "OWNER"}, format="json")
        self.assertEqual(promoted.data["role"], "OWNER")
        demoted = self.client.patch(f"/api/platform/memberships/detail/?id={owner.id}", {"role": "MEMBER"}, format="json")
        self.assertEqual(demoted.data["role"], "MEMBER")
        self.assertEqual(AuditEvent.objects.filter(action="membership.role_changed", is_critical=True).count(), 2)

    def test_financial_actions_are_audited(self):
        actions = set(AuditEvent.objects.values_list("action", flat=True))
        for expected in (
            "invitation.created", "invitation.accepted", "property.created", "unit.created", "lease.created",
            "meter.created", "meter_reading.recorded", "tariff.created", "bills.generated", "bill.published",
            "payment.recorded", "receipt.issued", "workspace_settings.updated",
        ):
            self.assertIn(expected, actions)

    def test_staff_can_edit_plan_limits_even_on_a_synced_plan(self):
        from apps.billing.models import Plan

        plan = Plan.objects.create(
            name="Pro", code="PRO-LIM", price_cents=100, external_plan_id="plan_ext_1"
        )
        bearer(self.client, self.staff)
        resp = self.client.patch(
            f"/api/platform/plans/detail/?id={plan.id}",
            {"max_workspaces": 20, "max_members_per_workspace": 20},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        plan.refresh_from_db()
        self.assertEqual((plan.max_workspaces, plan.max_members_per_workspace), (20, 20))
        locked = self.client.patch(
            f"/api/platform/plans/detail/?id={plan.id}", {"price_cents": 1}, format="json"
        )
        self.assertNotEqual(locked.status_code, 200)

    def test_new_platform_paths_are_exact_global_paths(self):
        for path in (
            "/api/platform/property-billing/summary/",
            "/api/platform/property-billing/bills/detail/",
            "/api/platform/memberships/detail/",
        ):
            self.assertIn(path, GLOBAL_PATHS)
        self.assertNotIn("/api/bills/", GLOBAL_PATHS)
        self.assertNotIn("/api/properties/", GLOBAL_PATHS)

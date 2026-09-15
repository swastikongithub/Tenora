"""Owner billing portfolio (plan §16.2): totals across only the workspaces the
authenticated user controls, never mixing currencies, refused to residents."""

from datetime import date
from unittest import mock

from rest_framework.test import APITestCase

from apps.properties.models import WorkspaceSettings
from apps.properties.tests.factories import Scenario, add_resident, bearer, make_workspace
from apps.tenants.authentication import GLOBAL_PATHS
from apps.tenants.models import Membership
from apps.tenants.services import MembershipService

URL = "/api/account/billing-portfolio/"


class PortfolioTests(APITestCase):
    def setUp(self):
        # Sunrise: ₹13,780 billed for March, ₹3,780 paid. Green Valley belongs to
        # the same owner, unbilled. Other Owner's workspace must never appear.
        self.sunrise = Scenario(slug="sunrise")
        self.owner = self.sunrise.owner
        self.bill = self.sunrise.march_bill()
        self.sunrise.pay(self.bill, 378_000)
        self.green_valley, _ = make_workspace("green-valley", owner=self.owner)
        self.other = Scenario(slug="elsewhere")
        self.other.march_bill()

    def fetch(self, user, period="2026-03", today=date(2026, 4, 20)):
        bearer(self.client, user)
        with mock.patch("apps.properties.aging.server_today", return_value=today):
            return self.client.get(URL, {"period": period})

    def test_is_an_exact_global_path(self):
        self.assertIn(URL, GLOBAL_PATHS)

    def test_totals_cover_only_the_owners_workspaces(self):
        resp = self.fetch(self.owner)
        self.assertEqual(resp.status_code, 200, resp.data)
        names = [w["name"] for w in resp.data["workspaces"]]
        self.assertEqual(names, [self.sunrise.tenant.name, self.green_valley.name])
        sunrise = resp.data["workspaces"][0]
        self.assertEqual(
            (sunrise["billed_cents"], sunrise["collected_cents"], sunrise["outstanding_cents"], sunrise["overdue_cents"]),
            (1_378_000, 378_000, 1_000_000, 1_000_000),
        )
        [inr] = resp.data["totals"]
        self.assertEqual(inr["currency"], "INR")
        self.assertEqual(inr["workspaces"], 2)
        self.assertEqual(inr["billed_cents"], 1_378_000)
        self.assertEqual(inr["total_overdue_cents"], 1_000_000)
        self.assertEqual(sum(b["amount_cents"] for b in inr["buckets"]), 1_000_000)

    def test_a_workspace_where_the_user_is_only_a_resident_is_excluded(self):
        add_resident(self.other.tenant, self.other.owner, self.owner.email)
        names = [w["name"] for w in self.fetch(self.owner).data["workspaces"]]
        self.assertNotIn(self.other.tenant.name, names)

    def test_a_workspace_the_owner_left_is_excluded(self):
        second_owner = add_resident(self.green_valley, self.owner, "co-owner@example.com")[0]
        Membership.objects.filter(user=second_owner, tenant=self.green_valley).update(role=Membership.Role.OWNER)
        MembershipService.leave(user=self.owner, tenant=self.green_valley)
        names = [w["name"] for w in self.fetch(self.owner).data["workspaces"]]
        self.assertEqual(names, [self.sunrise.tenant.name])

    def test_currencies_are_never_added_together(self):
        WorkspaceSettings.objects.filter(tenant=self.green_valley).delete()
        WorkspaceSettings.objects.create(tenant=self.green_valley, currency="USD")
        totals = {t["currency"]: t for t in self.fetch(self.owner).data["totals"]}
        self.assertEqual(set(totals), {"INR", "USD"})
        self.assertEqual(totals["INR"]["billed_cents"], 1_378_000)
        self.assertEqual(totals["USD"]["billed_cents"], 0)

    def test_residents_are_refused(self):
        resp = self.fetch(self.sunrise.user)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "not_a_workspace_owner")

    def test_unauthenticated_is_refused(self):
        self.client.credentials()
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_a_tenant_id_in_the_request_changes_nothing(self):
        bearer(self.client, self.owner)
        resp = self.client.get(URL, {"period": "2026-03", "tenant": str(self.other.tenant.id)}, HTTP_X_TENANT_ID=str(self.other.tenant.id))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(str(self.other.tenant.id), [w["id"] for w in resp.data["workspaces"]])

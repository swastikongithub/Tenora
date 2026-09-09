"""
seed_demo_data management command — docs/docker-packaging-spec.md §4.5/§8.

The command runs on every container start (gated by SEED_DEMO_DATA), so its
idempotency is a real correctness requirement, not a nicety: this proves it
concretely (row counts unchanged across repeated runs), not just by
inspecting the check-then-create shape of the code.
"""

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import Plan, Subscription
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

LOGIN_URL = "/api/auth/login/"


class SeedDemoDataTests(TestCase):
    def test_creates_one_of_each_row(self):
        call_command("seed_demo_data")

        self.assertEqual(User.objects.filter(email="demo@example.com").count(), 1)
        self.assertEqual(Tenant.objects.filter(slug="demo-workspace").count(), 1)
        self.assertEqual(Plan.objects.filter(code__in=["PRO", "TEAM"]).count(), 2)

        tenant = Tenant.objects.get(slug="demo-workspace")
        user = User.objects.get(email="demo@example.com")
        self.assertEqual(
            Membership.objects.filter(user=user, tenant=tenant, role="OWNER").count(),
            1,
        )
        self.assertEqual(Subscription.objects.filter(tenant=tenant).count(), 1)

    def test_running_twice_does_not_duplicate_anything(self):
        call_command("seed_demo_data")
        call_command("seed_demo_data")

        self.assertEqual(User.objects.filter(email="demo@example.com").count(), 1)
        self.assertEqual(Tenant.objects.filter(slug="demo-workspace").count(), 1)
        self.assertEqual(Plan.objects.filter(code__in=["PRO", "TEAM"]).count(), 2)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_demo_user_can_authenticate_with_the_documented_password(self):
        call_command("seed_demo_data")

        user = User.objects.get(email="demo@example.com")
        self.assertTrue(user.check_password("demo-pass-12345"))

    def test_third_run_still_a_no_op(self):
        call_command("seed_demo_data")
        call_command("seed_demo_data")
        call_command("seed_demo_data")

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), 1)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertEqual(Plan.objects.count(), 2)


class SeedDemoDataLoginTests(APITestCase):
    """
    email-verification-spec.md §8: the grandfathering migration only covers
    rows that exist at migration-apply time, not a demo user seeded fresh
    afterward — this proves the seed command sets email_verified=True itself
    by actually logging the seeded account in through the real gated
    endpoint, not by inspecting the seed command's code.
    """

    def test_seeded_demo_account_can_log_in_through_the_real_endpoint(self):
        call_command("seed_demo_data")

        resp = self.client.post(
            LOGIN_URL, {"email": "demo@example.com", "password": "demo-pass-12345"}
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

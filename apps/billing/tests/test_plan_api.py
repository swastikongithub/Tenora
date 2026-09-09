"""
GET /api/plans/ — spec §B2.4.1. Global path, IsAuthenticated only.

Real access token, not force_authenticate — same reason as the B1 API
tests (force_authenticate replaces the authenticator tuple and
TenantJWTAuthentication never runs).
"""

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan
from apps.users.models import User

URL = "/api/plans/"
PASSWORD = "correct-horse-staple-42"


class PlanListTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="user@example.com", password=PASSWORD
        )

    def _auth(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}"
        )

    def test_active_plans_returned_inactive_excluded(self):
        Plan.objects.create(name="Pro", code="PRO", price_cents=2900, currency="USD")
        Plan.objects.create(
            name="Legacy", code="LEGACY", price_cents=900, currency="USD",
            is_active=False,
        )
        self._auth(self.user)

        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = {row["code"] for row in resp.data}
        self.assertEqual(codes, {"PRO"})

    def test_no_active_plans_returns_empty_list(self):
        Plan.objects.create(
            name="Legacy", code="LEGACY", price_cents=900, currency="USD",
            is_active=False,
        )
        self._auth(self.user)

        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

    def test_unauthenticated_returns_401(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

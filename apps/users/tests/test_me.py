"""
GET /api/users/me/ — the requesting user's own identity.

Stage C3 §0.1. Lets the frontend show the real signed-in email after a
silent-refresh reload instead of a "Signed in" stopgap. Global path: no
X-Tenant-ID required (identity, not tenant data).
"""

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.users.models import User

ME_URL = "/api/users/me/"
GOOD_PASSWORD = "correct-horse-staple-42"


class MeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="me@example.com", password=GOOD_PASSWORD
        )

    def _auth(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}"
        )

    def test_authenticated_returns_identity_fields(self):
        self._auth(self.user)

        resp = self.client.get(ME_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # `is_staff` was added (MeSerializer) so the frontend can gate the
        # platform-admin dashboard — docs/platform-admin-spec.md §4.4;
        # `is_superuser` joined it in Operator Control Plane Phase 4 so the
        # Root-only operator controls don't render for a Staff-tier viewer
        # (docs/operator-control-plane-spec.md §D). Both are on this endpoint
        # only; RegisterView's {id, email} shape is unchanged.
        self.assertEqual(set(resp.data), {"id", "email", "is_staff", "is_superuser"})
        self.assertEqual(resp.data["email"], "me@example.com")
        self.assertEqual(str(resp.data["id"]), str(self.user.id))

    def test_is_staff_reflects_the_user(self):
        # A normal account: False.
        self._auth(self.user)
        self.assertIs(self.client.get(ME_URL).data["is_staff"], False)

        # A staff account: True.
        staff = User.objects.create_user(
            email="staff@example.com", password=GOOD_PASSWORD, is_staff=True
        )
        self._auth(staff)
        self.assertIs(self.client.get(ME_URL).data["is_staff"], True)

    def test_is_superuser_reflects_the_user(self):
        # A normal account: False.
        self._auth(self.user)
        self.assertIs(self.client.get(ME_URL).data["is_superuser"], False)

        # A root account: True. Both flags, which is exactly the predicate
        # IsPlatformRoot checks server-side.
        root = User.objects.create_user(
            email="root@example.com",
            password=GOOD_PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self._auth(root)
        body = self.client.get(ME_URL).data
        self.assertIs(body["is_staff"], True)
        self.assertIs(body["is_superuser"], True)

    def test_returns_the_requesting_user_not_some_other(self):
        other = User.objects.create_user(
            email="other@example.com", password=GOOD_PASSWORD
        )
        self._auth(other)

        resp = self.client.get(ME_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["email"], "other@example.com")

    def test_unauthenticated_returns_401(self):
        resp = self.client.get(ME_URL)

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_tenant_header_required(self):
        # Global path: a valid JWT alone is enough, no X-Tenant-ID.
        self._auth(self.user)

        resp = self.client.get(ME_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_password_hash_never_exposed(self):
        self._auth(self.user)

        resp = self.client.get(ME_URL)

        self.assertNotIn("password", resp.data)

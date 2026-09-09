"""
POST /api/tenants/ and GET /api/tenants/me/ — spec §10 "Tenant
creation / listing".

Both are global paths (no X-Tenant-ID). Tests mint a real access token
rather than using force_authenticate: force_authenticate replaces the
authenticator tuple (rest_framework/request.py), which would also be
fine here, but keeping one auth mechanism across the B1 API tests
avoids surprises when the same helper is reused for tenant-scoped views.
"""

from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.tenants.models import Membership, Tenant
from apps.users.models import User

TENANTS_URL = "/api/tenants/"
ME_URL = "/api/tenants/me/"
PASSWORD = "correct-horse-staple-42"


def bearer(user):
    return f"Bearer {AccessToken.for_user(user)}"


class TenantCreateTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="creator@example.com", password=PASSWORD
        )

    def test_create_tenant_creates_owner_membership_atomically(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.user))

        resp = self.client.post(TENANTS_URL, {"name": "Acme", "slug": "acme"})

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["slug"], "acme")
        self.assertEqual(resp.data["role"], Membership.Role.OWNER)

        tenant = Tenant.objects.get(slug="acme")
        membership = Membership.objects.get(tenant=tenant, user=self.user)
        self.assertEqual(membership.role, Membership.Role.OWNER)

    def test_duplicate_slug_returns_400_and_leaves_nothing_behind(self):
        Tenant.objects.create(name="Existing", slug="taken")
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.user))

        resp = self.client.post(TENANTS_URL, {"name": "New", "slug": "taken"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slug", resp.data)
        self.assertEqual(Tenant.objects.filter(slug="taken").count(), 1)
        self.assertFalse(Membership.objects.filter(user=self.user).exists())

    def test_tenant_rolls_back_if_membership_creation_fails(self):
        # The membership insert blowing up must undo the tenant insert —
        # this is the only assertion that actually exercises the
        # transaction.atomic() in TenantService.create_tenant.
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.user))

        with mock.patch(
            "apps.tenants.services.Membership.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(TENANTS_URL, {"name": "Acme", "slug": "acme"})

        self.assertFalse(Tenant.objects.filter(slug="acme").exists())

    def test_unauthenticated_returns_401(self):
        resp = self.client.post(TENANTS_URL, {"name": "Acme", "slug": "acme"})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class MyTenantsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="multi@example.com", password=PASSWORD
        )

    def test_returns_every_tenant_with_its_role(self):
        t_owner = Tenant.objects.create(name="Owned", slug="owned")
        t_member = Tenant.objects.create(name="Joined", slug="joined")
        Membership.objects.create(
            user=self.user, tenant=t_owner, role=Membership.Role.OWNER
        )
        Membership.objects.create(
            user=self.user, tenant=t_member, role=Membership.Role.MEMBER
        )
        # A tenant the user is NOT in — must not appear.
        Tenant.objects.create(name="Foreign", slug="foreign")

        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.user))
        resp = self.client.get(ME_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        by_slug = {row["slug"]: row["role"] for row in resp.data}
        self.assertEqual(
            by_slug,
            {"owned": Membership.Role.OWNER, "joined": Membership.Role.MEMBER},
        )

    def test_zero_memberships_returns_200_and_empty_list(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.user))

        resp = self.client.get(ME_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

    def test_unauthenticated_returns_401(self):
        resp = self.client.get(ME_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

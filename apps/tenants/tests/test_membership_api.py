"""
GET/POST /api/memberships/ — spec §10 "Membership listing / creation".

Tenant-scoped, so these tests mint a real access token and send an
X-Tenant-ID header: force_authenticate would replace the authenticator
tuple (rest_framework/request.py) and TenantJWTAuthentication would
never run, leaving request.tenant unset. This is not the B3 login-flow
integration work — just the only way to reach the auth class.
"""

from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.tenants.models import Membership, Tenant
from apps.tenants.services import MembershipService
from apps.users.models import User

URL = "/api/memberships/"
PASSWORD = "correct-horse-staple-42"


class MembershipAPITests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.other_tenant = Tenant.objects.create(name="Other", slug="other")

        self.owner = User.objects.create_user(
            email="owner@example.com", password=PASSWORD
        )
        self.member = User.objects.create_user(
            email="member@example.com", password=PASSWORD
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com", password=PASSWORD
        )

        Membership.objects.create(
            user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER
        )
        Membership.objects.create(
            user=self.member, tenant=self.tenant, role=Membership.Role.MEMBER
        )

    def _auth(self, user, tenant_id=None):
        creds = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}
        if tenant_id is not None:
            creds["HTTP_X_TENANT_ID"] = str(tenant_id)
        self.client.credentials(**creds)

    # --- listing -----------------------------------------------------------

    def test_owner_can_list(self):
        self._auth(self.owner, self.tenant.id)
        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        emails = {row["email"] for row in resp.data}
        self.assertEqual(emails, {"owner@example.com", "member@example.com"})

    def test_member_can_list(self):
        self._auth(self.member, self.tenant.id)
        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

    def test_listing_is_scoped_to_the_header_tenant(self):
        dual = User.objects.create_user(email="dual@example.com", password=PASSWORD)
        Membership.objects.create(
            user=dual, tenant=self.tenant, role=Membership.Role.MEMBER
        )
        Membership.objects.create(
            user=dual, tenant=self.other_tenant, role=Membership.Role.OWNER
        )
        other_only = User.objects.create_user(
            email="other-only@example.com", password=PASSWORD
        )
        Membership.objects.create(
            user=other_only, tenant=self.other_tenant, role=Membership.Role.MEMBER
        )

        self._auth(dual, self.tenant.id)
        resp = self.client.get(URL)

        emails = {row["email"] for row in resp.data}
        self.assertEqual(
            emails,
            {"owner@example.com", "member@example.com", "dual@example.com"},
        )
        self.assertNotIn("other-only@example.com", emails)

    # --- creation --------------------------------------------------------

    def test_owner_adds_existing_user_as_member(self):
        self._auth(self.owner, self.tenant.id)
        resp = self.client.post(URL, {"email": "outsider@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["role"], Membership.Role.MEMBER)
        m = Membership.objects.get(user=self.outsider, tenant=self.tenant)
        self.assertEqual(m.role, Membership.Role.MEMBER)

    def test_member_cannot_add_and_gets_403(self):
        self._auth(self.member, self.tenant.id)
        resp = self.client.post(URL, {"email": "outsider@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            Membership.objects.filter(
                user=self.outsider, tenant=self.tenant
            ).exists()
        )

    def test_role_in_body_is_ignored(self):
        self._auth(self.owner, self.tenant.id)
        resp = self.client.post(
            URL, {"email": "outsider@example.com", "role": "OWNER"}
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        m = Membership.objects.get(user=self.outsider, tenant=self.tenant)
        self.assertEqual(m.role, Membership.Role.MEMBER)

    def test_tenant_id_in_body_is_ignored(self):
        self._auth(self.owner, self.tenant.id)
        resp = self.client.post(
            URL,
            {
                "email": "outsider@example.com",
                "tenant_id": str(self.other_tenant.id),
            },
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Membership.objects.filter(
                user=self.outsider, tenant=self.tenant
            ).exists()
        )
        self.assertFalse(
            Membership.objects.filter(
                user=self.outsider, tenant=self.other_tenant
            ).exists()
        )

    def test_unknown_email_returns_404(self):
        self._auth(self.owner, self.tenant.id)
        resp = self.client.post(URL, {"email": "nobody@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_duplicate_member_via_precheck_returns_400(self):
        self._auth(self.owner, self.tenant.id)
        resp = self.client.post(URL, {"email": "member@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)
        self.assertEqual(
            Membership.objects.filter(
                user=self.member, tenant=self.tenant
            ).count(),
            1,
        )

    def test_duplicate_member_via_integrityerror_path_returns_400(self):
        # Neutralise the pre-check so UNIQUE(user, tenant) is what rejects
        # the insert — this is the concurrency guarantee, the pre-check is
        # only a UX convenience.
        self._auth(self.owner, self.tenant.id)

        with mock.patch.object(
            MembershipService, "_member_exists", return_value=False
        ):
            resp = self.client.post(URL, {"email": "member@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)
        self.assertEqual(
            Membership.objects.filter(
                user=self.member, tenant=self.tenant
            ).count(),
            1,
        )

    # --- tenant-context contract (spec §9) --------------------------------

    def test_unauthenticated_returns_401(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_tenant_header_returns_400(self):
        self._auth(self.owner)  # token but no X-Tenant-ID
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_malformed_tenant_header_returns_400_not_500(self):
        self._auth(self.owner, "not-a-uuid")
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tenant_header_for_non_member_tenant_returns_403(self):
        outsider_tenant = Tenant.objects.create(name="Nope", slug="nope")
        self._auth(self.owner, outsider_tenant.id)
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

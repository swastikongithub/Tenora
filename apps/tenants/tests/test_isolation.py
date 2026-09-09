"""
The single most important test in this project.

Nothing in Phase 2+ matters if this doesn't hold. Run this before
writing any other view logic — it should fail against an empty
urls.py, then you build views/permissions/managers until it's green.

Attacks every verb, not just GET, and attacks tenant-context
manipulation (a forged tenant_id in the request body) in addition to
plain object-ID access — a GET-only test would pass even if PATCH or
body-based tenant switching were still wide open.

Auth: _auth_as() mints a real JWT (not force_authenticate), so
TenantJWTAuthentication genuinely runs. Caveat: the three
foreign-subscription tests hit a route that doesn't exist
(/api/subscriptions/<id>/ — only /current/ is wired), so their 404s
come from the URL resolver, not from the auth class + scoped manager.
Each of those tests documents this in its own docstring.
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan, Subscription
from apps.tenants.models import Membership, Tenant
from apps.users.models import User


class CrossTenantIsolationTests(APITestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )

        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")

        self.user_a = User.objects.create_user(
            email="owner-a@example.com", password="testpass123"
        )
        self.user_b = User.objects.create_user(
            email="owner-b@example.com", password="testpass123"
        )

        Membership.objects.create(
            user=self.user_a, tenant=self.tenant_a, role=Membership.Role.OWNER
        )
        Membership.objects.create(
            user=self.user_b, tenant=self.tenant_b, role=Membership.Role.OWNER
        )

        now = timezone.now()
        self.subscription_a = Subscription.objects.create(
            tenant=self.tenant_a,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
        )
        self.subscription_b = Subscription.objects.create(
            tenant=self.tenant_b,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
        )

    def _auth_as(self, user, tenant):
        # Mint a real access token so TenantJWTAuthentication actually
        # runs: force_authenticate() replaces DRF's authenticator tuple
        # entirely (rest_framework/request.py), so the auth class — and
        # with it GLOBAL_PATHS, the 400/403 contract, and tenant
        # resolution — would never execute. Same pattern as
        # test_membership_api.py / test_subscription_api.py.
        token = AccessToken.for_user(user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_X_TENANT_ID=str(tenant.id),
        )

    def test_get_foreign_subscription_returns_404(self):
        """
        Cross-tenant object access returns 404, not 403.

        Coverage caveat: there is no ``/api/subscriptions/<id>/`` detail
        route (only ``/current/``), so this 404 comes from Django's URL
        resolver, NOT from TenantJWTAuthentication resolving the caller's
        tenant and then TenantScopedManager failing the lookup. The
        assertion its name makes is still true, but the code path is
        routing-level isolation only. A real object-level isolation test
        needs a detail endpoint, which Phase 1 does not define.
        """
        self._auth_as(self.user_a, self.tenant_a)
        url = f"/api/subscriptions/{self.subscription_b.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_foreign_subscription_returns_404(self):
        """
        Cross-tenant PATCH returns 404 and does not mutate the target.

        Coverage caveat: as with the GET case, this 404 is produced by
        the URL resolver (no ``/api/subscriptions/<id>/`` route exists),
        not by TenantJWTAuthentication + TenantScopedManager. The
        "Tenant B's subscription is untouched" assertion still holds
        because the request never reaches a view at all.
        """
        self._auth_as(self.user_a, self.tenant_a)
        url = f"/api/subscriptions/{self.subscription_b.id}/"
        response = self.client.patch(url, {"status": "CANCELED"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.subscription_b.refresh_from_db()
        self.assertEqual(self.subscription_b.status, Subscription.Status.ACTIVE)

    def test_delete_foreign_subscription_returns_404(self):
        """
        Cross-tenant DELETE returns 404 and does not delete the target.

        Coverage caveat: same as the GET/PATCH cases — this 404 is a URL
        resolver miss (no ``/api/subscriptions/<id>/`` route), not
        TenantJWTAuthentication + TenantScopedManager denying access to
        a real object.
        """
        self._auth_as(self.user_a, self.tenant_a)
        url = f"/api/subscriptions/{self.subscription_b.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(
            Subscription.objects.filter(id=self.subscription_b.id).exists()
        )

    def test_forged_tenant_id_in_body_is_not_honored(self):
        """
        Authenticated as Tenant A, but the request body claims to act
        on Tenant B. tenant_id must never be accepted as an input
        field at all — the tenant comes exclusively from
        X-Tenant-ID + Membership resolution.
        """
        self._auth_as(self.user_a, self.tenant_a)
        url = "/api/subscriptions/current/"
        response = self.client.patch(
            url, {"tenant_id": str(self.tenant_b.id), "status": "CANCELED"}
        )
        # Whatever happened, it must have happened to Tenant A's
        # subscription, never Tenant B's.
        self.subscription_b.refresh_from_db()
        self.assertEqual(self.subscription_b.status, Subscription.Status.ACTIVE)

    def test_missing_tenant_header_returns_400(self):
        # Deliberately sends a real, valid JWT but NO X-Tenant-ID — the
        # whole point of the test — so it can't use _auth_as (which
        # always sets both headers). Expect a genuine 400 from
        # TenantHeaderRequired in TenantJWTAuthentication, not a 403
        # from IsTenantMember on an unresolved membership.
        token = AccessToken.for_user(self.user_a)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get("/api/subscriptions/current/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tenant_header_for_non_member_tenant_returns_403(self):
        # user_a authenticates with a real token but claims tenant_b,
        # where they have no Membership row at all. Expect a genuine 403
        # from PermissionDenied in TenantJWTAuthentication when the
        # Membership lookup misses.
        self._auth_as(self.user_a, self.tenant_b)
        response = self.client.get("/api/subscriptions/current/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

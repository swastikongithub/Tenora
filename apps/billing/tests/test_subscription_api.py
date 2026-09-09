"""
GET/PATCH /api/subscriptions/current/ (+ the D2 checkout endpoints).

Tenant-scoped, so these tests mint a real access token and send an
X-Tenant-ID header (force_authenticate would bypass
TenantJWTAuthentication and leave request.tenant unset).
"""

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan, Subscription, SubscriptionCheckout
from apps.billing.services import SubscriptionService
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

URL = "/api/subscriptions/current/"
PASSWORD = "correct-horse-staple-42"


class SubscriptionAPITestBase(APITestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        self.other_plan = Plan.objects.create(
            name="Team", code="TEAM", price_cents=9900, currency="USD"
        )
        self.inactive_plan = Plan.objects.create(
            name="Legacy", code="LEGACY", price_cents=900, currency="USD",
            is_active=False,
        )

        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.owner = User.objects.create_user(
            email="owner@example.com", password=PASSWORD
        )
        self.member = User.objects.create_user(
            email="member@example.com", password=PASSWORD
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

    def _create_subscription(self, tenant=None, plan=None):
        tenant = tenant or self.tenant
        plan = plan or self.plan
        start, end = SubscriptionService.default_period(plan)
        return SubscriptionService.create_subscription(
            tenant=tenant,
            plan=plan,
            current_period_start=start,
            current_period_end=end,
        )


class SubscriptionReadTests(SubscriptionAPITestBase):
    def test_owner_can_read(self):
        self._create_subscription()
        self._auth(self.owner, self.tenant.id)

        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["plan"]["code"], "PRO")
        self.assertEqual(resp.data["status"], Subscription.Status.TRIALING)

    def test_member_can_read(self):
        self._create_subscription()
        self._auth(self.member, self.tenant.id)

        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_no_subscription_returns_404(self):
        self._auth(self.owner, self.tenant.id)

        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_tenant_header_returns_400(self):
        self._auth(self.owner)

        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_two_tenant_isolation_never_crossed(self):
        tenant_b = Tenant.objects.create(name="Beta", slug="beta")
        Membership.objects.create(
            user=self.owner, tenant=tenant_b, role=Membership.Role.OWNER
        )
        sub_a = self._create_subscription(tenant=self.tenant, plan=self.plan)
        sub_b = self._create_subscription(tenant=tenant_b, plan=self.other_plan)

        self._auth(self.owner, self.tenant.id)
        resp_a = self.client.get(URL)
        self.assertEqual(str(resp_a.data["id"]), str(sub_a.id))
        self.assertEqual(resp_a.data["plan"]["code"], "PRO")

        self._auth(self.owner, tenant_b.id)
        resp_b = self.client.get(URL)
        self.assertEqual(str(resp_b.data["id"]), str(sub_b.id))
        self.assertEqual(resp_b.data["plan"]["code"], "TEAM")


@override_settings(PAYMENT_GATEWAY="mock")
class SubscriptionCheckoutEndpointTests(SubscriptionAPITestBase):
    """
    POST /api/subscriptions/current/checkout/ — replaces the Phase-1
    POST /api/subscriptions/current/ (removed in D2: it created a local
    Subscription row directly, which now would fabricate a paid state).
    These carry over the auth / validation coverage the old
    SubscriptionCreateTests had, now against the checkout endpoint. The gateway
    adapter's own behaviour is covered in test_gateway_*.py; here the
    MockGatewayAdapter stands in for it.
    """

    URL = "/api/subscriptions/current/checkout/"

    def setUp(self):
        super().setUp()
        # Checkout needs a synced plan; a plan without external_plan_id is its
        # own 400 case, tested in test_checkout.py.
        self.plan.external_plan_id = "plan_TEST_PRO"
        self.plan.save(update_fields=["external_plan_id"])
        self.other_plan.external_plan_id = "plan_TEST_TEAM"
        self.other_plan.save(update_fields=["external_plan_id"])

    def test_owner_starts_checkout_without_creating_a_local_subscription(self):
        self._auth(self.owner, self.tenant.id)

        resp = self.client.post(self.URL, {"plan_id": str(self.plan.id)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # JSON key unchanged (external contract), value now from MockGatewayAdapter.
        self.assertEqual(
            resp.data["razorpay_subscription_id"], f"mock_sub_{self.tenant.id}"
        )
        self.assertEqual(resp.data["plan"]["code"], "PRO")
        self.assertIn("razorpay_key_id", resp.data)
        # The whole point: no local Subscription row.
        self.assertFalse(
            Subscription.objects.filter(tenant=self.tenant).exists()
        )

    def test_member_cannot_start_checkout_and_gets_403(self):
        self._auth(self.member, self.tenant.id)

        resp = self.client.post(self.URL, {"plan_id": str(self.plan.id)})

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            SubscriptionCheckout.objects.filter(tenant=self.tenant).exists()
        )

    def test_checkout_when_a_subscription_already_exists_returns_400(self):
        self._create_subscription(plan=self.plan)
        self._auth(self.owner, self.tenant.id)

        resp = self.client.post(self.URL, {"plan_id": str(self.other_plan.id)})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_plan_id_returns_400(self):
        self._auth(self.owner, self.tenant.id)

        resp = self.client.post(
            self.URL, {"plan_id": "00000000-0000-0000-0000-000000000000"}
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            SubscriptionCheckout.objects.filter(tenant=self.tenant).exists()
        )

    def test_inactive_plan_id_returns_400(self):
        self._auth(self.owner, self.tenant.id)

        resp = self.client.post(self.URL, {"plan_id": str(self.inactive_plan.id)})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            SubscriptionCheckout.objects.filter(tenant=self.tenant).exists()
        )

    def test_missing_tenant_header_returns_400(self):
        self._auth(self.owner)

        resp = self.client.post(self.URL, {"plan_id": str(self.plan.id)})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SubscriptionUpdateTests(SubscriptionAPITestBase):
    def test_owner_changes_plan(self):
        self._create_subscription(plan=self.plan)
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(URL, {"plan_id": str(self.other_plan.id)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["plan"]["code"], "TEAM")
        sub = Subscription.objects.get(tenant=self.tenant)
        self.assertEqual(sub.plan_id, self.other_plan.id)

    def test_owner_makes_legal_status_transition(self):
        self._create_subscription()  # starts TRIALING
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(URL, {"status": Subscription.Status.ACTIVE})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], Subscription.Status.ACTIVE)
        sub = Subscription.objects.get(tenant=self.tenant)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)

    def test_illegal_transition_returns_400_and_status_unchanged(self):
        sub = self._create_subscription()
        SubscriptionService.transition_status(sub, Subscription.Status.CANCELED)
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(URL, {"status": Subscription.Status.ACTIVE})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)

    def test_plan_change_on_canceled_subscription_returns_400_and_plan_unchanged(self):
        """
        CANCELED is terminal for the plan field, not only for status —
        master spec §B.5 names change_plan as a state-machine enforcement
        point. Without the guard in SubscriptionService.change_plan this
        PATCH would return 200 and silently reassign the plan.
        """
        sub = self._create_subscription(plan=self.plan)
        SubscriptionService.transition_status(sub, Subscription.Status.CANCELED)
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(URL, {"plan_id": str(self.other_plan.id)})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_id", resp.data)
        sub.refresh_from_db()
        self.assertEqual(sub.plan_id, self.plan.id)
        self.assertEqual(sub.status, Subscription.Status.CANCELED)

    def test_owner_cancels_from_each_legal_status(self):
        """
        PATCH {status: "CANCELED"} — the cancellation flow's real API call
        (docs/cancellation-spec.md). Works from every non-terminal status
        through the same view status-branch every other transition uses; no
        dedicated endpoint or service method is involved.
        """
        for start in (
            Subscription.Status.TRIALING,
            Subscription.Status.ACTIVE,
            Subscription.Status.PAST_DUE,
        ):
            with self.subTest(start=start):
                Subscription.objects.filter(tenant=self.tenant).delete()
                sub = self._create_subscription()  # starts TRIALING
                if start != Subscription.Status.TRIALING:
                    SubscriptionService.transition_status(
                        sub, Subscription.Status.ACTIVE
                    )
                    if start == Subscription.Status.PAST_DUE:
                        SubscriptionService.transition_status(
                            sub, Subscription.Status.PAST_DUE
                        )

                self._auth(self.owner, self.tenant.id)
                resp = self.client.patch(
                    URL, {"status": Subscription.Status.CANCELED}
                )

                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    resp.data["status"], Subscription.Status.CANCELED
                )
                sub.refresh_from_db()
                self.assertEqual(sub.status, Subscription.Status.CANCELED)

    def test_cancel_already_canceled_returns_400_and_status_unchanged(self):
        # A stale render or a double-submit race: CANCELED is terminal, so
        # CANCELED -> CANCELED is rejected exactly like any other move out of
        # CANCELED. The frontend surfaces resp.data["status"][0].
        sub = self._create_subscription()
        SubscriptionService.transition_status(sub, Subscription.Status.CANCELED)
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(URL, {"status": Subscription.Status.CANCELED})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)

    def test_member_cannot_cancel_and_gets_403(self):
        # IsTenantOwner is the real boundary for cancellation — not the
        # frontend hiding the button (docs/cancellation-spec.md §7).
        self._create_subscription()
        self._auth(self.member, self.tenant.id)

        resp = self.client.patch(URL, {"status": Subscription.Status.CANCELED})

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        sub = Subscription.objects.get(tenant=self.tenant)
        self.assertEqual(sub.status, Subscription.Status.TRIALING)

    def test_both_plan_and_status_returns_400(self):
        self._create_subscription()
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(
            URL,
            {
                "plan_id": str(self.other_plan.id),
                "status": Subscription.Status.ACTIVE,
            },
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        sub = Subscription.objects.get(tenant=self.tenant)
        self.assertEqual(sub.status, Subscription.Status.TRIALING)
        self.assertEqual(sub.plan_id, self.plan.id)

    def test_empty_body_returns_400(self):
        self._create_subscription()
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(URL, {})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_cannot_update_and_gets_403(self):
        self._create_subscription()
        self._auth(self.member, self.tenant.id)

        resp = self.client.patch(URL, {"status": Subscription.Status.ACTIVE})

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        sub = Subscription.objects.get(tenant=self.tenant)
        self.assertEqual(sub.status, Subscription.Status.TRIALING)

    def test_no_subscription_to_patch_returns_404(self):
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(URL, {"status": Subscription.Status.ACTIVE})

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_tenant_id_in_body_has_no_effect(self):
        tenant_b = Tenant.objects.create(name="Beta", slug="beta")
        Membership.objects.create(
            user=self.owner, tenant=tenant_b, role=Membership.Role.OWNER
        )
        sub_b = self._create_subscription(tenant=tenant_b, plan=self.other_plan)
        self._create_subscription(tenant=self.tenant, plan=self.plan)
        self._auth(self.owner, self.tenant.id)

        resp = self.client.patch(
            URL,
            {"tenant_id": str(tenant_b.id), "status": Subscription.Status.ACTIVE},
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sub_b.refresh_from_db()
        self.assertEqual(sub_b.status, Subscription.Status.TRIALING)

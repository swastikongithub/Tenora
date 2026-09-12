"""
PATCH /api/platform/subscriptions/detail/?id=<uuid> — docs
/operator-control-plane-spec.md §B: an operator override, Staff-tier
(not Root), reusing SubscriptionService.change_plan / .transition_status
verbatim — this endpoint must never be able to express a state change those
services don't already allow.

Real access tokens throughout — force_authenticate would bypass
TenantJWTAuthentication, which is exactly the code path these tests need to
exercise (this is a GLOBAL_PATH: no X-Tenant-ID should ever be required, and
one sent for a foreign tenant must not change the outcome).
"""

from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan, Subscription
from apps.billing.services import SubscriptionService
from apps.platform.models import AuditEvent
from apps.tenants.models import Tenant
from apps.users.models import User

URL = "/api/platform/subscriptions/detail/"
PASSWORD = "correct-horse-staple-42"


def _url(sub_id):
    return f"{URL}?id={sub_id}"


class SubscriptionMutationTestBase(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.root = User.objects.create_user(
            email="root@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.ordinary = User.objects.create_user(
            email="normal@example.com", password=PASSWORD
        )

        self.pro = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        self.team = Plan.objects.create(
            name="Team", code="TEAM", price_cents=9900, currency="USD"
        )
        self.inactive = Plan.objects.create(
            name="Legacy",
            code="LEGACY",
            price_cents=900,
            currency="USD",
            is_active=False,
        )

        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        start, end = SubscriptionService.default_period(self.pro)
        sub = SubscriptionService.create_subscription(self.tenant, self.pro, start, end)
        self.subscription = SubscriptionService.transition_status(
            sub, Subscription.Status.ACTIVE
        )

    def _auth(self, user, tenant_id=None):
        creds = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}
        if tenant_id is not None:
            creds["HTTP_X_TENANT_ID"] = str(tenant_id)
        self.client.credentials(**creds)


class SubscriptionMutationPermissionTests(SubscriptionMutationTestBase):
    def test_unauthenticated_gets_401(self):
        resp = self.client.patch(
            _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ordinary_authenticated_user_gets_403(self):
        self._auth(self.ordinary)
        resp = self.client.patch(
            _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_is_allowed(self):
        self._auth(self.staff)
        resp = self.client.patch(
            _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_root_is_also_allowed_this_is_staff_tier_not_root_only(self):
        self._auth(self.root)
        resp = self.client.patch(
            _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_x_tenant_id_for_a_foreign_tenant_does_not_change_the_outcome(self):
        # Global path: TenantJWTAuthentication returns before ever resolving
        # X-Tenant-ID / Membership for this path. A header naming a tenant
        # the operator isn't even a member of must not 400/403 — proving no
        # membership lookup runs for this endpoint at all.
        other_tenant = Tenant.objects.create(name="Other", slug="other")
        self._auth(self.staff, tenant_id=other_tenant.id)
        resp = self.client.patch(
            _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_nonexistent_subscription_is_404_for_staff(self):
        self._auth(self.staff)
        resp = self.client.patch(
            _url("00000000-0000-0000-0000-000000000000"),
            {"status": "PAST_DUE"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_malformed_id_is_404_not_500(self):
        self._auth(self.staff)
        resp = self.client.patch(
            f"{URL}?id=not-a-uuid", {"status": "PAST_DUE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_id_is_404(self):
        self._auth(self.staff)
        resp = self.client.patch(URL, {"status": "PAST_DUE"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class SubscriptionMutationContractTests(SubscriptionMutationTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_both_plan_id_and_status_is_rejected(self):
        resp = self.client.patch(
            _url(self.subscription.id),
            {"status": "PAST_DUE", "plan_id": str(self.team.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_neither_field_is_rejected(self):
        resp = self.client.patch(_url(self.subscription.id), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejected_request_does_not_mutate_or_audit(self):
        self.client.patch(_url(self.subscription.id), {}, format="json")
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(AuditEvent.objects.count(), 0)


class SubscriptionMutationStatusTransitionTests(SubscriptionMutationTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_valid_status_transition_succeeds_via_the_real_service(self):
        resp = self.client.patch(
            _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "PAST_DUE")
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.PAST_DUE)

    def test_illegal_transition_rejected_with_the_same_error_shape_as_the_tenant_facing_endpoint(
        self,
    ):
        # ACTIVE -> TRIALING is not in SubscriptionService.LEGAL_TRANSITIONS.
        resp = self.client.patch(
            _url(self.subscription.id), {"status": "TRIALING"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)

    def test_illegal_transition_from_canceled_is_rejected(self):
        canceled = SubscriptionService.transition_status(
            self.subscription, Subscription.Status.CANCELED
        )
        resp = self.client.patch(
            _url(canceled.id), {"status": "ACTIVE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_illegal_transition_does_not_write_an_audit_row(self):
        self.client.patch(
            _url(self.subscription.id), {"status": "TRIALING"}, format="json"
        )
        self.assertEqual(AuditEvent.objects.count(), 0)


class SubscriptionMutationPlanChangeTests(SubscriptionMutationTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_valid_plan_change_succeeds_via_the_real_service(self):
        resp = self.client.patch(
            _url(self.subscription.id), {"plan_id": str(self.team.id)}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["plan"]["code"], "TEAM")
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_id, self.team.id)

    def test_plan_change_on_canceled_subscription_is_rejected(self):
        canceled = SubscriptionService.transition_status(
            self.subscription, Subscription.Status.CANCELED
        )
        resp = self.client.patch(
            _url(canceled.id), {"plan_id": str(self.team.id)}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_id", resp.data)

    def test_inactive_plan_is_rejected(self):
        resp = self.client.patch(
            _url(self.subscription.id),
            {"plan_id": str(self.inactive.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_id", resp.data)

    def test_nonexistent_plan_is_rejected(self):
        resp = self.client.patch(
            _url(self.subscription.id),
            {"plan_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SubscriptionMutationAuditTests(SubscriptionMutationTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_successful_status_transition_writes_exactly_one_critical_audit_row(self):
        self.client.patch(
            _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
        )
        self.assertEqual(AuditEvent.objects.count(), 1)
        event = AuditEvent.objects.get()
        self.assertTrue(event.is_critical)
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.action, "subscription.transitioned")
        self.assertEqual(event.target_type, "Subscription")
        self.assertEqual(event.target_id, str(self.subscription.id))
        self.assertEqual(event.metadata["from_status"], "ACTIVE")
        self.assertEqual(event.metadata["to_status"], "PAST_DUE")

    def test_successful_plan_change_writes_exactly_one_critical_audit_row_with_before_after(
        self,
    ):
        self.client.patch(
            _url(self.subscription.id), {"plan_id": str(self.team.id)}, format="json"
        )
        self.assertEqual(AuditEvent.objects.count(), 1)
        event = AuditEvent.objects.get()
        self.assertTrue(event.is_critical)
        self.assertEqual(event.action, "subscription.plan_changed")
        self.assertEqual(event.metadata["from_plan"], "PRO")
        self.assertEqual(event.metadata["to_plan"], "TEAM")

    def test_audit_metadata_never_contains_a_password_or_secret_or_raw_payload(self):
        self.client.patch(
            _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
        )
        event = AuditEvent.objects.get()
        forbidden = {"password", "secret", "token", "razorpay_key_secret", "raw_payload"}
        self.assertFalse(forbidden & set(event.metadata.keys()))

    def test_audit_write_failure_rolls_back_the_subscription_mutation(self):
        # The mutation and its critical audit write are one transaction — a
        # failure in the latter must undo the former, not leave a
        # half-applied, un-audited state change.
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.patch(
                    _url(self.subscription.id), {"status": "PAST_DUE"}, format="json"
                )

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_audit_write_failure_rolls_back_a_plan_change_too(self):
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.patch(
                    _url(self.subscription.id),
                    {"plan_id": str(self.team.id)},
                    format="json",
                )

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_id, self.pro.id)
        self.assertEqual(AuditEvent.objects.count(), 0)

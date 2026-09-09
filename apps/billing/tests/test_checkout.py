"""
Stage D2 — the subscription checkout flow, now provider-neutral.

Nothing here creates or mutates a local `Subscription` row; several tests assert
that absence explicitly. The gateway is exercised through the `get_gateway`
seam — `CheckoutStartTests` inject a `Mock(spec=PaymentGatewayAdapter)` for
precise call assertions; `CheckoutConfirmTests` run the REAL
`RazorpayGatewayAdapter.verify_checkout_signature` (a real HMAC against an
overridden secret) so the cryptographic check genuinely runs.
"""

import hashlib
import hmac
from unittest import mock

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.gateway import PaymentGatewayAdapter
from apps.billing.models import Plan, Subscription, SubscriptionCheckout
from apps.billing.services import CheckoutService
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

START_URL = "/api/subscriptions/current/checkout/"
CONFIRM_URL = "/api/subscriptions/current/confirm-checkout/"
PASSWORD = "correct-horse-staple-42"
API_SECRET = "rzp_secret_d2_test"


def _checkout_sig(payment_id, subscription_id, secret=API_SECRET):
    msg = f"{payment_id}|{subscription_id}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


class CheckoutTestBase(APITestCase):
    def setUp(self):
        self.pro = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD",
            interval=Plan.Interval.MONTHLY, external_plan_id="plan_PRO",
        )
        self.annual = Plan.objects.create(
            name="Yearly", code="YEARLY", price_cents=29000, currency="USD",
            interval=Plan.Interval.ANNUAL, external_plan_id="plan_YEARLY",
        )
        self.unsynced = Plan.objects.create(
            name="New", code="NEW", price_cents=100, currency="USD",
        )
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.owner = User.objects.create_user(
            email="owner@example.com", password=PASSWORD
        )
        Membership.objects.create(
            user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER
        )

    def _auth_owner(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.owner)}",
            HTTP_X_TENANT_ID=str(self.tenant.id),
        )


def _gateway(sub_id="sub_MOCK"):
    gw = mock.Mock(spec=PaymentGatewayAdapter)
    gw.create_subscription.return_value = sub_id
    return gw


class CheckoutStartTests(CheckoutTestBase):
    @mock.patch("apps.billing.services.get_gateway")
    def test_creates_gateway_subscription_without_a_local_subscription(
        self, get_gateway
    ):
        get_gateway.return_value = _gateway("sub_A")
        self._auth_owner()

        resp = self.client.post(START_URL, {"plan_id": str(self.pro.id)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        get_gateway.return_value.create_subscription.assert_called_once_with(
            self.tenant, self.pro
        )
        self.assertEqual(resp.data["razorpay_subscription_id"], "sub_A")
        checkout = SubscriptionCheckout.objects.get(tenant=self.tenant)
        self.assertEqual(checkout.external_subscription_id, "sub_A")
        self.assertEqual(checkout.status, SubscriptionCheckout.Status.CREATED)
        self.assertEqual(Subscription.objects.count(), 0)

    @mock.patch("apps.billing.services.get_gateway")
    def test_plan_without_external_plan_id_fails_cleanly(self, get_gateway):
        get_gateway.return_value = _gateway()
        self._auth_owner()

        resp = self.client.post(START_URL, {"plan_id": str(self.unsynced.id)})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_id", resp.data)
        get_gateway.return_value.create_subscription.assert_not_called()
        self.assertFalse(SubscriptionCheckout.objects.exists())
        self.assertEqual(Subscription.objects.count(), 0)

    @mock.patch("apps.billing.services.get_gateway")
    def test_response_contract_is_unchanged_by_the_adapter_refactor(
        self, get_gateway
    ):
        # payment-gateway-adapter-spec.md §3: the external JSON contract of the
        # checkout endpoints must be byte-identical before/after. The model
        # field is external_subscription_id now, but the JSON key stays.
        get_gateway.return_value = _gateway("sub_CONTRACT")
        self._auth_owner()

        resp = self.client.post(START_URL, {"plan_id": str(self.pro.id)})

        self.assertEqual(
            set(resp.data),
            {"razorpay_subscription_id", "plan", "status", "razorpay_key_id"},
        )
        self.assertEqual(set(resp.data["plan"]), {
            "id", "name", "code", "price_cents", "currency", "interval",
        })

    @mock.patch("apps.billing.services.get_gateway")
    def test_double_start_reuses_one_gateway_subscription(self, get_gateway):
        get_gateway.return_value = _gateway("sub_ONCE")
        self._auth_owner()

        first = self.client.post(START_URL, {"plan_id": str(self.pro.id)})
        second = self.client.post(START_URL, {"plan_id": str(self.pro.id)})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            first.data["razorpay_subscription_id"],
            second.data["razorpay_subscription_id"],
        )
        self.assertEqual(
            get_gateway.return_value.create_subscription.call_count, 1
        )
        self.assertEqual(SubscriptionCheckout.objects.count(), 1)

    @mock.patch("apps.billing.services.get_gateway")
    def test_starting_a_different_plan_while_one_is_in_flight_is_400(
        self, get_gateway
    ):
        get_gateway.return_value = _gateway("sub_C")
        self._auth_owner()

        self.client.post(START_URL, {"plan_id": str(self.pro.id)})
        resp = self.client.post(START_URL, {"plan_id": str(self.annual.id)})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            get_gateway.return_value.create_subscription.call_count, 1
        )

    def test_member_cannot_start_checkout_and_gets_403(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.owner)}",
        )
        member = User.objects.create_user(email="m@example.com", password=PASSWORD)
        Membership.objects.create(
            user=member, tenant=self.tenant, role=Membership.Role.MEMBER
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(member)}",
            HTTP_X_TENANT_ID=str(self.tenant.id),
        )

        resp = self.client.post(START_URL, {"plan_id": str(self.pro.id)})

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(SubscriptionCheckout.objects.exists())


@override_settings(PAYMENT_GATEWAY="razorpay", RAZORPAY_KEY_SECRET=API_SECRET)
class CheckoutConfirmTests(CheckoutTestBase):
    def setUp(self):
        super().setUp()
        self.checkout = SubscriptionCheckout.objects.create(
            tenant=self.tenant,
            plan=self.pro,
            external_subscription_id="sub_CONFIRM",
            status=SubscriptionCheckout.Status.CREATED,
        )
        self._auth_owner()

    def _confirm(self, payment_id="pay_1", subscription_id="sub_CONFIRM", signature=None):
        if signature is None:
            signature = _checkout_sig(payment_id, subscription_id)
        return self.client.post(
            CONFIRM_URL,
            {
                "razorpay_payment_id": payment_id,
                "razorpay_subscription_id": subscription_id,
                "razorpay_signature": signature,
            },
        )

    def test_valid_signature_marks_confirmed_and_creates_no_subscription(self):
        resp = self._confirm()

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, {"status": "processing"})
        self.checkout.refresh_from_db()
        self.assertEqual(
            self.checkout.status, SubscriptionCheckout.Status.CONFIRMED
        )
        self.assertEqual(Subscription.objects.count(), 0)

    def test_tampered_signature_is_400_and_changes_nothing(self):
        resp = self._confirm(signature="deadbeef")

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.checkout.refresh_from_db()
        self.assertEqual(
            self.checkout.status, SubscriptionCheckout.Status.CREATED
        )
        self.assertEqual(Subscription.objects.count(), 0)

    def test_signature_from_a_wrong_secret_is_400(self):
        resp = self._confirm(
            signature=_checkout_sig("pay_1", "sub_CONFIRM", "not-the-secret")
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_body_subscription_id_not_matching_our_record_is_400(self):
        resp = self._confirm(subscription_id="sub_SOMEONE_ELSE")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.checkout.refresh_from_db()
        self.assertEqual(
            self.checkout.status, SubscriptionCheckout.Status.CREATED
        )

    def test_confirm_with_no_checkout_in_progress_is_400(self):
        self.checkout.delete()
        resp = self._confirm()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class CheckoutServiceUnitTests(CheckoutTestBase):
    @mock.patch("apps.billing.services.get_gateway")
    def test_create_checkout_returns_the_row(self, get_gateway):
        get_gateway.return_value = _gateway("sub_U")

        checkout = CheckoutService.create_checkout(
            tenant=self.tenant, plan=self.pro
        )

        self.assertEqual(checkout.external_subscription_id, "sub_U")
        self.assertEqual(checkout.plan_id, self.pro.id)

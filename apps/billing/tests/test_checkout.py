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
import threading
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.gateway import PaymentGatewayAdapter, ProviderCheckout
from apps.billing.models import Plan, Subscription, SubscriptionCheckout, WebhookEvent
from datetime import timedelta

from django.utils import timezone

from apps.billing.gateway import EventType
from apps.billing.services import (
    CheckoutPlanMismatch,
    CheckoutService,
    WebhookProcessingService,
)
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


def _gateway(sub_id="sub_MOCK", provider="razorpay", session_token=""):
    gw = mock.Mock(spec=PaymentGatewayAdapter)
    gw.create_subscription.return_value = ProviderCheckout(
        provider=provider,
        external_subscription_id=sub_id,
        session_token=session_token,
        public_key="rzp_test_key",
        mode="sandbox",
    )
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

        # The original Razorpay keys are all still present and unchanged; the
        # provider-neutral ones sit alongside them for a non-Razorpay frontend.
        self.assertLessEqual(
            {"razorpay_subscription_id", "plan", "status", "razorpay_key_id"},
            set(resp.data),
        )
        self.assertEqual(
            set(resp.data),
            {
                "razorpay_subscription_id", "razorpay_key_id", "subscription_id",
                "provider", "session_token", "checkout_mode", "plan", "status",
            },
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


@override_settings(SUBSCRIPTION_CHECKOUT_STALE_AFTER_MINUTES=60)
class AbandonedCheckoutTests(CheckoutTestBase):
    """
    An in-flight checkout must not lock a workspace out of every other plan
    forever, and must not be discarded while it is still alive.
    """

    def _in_flight(self, plan, *, external_id="sub_OLD", status=None, age_minutes=0):
        checkout = SubscriptionCheckout.objects.create(
            tenant=self.tenant,
            plan=plan,
            external_subscription_id=external_id,
            status=status or SubscriptionCheckout.Status.CREATED,
        )
        if age_minutes:
            SubscriptionCheckout.objects.filter(pk=checkout.pk).update(
                updated_at=timezone.now() - timedelta(minutes=age_minutes)
            )
        return SubscriptionCheckout.objects.get(pk=checkout.pk)

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_valid_checkout_for_the_same_plan_is_reused(self, get_gateway):
        gateway = _gateway("sub_NEW")
        get_gateway.return_value = gateway
        self._in_flight(self.pro)

        checkout = CheckoutService.create_checkout(tenant=self.tenant, plan=self.pro)

        self.assertEqual(checkout.external_subscription_id, "sub_OLD")
        gateway.create_subscription.assert_not_called()

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_live_checkout_still_blocks_a_different_plan(self, get_gateway):
        gateway = _gateway("sub_NEW")
        get_gateway.return_value = gateway
        self._in_flight(self.pro, age_minutes=0)

        with self.assertRaises(CheckoutPlanMismatch):
            CheckoutService.create_checkout(tenant=self.tenant, plan=self.annual)
        gateway.create_subscription.assert_not_called()
        # Not even asked: inside the window, age alone settles it.
        gateway.checkout_is_abandoned.assert_not_called()

    @mock.patch("apps.billing.services.get_gateway")
    def test_an_old_checkout_the_provider_calls_live_still_blocks(self, get_gateway):
        # eNACH bank approval can take days — age alone must never discard it.
        gateway = _gateway("sub_NEW")
        gateway.checkout_is_abandoned.return_value = False
        get_gateway.return_value = gateway
        self._in_flight(self.pro, age_minutes=180)

        with self.assertRaises(CheckoutPlanMismatch):
            CheckoutService.create_checkout(tenant=self.tenant, plan=self.annual)
        gateway.create_subscription.assert_not_called()

    @mock.patch("apps.billing.services.get_gateway")
    def test_an_unreachable_provider_never_counts_as_abandoned(self, get_gateway):
        gateway = _gateway("sub_NEW")
        gateway.checkout_is_abandoned.return_value = None  # unknown
        get_gateway.return_value = gateway
        self._in_flight(self.pro, age_minutes=180)

        with self.assertRaises(CheckoutPlanMismatch):
            CheckoutService.create_checkout(tenant=self.tenant, plan=self.annual)
        gateway.create_subscription.assert_not_called()

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_confirmed_checkout_is_never_replaced(self, get_gateway):
        # Its authorisation succeeded; the activation webhook may be seconds away.
        gateway = _gateway("sub_NEW")
        gateway.checkout_is_abandoned.return_value = True
        get_gateway.return_value = gateway
        self._in_flight(
            self.pro, status=SubscriptionCheckout.Status.CONFIRMED, age_minutes=600
        )

        with self.assertRaises(CheckoutPlanMismatch):
            CheckoutService.create_checkout(tenant=self.tenant, plan=self.annual)
        gateway.create_subscription.assert_not_called()

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_stale_abandoned_checkout_is_replaced_by_the_new_plan(self, get_gateway):
        gateway = _gateway("sub_NEW")
        gateway.checkout_is_abandoned.return_value = True
        get_gateway.return_value = gateway
        self._in_flight(self.pro, age_minutes=180)

        checkout = CheckoutService.create_checkout(tenant=self.tenant, plan=self.annual)

        self.assertEqual(checkout.plan_id, self.annual.id)
        self.assertEqual(checkout.external_subscription_id, "sub_NEW")
        self.assertEqual(checkout.status, SubscriptionCheckout.Status.CREATED)
        # Still exactly one checkout for the tenant (OneToOne), re-pointed.
        self.assertEqual(SubscriptionCheckout.objects.count(), 1)

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_replaced_checkout_can_no_longer_activate_its_old_plan(self, get_gateway):
        gateway = _gateway("sub_NEW")
        gateway.checkout_is_abandoned.return_value = True
        get_gateway.return_value = gateway
        self._in_flight(self.pro, age_minutes=180)
        CheckoutService.create_checkout(tenant=self.tenant, plan=self.annual)

        # A delayed ACTIVATED for the ABANDONED mandate arrives.
        event = WebhookEvent.objects.create(
            external_event_id="evt_late",
            event_type=EventType.ACTIVATED,
            external_subscription_id="sub_OLD",
            raw_payload={},
        )
        WebhookProcessingService.process_event(event)

        # It matches no checkout, so it creates nothing — least of all a
        # subscription for the plan the customer walked away from.
        self.assertEqual(Subscription.objects.count(), 0)

    @mock.patch("apps.billing.services.get_gateway")
    def test_the_replacing_checkout_still_activates_normally(self, get_gateway):
        gateway = _gateway("sub_NEW")
        gateway.checkout_is_abandoned.return_value = True
        get_gateway.return_value = gateway
        self._in_flight(self.pro, age_minutes=180)
        CheckoutService.create_checkout(tenant=self.tenant, plan=self.annual)

        event = WebhookEvent.objects.create(
            external_event_id="evt_new",
            event_type=EventType.ACTIVATED,
            external_subscription_id="sub_NEW",
            raw_payload={},
        )
        WebhookProcessingService.process_event(event)

        subscription = Subscription.objects.get()
        self.assertEqual(subscription.plan_id, self.annual.id)
        self.assertEqual(subscription.tenant_id, self.tenant.id)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)


class CheckoutServiceUnitTests(CheckoutTestBase):
    @mock.patch("apps.billing.services.get_gateway")
    def test_create_checkout_returns_the_row(self, get_gateway):
        get_gateway.return_value = _gateway("sub_U")

        checkout = CheckoutService.create_checkout(
            tenant=self.tenant, plan=self.pro
        )

        self.assertEqual(checkout.external_subscription_id, "sub_U")
        self.assertEqual(checkout.plan_id, self.pro.id)


class ConcurrentCheckoutTests(TransactionTestCase):
    """
    The real concurrency guarantee, on real connections: `create_checkout`'s
    `select_for_update()` must serialise two simultaneous starts so the gateway
    is asked for a subscription exactly ONCE. TransactionTestCase (not
    TestCase), because the guarantee is about COMMITTED rows across connections.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrent", slug="concurrent")
        self.owner = User.objects.create_user(
            email="concurrent@example.com", password=PASSWORD
        )
        Membership.objects.create(
            user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER
        )
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2000, currency="INR",
            interval="MONTHLY", external_plan_id="plan_EXT",
        )

    def test_two_simultaneous_starts_create_one_gateway_subscription(self):
        calls = []
        barrier = threading.Barrier(2)

        def create_subscription(tenant, plan):
            calls.append(plan.code)
            return ProviderCheckout(
                provider="mock",
                external_subscription_id=f"sub_{len(calls)}",
                session_token="sess",
                public_key="",
                mode="sandbox",
            )

        gateway = mock.Mock(spec=PaymentGatewayAdapter)
        gateway.create_subscription.side_effect = create_subscription
        results = []

        def start():
            barrier.wait()
            try:
                with mock.patch("apps.billing.services.get_gateway", return_value=gateway):
                    results.append(
                        CheckoutService.create_checkout(
                            tenant=self.tenant, plan=self.plan
                        ).external_subscription_id
                    )
            except Exception as exc:  # surfaced in the assertions below
                results.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=start) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(calls), 1, f"gateway called {len(calls)}x: {results}")
        self.assertEqual(SubscriptionCheckout.objects.count(), 1)
        self.assertEqual(set(results), {"sub_1"})

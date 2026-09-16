"""
Cashfree Subscriptions end to end inside the billing domain: an owner's
checkout, the authorisation webhook that activates the subscription, and the
recurring charges that renew it — all through the real URL, the real adapter's
signature check and the existing `SubscriptionService` transitions.

The point of these tests is that switching providers changed only the adapter:
subscription state still moves exclusively through the service, a redelivered
webhook still settles nothing twice, and a browser's report still activates
nothing by itself.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan, Subscription, SubscriptionCheckout, WebhookEvent
from apps.properties.tests.factories import make_workspace

SECRET = "sub-fixture-secret"
WEBHOOK_URL = "/api/webhooks/cashfree/subscriptions/"
START_URL = "/api/subscriptions/current/checkout/"
CONFIRM_URL = "/api/subscriptions/current/confirm-checkout/"

CASHFREE = dict(
    PAYMENT_GATEWAY="cashfree",
    CASHFREE_SUBSCRIPTION_CLIENT_ID="sub_app_id",
    CASHFREE_SUBSCRIPTION_CLIENT_SECRET=SECRET,
    CASHFREE_SUBSCRIPTION_ENVIRONMENT="sandbox",
    CASHFREE_SUBSCRIPTION_WEBHOOK_TOLERANCE_SECONDS=300,
    FRONTEND_URL="https://app.example.com",
)

SUBSCRIPTION_ID = "tnrsub_live"


def body(event_type, *, status="ACTIVE", event_time="2026-09-16T10:00:00+05:30", next_date="2026-10-16T00:00:00+05:30"):
    payload = {
        "type": event_type,
        "event_time": event_time,
        "data": {
            "subscription_details": {
                "subscription_id": SUBSCRIPTION_ID,
                "subscription_status": status,
                "next_schedule_date": next_date,
            },
            "payment_details": {
                "cf_payment_id": "5114",
                "payment_amount": 2000.0,
                "payment_time": event_time,
            },
        },
    }
    return json.dumps(payload).encode()


def headers(raw, secret=SECRET, ts=None):
    ts = str(ts or int(time.time() * 1000))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + raw, hashlib.sha256).digest()).decode()
    return {"HTTP_X_WEBHOOK_SIGNATURE": sig, "HTTP_X_WEBHOOK_TIMESTAMP": ts}


@override_settings(**CASHFREE)
class CashfreeSubscriptionWebhookTests(APITestCase):
    def setUp(self):
        self.tenant, self.owner = make_workspace("cf-flow")
        self.plan = Plan.objects.create(
            code="PRO", name="Pro", price_cents=200_000, currency="INR",
            interval="MONTHLY", external_plan_id="tenora_pro",
        )
        SubscriptionCheckout.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            external_subscription_id=SUBSCRIPTION_ID,
            provider="cashfree",
            session_token="sess_abc",
        )

    def post(self, raw, **extra):
        return self.client.post(
            WEBHOOK_URL, data=raw, content_type="application/json", **extra
        )

    def test_an_authorised_mandate_activates_the_subscription(self):
        raw = body("SUBSCRIPTION_STATUS_CHANGED")
        resp = self.post(raw, **headers(raw))

        self.assertEqual(resp.status_code, 200)
        subscription = Subscription.objects.get()
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(subscription.tenant_id, self.tenant.id)
        self.assertEqual(subscription.plan_id, self.plan.id)
        self.assertEqual(subscription.external_subscription_id, SUBSCRIPTION_ID)

    def test_an_unsigned_or_tampered_delivery_changes_nothing(self):
        raw = body("SUBSCRIPTION_STATUS_CHANGED")
        cases = {
            "no signature": {},
            "wrong secret": headers(raw, secret="not-it"),
            "stale": headers(raw, ts=int((time.time() - 3600) * 1000)),
        }
        for name, extra in cases.items():
            with self.subTest(name):
                resp = self.post(raw, **extra)
                self.assertEqual(resp.status_code, 400)
        # Tampering with the body after signing is caught too.
        signed = headers(raw)
        resp = self.post(raw.replace(b"ACTIVE", b"ON_HOLD"), **signed)
        self.assertEqual(resp.status_code, 400)

        self.assertEqual(WebhookEvent.objects.count(), 0)
        self.assertEqual(Subscription.objects.count(), 0)

    def test_a_redelivered_activation_is_stored_once_and_applied_once(self):
        raw = body("SUBSCRIPTION_STATUS_CHANGED")
        first = self.post(raw, **headers(raw))
        # Cashfree retries with the SAME body; only the timestamp header differs.
        second = self.post(raw, **headers(raw))

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_a_recurring_charge_renews_once_however_often_it_is_delivered(self):
        activation = body("SUBSCRIPTION_STATUS_CHANGED")
        self.post(activation, **headers(activation))

        charge = body(
            "SUBSCRIPTION_PAYMENT_SUCCESS",
            event_time="2026-10-16T10:00:00+05:30",
            next_date="2026-11-16T00:00:00+05:30",
        )
        self.post(charge, **headers(charge))
        renewed = Subscription.objects.get()
        period_end = renewed.current_period_end

        self.post(charge, **headers(charge))  # duplicate renewal delivery
        renewed.refresh_from_db()

        self.assertEqual(renewed.status, Subscription.Status.ACTIVE)
        self.assertEqual(renewed.current_period_end, period_end)
        self.assertEqual(WebhookEvent.objects.count(), 2)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_a_failed_recurring_charge_moves_the_subscription_to_past_due(self):
        activation = body("SUBSCRIPTION_STATUS_CHANGED")
        self.post(activation, **headers(activation))
        failure = body("SUBSCRIPTION_PAYMENT_FAILED", event_time="2026-10-16T10:00:00+05:30")
        self.post(failure, **headers(failure))

        self.assertEqual(Subscription.objects.get().status, Subscription.Status.PAST_DUE)

    def test_a_cancelled_mandate_cancels_the_subscription(self):
        activation = body("SUBSCRIPTION_STATUS_CHANGED")
        self.post(activation, **headers(activation))
        cancelled = body(
            "SUBSCRIPTION_STATUS_CHANGED", status="CUSTOMER_CANCELLED",
            event_time="2026-10-20T10:00:00+05:30",
        )
        self.post(cancelled, **headers(cancelled))

        self.assertEqual(Subscription.objects.get().status, Subscription.Status.CANCELED)

    def test_an_unknown_subscription_is_recorded_but_activates_nothing(self):
        SubscriptionCheckout.objects.all().delete()
        raw = body("SUBSCRIPTION_STATUS_CHANGED")
        resp = self.post(raw, **headers(raw))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Subscription.objects.count(), 0)


@override_settings(**CASHFREE)
class CashfreeCheckoutEndpointTests(APITestCase):
    def setUp(self):
        self.tenant, self.owner = make_workspace("cf-checkout")
        self.owner.phone = "9876543210"
        self.owner.save(update_fields=["phone"])
        self.plan = Plan.objects.create(
            code="PRO", name="Pro", price_cents=200_000, currency="INR",
            interval="MONTHLY", external_plan_id="tenora_pro",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.owner)}",
            HTTP_X_TENANT_ID=str(self.tenant.id),
        )

    def _adapter(self, **overrides):
        gateway = mock.Mock()
        gateway.create_subscription.return_value = __import__(
            "apps.billing.gateway", fromlist=["ProviderCheckout"]
        ).ProviderCheckout(
            provider="cashfree",
            external_subscription_id=SUBSCRIPTION_ID,
            session_token="sess_abc",
            public_key="",
            mode="sandbox",
        )
        for key, value in overrides.items():
            setattr(gateway, key, value)
        return gateway

    @mock.patch("apps.billing.services.get_gateway")
    def test_checkout_start_returns_a_session_token_and_no_secret(self, get_gateway):
        get_gateway.return_value = self._adapter()

        resp = self.client.post(START_URL, {"plan_id": str(self.plan.id)})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["provider"], "cashfree")
        self.assertEqual(resp.data["session_token"], "sess_abc")
        self.assertEqual(resp.data["subscription_id"], SUBSCRIPTION_ID)
        self.assertEqual(resp.data["checkout_mode"], "sandbox")
        self.assertNotIn(SECRET, json.dumps(resp.data))
        # Still no local subscription: only the webhook creates one.
        self.assertEqual(Subscription.objects.count(), 0)
        self.assertEqual(
            SubscriptionCheckout.objects.get().session_token, "sess_abc"
        )

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_second_click_reuses_the_same_mandate(self, get_gateway):
        gateway = self._adapter()
        get_gateway.return_value = gateway

        first = self.client.post(START_URL, {"plan_id": str(self.plan.id)})
        second = self.client.post(START_URL, {"plan_id": str(self.plan.id)})

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(gateway.create_subscription.call_count, 1)
        self.assertEqual(second.data["session_token"], "sess_abc")

    @mock.patch("apps.billing.services.get_gateway")
    def test_an_owner_without_a_phone_is_told_what_to_fix(self, get_gateway):
        from apps.billing.gateway import SubscriberContactRequired

        gateway = self._adapter()
        gateway.create_subscription.side_effect = SubscriberContactRequired(
            "Add a mobile number in Settings before subscribing."
        )
        get_gateway.return_value = gateway

        resp = self.client.post(START_URL, {"plan_id": str(self.plan.id)})

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "subscriber_contact_required")
        self.assertFalse(SubscriptionCheckout.objects.exists())

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_provider_outage_is_503_and_leaves_no_half_checkout(self, get_gateway):
        from apps.billing.gateway import ProviderUnavailable

        gateway = self._adapter()
        gateway.create_subscription.side_effect = ProviderUnavailable("boom")
        get_gateway.return_value = gateway

        resp = self.client.post(START_URL, {"plan_id": str(self.plan.id)})

        self.assertEqual(resp.status_code, 503)
        self.assertFalse(
            SubscriptionCheckout.objects.exclude(external_subscription_id=None).exists()
        )

    @mock.patch("apps.billing.services.get_gateway")
    def test_the_browsers_report_is_checked_with_the_provider_and_never_activates(
        self, get_gateway
    ):
        gateway = self._adapter()
        get_gateway.return_value = gateway
        self.client.post(START_URL, {"plan_id": str(self.plan.id)})

        gateway.confirm_checkout_report.return_value = True
        resp = self.client.post(CONFIRM_URL, {"subscription_id": SUBSCRIPTION_ID})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {"status": "processing"})
        gateway.confirm_checkout_report.assert_called_once()
        self.assertEqual(
            SubscriptionCheckout.objects.get().status,
            SubscriptionCheckout.Status.CONFIRMED,
        )
        # UI feedback only — the subscription still does not exist.
        self.assertEqual(Subscription.objects.count(), 0)

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_report_the_provider_does_not_confirm_is_refused(self, get_gateway):
        gateway = self._adapter()
        get_gateway.return_value = gateway
        self.client.post(START_URL, {"plan_id": str(self.plan.id)})

        gateway.confirm_checkout_report.return_value = False
        resp = self.client.post(CONFIRM_URL, {"subscription_id": SUBSCRIPTION_ID})

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            SubscriptionCheckout.objects.get().status,
            SubscriptionCheckout.Status.CREATED,
        )

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_report_for_someone_elses_subscription_is_refused(self, get_gateway):
        gateway = self._adapter()
        get_gateway.return_value = gateway
        self.client.post(START_URL, {"plan_id": str(self.plan.id)})

        gateway.confirm_checkout_report.return_value = True
        resp = self.client.post(CONFIRM_URL, {"subscription_id": "tnrsub_someone_else"})

        self.assertEqual(resp.status_code, 400)
        gateway.confirm_checkout_report.assert_not_called()


@override_settings(**CASHFREE)
class PlanMappingTests(TestCase):
    def test_tenora_plan_limits_are_untouched_by_the_provider_mapping(self):
        plan = Plan.objects.create(
            code="BASIC", name="Basic", price_cents=50_000, currency="INR",
            interval="MONTHLY", max_workspaces=2, max_members_per_workspace=10,
        )
        session = mock.Mock()
        session.request.return_value = type(
            "R", (), {"status_code": 200, "content": b"{}", "json": lambda self: {"plan_id": "tenora_basic"}}
        )()
        from apps.billing.gateway.cashfree import CashfreeSubscriptionGatewayAdapter

        external_id = CashfreeSubscriptionGatewayAdapter(session=session).create_plan(plan)
        plan.refresh_from_db()

        self.assertEqual(external_id, "tenora_basic")
        # Mirroring money at the provider changes no entitlement locally.
        self.assertEqual(plan.max_workspaces, 2)
        self.assertEqual(plan.max_members_per_workspace, 10)
        self.assertEqual(plan.price_cents, 50_000)

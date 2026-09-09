"""
RazorpayGatewayAdapter — the Razorpay-specific request bodies, HMAC
constructions, and event-name mapping, all relocated here from D1/D2's
services (payment-gateway-adapter-spec.md §4.2 / §9). The SDK client is mocked;
the HMACs are real.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings

import razorpay

from apps.billing.gateway import EventType, WebhookParseError
from apps.billing.gateway.base import (
    ProviderSubscriptionStatus,
    ProviderUnavailable,
)
from apps.billing.gateway.razorpay import RazorpayGatewayAdapter

WEBHOOK_SECRET = "whsec_adapter_test"
API_SECRET = "apisecret_adapter_test"


def _plan(**over):
    fields = {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Pro",
        "code": "PRO",
        "price_cents": 2900,
        "currency": "USD",
        "interval": "MONTHLY",
        "external_plan_id": "plan_EXT",
    }
    fields.update(over)
    return SimpleNamespace(**fields)


class RazorpayCreateCallsTests(SimpleTestCase):
    def setUp(self):
        self.adapter = RazorpayGatewayAdapter()
        self.client = mock.Mock()
        patcher = mock.patch.object(
            RazorpayGatewayAdapter, "_client", return_value=self.client
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_plan_maps_local_fields(self):
        self.client.plan.create.return_value = {"id": "plan_NEW"}

        result = self.adapter.create_plan(_plan())

        self.assertEqual(result, "plan_NEW")
        body = self.client.plan.create.call_args.args[0]
        self.assertEqual(body["period"], "monthly")
        self.assertEqual(body["interval"], 1)
        self.assertEqual(body["item"]["amount"], 2900)  # price_cents verbatim
        self.assertEqual(body["item"]["currency"], "USD")
        self.assertEqual(
            body["notes"],
            {"local_plan_id": "11111111-1111-1111-1111-111111111111"},
        )

    def test_create_plan_annual_uses_yearly(self):
        self.client.plan.create.return_value = {"id": "plan_Y"}
        self.adapter.create_plan(_plan(interval="ANNUAL"))
        self.assertEqual(
            self.client.plan.create.call_args.args[0]["period"], "yearly"
        )

    def test_create_subscription_maps_fields_and_total_count(self):
        self.client.subscription.create.return_value = {"id": "sub_NEW"}
        tenant = SimpleNamespace(id="tenant-9")

        result = self.adapter.create_subscription(tenant, _plan())

        self.assertEqual(result, "sub_NEW")
        body = self.client.subscription.create.call_args.args[0]
        self.assertEqual(body["plan_id"], "plan_EXT")
        self.assertEqual(body["total_count"], 120)  # MONTHLY ≈ 10 years
        self.assertEqual(body["customer_notify"], 1)
        self.assertEqual(body["notes"], {"tenant_id": "tenant-9"})

    def test_create_subscription_annual_total_count(self):
        self.client.subscription.create.return_value = {"id": "sub_Y"}
        self.adapter.create_subscription(
            SimpleNamespace(id="t"), _plan(interval="ANNUAL")
        )
        self.assertEqual(
            self.client.subscription.create.call_args.args[0]["total_count"], 10
        )


@override_settings(
    RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET, RAZORPAY_KEY_SECRET=API_SECRET
)
class RazorpaySignatureTests(SimpleTestCase):
    def setUp(self):
        self.adapter = RazorpayGatewayAdapter()

    def test_webhook_signature_valid(self):
        body = b'{"event":"subscription.activated"}'
        sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(
            self.adapter.verify_webhook_signature(
                {"X-Razorpay-Signature": sig}, body
            )
        )

    def test_webhook_signature_tampered_or_missing(self):
        body = b'{"event":"subscription.activated"}'
        self.assertFalse(
            self.adapter.verify_webhook_signature(
                {"X-Razorpay-Signature": "nope"}, body
            )
        )
        self.assertFalse(self.adapter.verify_webhook_signature({}, body))

    @override_settings(RAZORPAY_WEBHOOK_SECRET="")
    def test_webhook_signature_no_secret_configured(self):
        body = b"{}"
        sig = hmac.new(b"", body, hashlib.sha256).hexdigest()
        self.assertFalse(
            self.adapter.verify_webhook_signature(
                {"X-Razorpay-Signature": sig}, body
            )
        )

    def test_checkout_signature_valid_payment_id_first(self):
        msg = b"pay_1|sub_1"
        sig = hmac.new(API_SECRET.encode(), msg, hashlib.sha256).hexdigest()
        self.assertTrue(
            self.adapter.verify_checkout_signature("pay_1", "sub_1", sig)
        )
        # order matters — the reversed message must not verify
        rev = hmac.new(
            API_SECRET.encode(), b"sub_1|pay_1", hashlib.sha256
        ).hexdigest()
        self.assertFalse(
            self.adapter.verify_checkout_signature("pay_1", "sub_1", rev)
        )

    def test_checkout_signature_tampered_or_missing(self):
        self.assertFalse(
            self.adapter.verify_checkout_signature("p", "s", "deadbeef")
        )
        self.assertFalse(self.adapter.verify_checkout_signature("p", "s", ""))


class RazorpayParseWebhookEventTests(SimpleTestCase):
    def setUp(self):
        self.adapter = RazorpayGatewayAdapter()

    def _parse(self, payload, event_id="evt_1"):
        return self.adapter.parse_webhook_event(
            {"X-Razorpay-Event-Id": event_id}, json.dumps(payload).encode()
        )

    def test_event_name_mapping(self):
        cases = {
            "subscription.activated": EventType.ACTIVATED,
            "subscription.charged": EventType.CHARGED,
            "subscription.cancelled": EventType.CANCELLED,
            "subscription.pending": EventType.PAYMENT_TROUBLE,
            "subscription.halted": EventType.PAYMENT_TROUBLE,
            "subscription.authenticated": EventType.UNKNOWN,
            "subscription.completed": EventType.UNKNOWN,
            "payment.failed": EventType.UNKNOWN,
            "something.weird": EventType.UNKNOWN,
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                ne = self._parse({"event": name})
                self.assertEqual(ne.event_type, expected)

    def test_extracts_ids(self):
        ne = self._parse(
            {
                "event": "subscription.charged",
                "payload": {"subscription": {"entity": {"id": "sub_XYZ"}}},
            },
            event_id="evt_ABC",
        )
        self.assertEqual(ne.external_event_id, "evt_ABC")
        self.assertEqual(ne.external_subscription_id, "sub_XYZ")

    def test_no_subscription_entity_gives_none(self):
        ne = self._parse({"event": "subscription.activated"})
        self.assertIsNone(ne.external_subscription_id)

    def test_extracts_and_converts_real_period_dates(self):
        start_ts, end_ts = 1_726_000_000, 1_728_592_000
        ne = self._parse(
            {
                "event": "subscription.charged",
                "payload": {
                    "subscription": {
                        "entity": {
                            "id": "sub_1",
                            "current_start": start_ts,
                            "current_end": end_ts,
                        }
                    }
                },
            }
        )
        self.assertEqual(
            ne.period_start, datetime.fromtimestamp(start_ts, tz=timezone.utc)
        )
        self.assertEqual(
            ne.period_end, datetime.fromtimestamp(end_ts, tz=timezone.utc)
        )
        self.assertEqual(ne.period_start.tzinfo, timezone.utc)

    def test_period_dates_absent_from_payload_are_none(self):
        ne = self._parse(
            {
                "event": "subscription.charged",
                "payload": {"subscription": {"entity": {"id": "sub_1"}}},
            }
        )
        self.assertIsNone(ne.period_start)
        self.assertIsNone(ne.period_end)

    def test_missing_event_id_header_is_empty_string(self):
        ne = self.adapter.parse_webhook_event({}, b'{"event":"x"}')
        self.assertEqual(ne.external_event_id, "")

    def test_raw_payload_retained(self):
        payload = {"event": "subscription.activated", "foo": "bar"}
        ne = self._parse(payload)
        self.assertEqual(ne.raw_payload, payload)

    def test_bad_json_raises_parse_error(self):
        with self.assertRaises(WebhookParseError):
            self.adapter.parse_webhook_event({}, b"not json")

    def test_non_object_json_raises_parse_error(self):
        with self.assertRaises(WebhookParseError):
            self.adapter.parse_webhook_event({}, b"[1, 2, 3]")


class RazorpayFetchSubscriptionStateTests(SimpleTestCase):
    """D8 — the read-only provider-state lookup. The SDK client is mocked."""

    def setUp(self):
        self.adapter = RazorpayGatewayAdapter()
        self.client = mock.Mock()
        patcher = mock.patch.object(
            RazorpayGatewayAdapter, "_client", return_value=self.client
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _entity(self, **over):
        entity = {"id": "sub_1", "status": "active", "plan_id": "plan_EXT"}
        entity.update(over)
        return entity

    def test_maps_each_razorpay_status(self):
        cases = {
            "created": ProviderSubscriptionStatus.PENDING,
            "authenticated": ProviderSubscriptionStatus.PENDING,
            "active": ProviderSubscriptionStatus.ACTIVE,
            "pending": ProviderSubscriptionStatus.PAST_DUE,
            "halted": ProviderSubscriptionStatus.PAST_DUE,
            "cancelled": ProviderSubscriptionStatus.CANCELED,
            "completed": ProviderSubscriptionStatus.CANCELED,
            "expired": ProviderSubscriptionStatus.CANCELED,
            "some_new_status": ProviderSubscriptionStatus.UNKNOWN,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.client.subscription.fetch.return_value = self._entity(
                    status=raw
                )
                state = self.adapter.fetch_subscription_state("sub_1")
                self.assertEqual(state.status, expected)
                self.assertEqual(state.raw_status, raw)

    def test_carries_plan_id(self):
        self.client.subscription.fetch.return_value = self._entity(
            plan_id="plan_ABC"
        )
        state = self.adapter.fetch_subscription_state("sub_1")
        self.assertEqual(state.external_plan_id, "plan_ABC")

    def test_is_read_only(self):
        self.client.subscription.fetch.return_value = self._entity()
        self.adapter.fetch_subscription_state("sub_1")
        self.client.subscription.fetch.assert_called_once_with("sub_1")
        self.client.subscription.edit.assert_not_called()
        self.client.subscription.cancel.assert_not_called()
        self.client.subscription.create.assert_not_called()
        self.client.subscription.pause.assert_not_called()

    def test_clear_not_found_returns_none(self):
        self.client.subscription.fetch.side_effect = razorpay.errors.BadRequestError(
            "The id provided does not exist"
        )
        self.assertIsNone(self.adapter.fetch_subscription_state("sub_gone"))

    def test_ambiguous_bad_request_is_provider_unavailable(self):
        self.client.subscription.fetch.side_effect = razorpay.errors.BadRequestError(
            "Authentication failed"
        )
        with self.assertRaises(ProviderUnavailable):
            self.adapter.fetch_subscription_state("sub_1")

    def test_server_error_is_provider_unavailable(self):
        self.client.subscription.fetch.side_effect = razorpay.errors.ServerError(
            "Internal Server Error"
        )
        with self.assertRaises(ProviderUnavailable):
            self.adapter.fetch_subscription_state("sub_1")

    def test_network_error_is_provider_unavailable(self):
        self.client.subscription.fetch.side_effect = ConnectionError("no route")
        with self.assertRaises(ProviderUnavailable):
            self.adapter.fetch_subscription_state("sub_1")

    def test_unexpected_shape_is_provider_unavailable(self):
        self.client.subscription.fetch.return_value = ["not", "a", "dict"]
        with self.assertRaises(ProviderUnavailable):
            self.adapter.fetch_subscription_state("sub_1")

"""
MockGatewayAdapter — deterministic, network-free, configurable
(payment-gateway-adapter-spec.md §4.3 / §9).
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.billing.gateway import EventType, MockGatewayAdapter, WebhookParseError
from apps.billing.gateway.base import (
    ProviderSubscriptionState,
    ProviderSubscriptionStatus,
    ProviderUnavailable,
)


class MockGatewayAdapterTests(SimpleTestCase):
    def setUp(self):
        self.adapter = MockGatewayAdapter()

    def test_create_plan_is_deterministic_per_code(self):
        plan = SimpleNamespace(code="PRO")
        self.assertEqual(self.adapter.create_plan(plan), "mock_plan_PRO")
        self.assertEqual(self.adapter.create_plan(plan), "mock_plan_PRO")

    def test_create_subscription_is_deterministic_per_tenant(self):
        tenant = SimpleNamespace(id="tenant-42")
        plan = SimpleNamespace(code="PRO")
        self.assertEqual(
            self.adapter.create_subscription(tenant, plan), "mock_sub_tenant-42"
        )

    def test_signature_flags_default_true(self):
        self.assertTrue(self.adapter.verify_webhook_signature({}, b"{}"))
        self.assertTrue(self.adapter.verify_checkout_signature("p", "s", "x"))

    def test_signature_flags_configurable(self):
        adapter = MockGatewayAdapter(
            webhook_signature_valid=False, checkout_signature_valid=False
        )
        self.assertFalse(adapter.verify_webhook_signature({}, b"{}"))
        self.assertFalse(adapter.verify_checkout_signature("p", "s", "x"))

    def test_parse_webhook_event_normal(self):
        ne = self.adapter.parse_webhook_event(
            {"X-Mock-Event-Id": "evt_7"},
            json.dumps({"type": "CHARGED", "subscription_id": "sub_1"}).encode(),
        )
        self.assertEqual(ne.event_type, EventType.CHARGED)
        self.assertEqual(ne.external_event_id, "evt_7")
        self.assertEqual(ne.external_subscription_id, "sub_1")

    def test_parse_webhook_event_carries_period_dates_when_present(self):
        start_ts, end_ts = 1_726_000_000, 1_728_592_000
        ne = self.adapter.parse_webhook_event(
            {"X-Mock-Event-Id": "e"},
            json.dumps(
                {
                    "type": "CHARGED",
                    "subscription_id": "sub_1",
                    "period_start": start_ts,
                    "period_end": end_ts,
                }
            ).encode(),
        )
        self.assertEqual(
            ne.period_start, datetime.fromtimestamp(start_ts, tz=timezone.utc)
        )
        self.assertEqual(
            ne.period_end, datetime.fromtimestamp(end_ts, tz=timezone.utc)
        )
        self.assertEqual(ne.period_start.tzinfo, timezone.utc)

    def test_parse_webhook_event_period_dates_default_to_none(self):
        ne = self.adapter.parse_webhook_event(
            {"X-Mock-Event-Id": "e"},
            json.dumps({"type": "CHARGED", "subscription_id": "sub_1"}).encode(),
        )
        self.assertIsNone(ne.period_start)
        self.assertIsNone(ne.period_end)

    def test_parse_webhook_event_unknown_type(self):
        ne = self.adapter.parse_webhook_event(
            {"X-Mock-Event-Id": "e"}, b'{"type": "banana"}'
        )
        self.assertEqual(ne.event_type, EventType.UNKNOWN)

    def test_parse_webhook_event_bad_body(self):
        with self.assertRaises(WebhookParseError):
            self.adapter.parse_webhook_event({}, b"nope")
        with self.assertRaises(WebhookParseError):
            self.adapter.parse_webhook_event({}, b"[1,2,3]")

    # -- D8: fetch_subscription_state -------------------------------------

    def test_fetch_subscription_state_returns_configured_state(self):
        adapter = MockGatewayAdapter(
            subscription_states={
                "sub_1": {
                    "status": "ACTIVE",
                    "raw_status": "active",
                    "external_plan_id": "plan_x",
                }
            }
        )
        state = adapter.fetch_subscription_state("sub_1")
        self.assertIsInstance(state, ProviderSubscriptionState)
        self.assertEqual(state.status, ProviderSubscriptionStatus.ACTIVE)
        self.assertEqual(state.raw_status, "active")
        self.assertEqual(state.external_plan_id, "plan_x")

    def test_fetch_subscription_state_unknown_id_is_none(self):
        self.assertIsNone(
            MockGatewayAdapter().fetch_subscription_state("sub_absent")
        )

    def test_fetch_subscription_state_configured_none_is_not_found(self):
        adapter = MockGatewayAdapter(subscription_states={"sub_1": None})
        self.assertIsNone(adapter.fetch_subscription_state("sub_1"))

    def test_fetch_subscription_state_configured_exception_is_raised(self):
        adapter = MockGatewayAdapter(
            subscription_states={"sub_1": ProviderUnavailable("boom")}
        )
        with self.assertRaises(ProviderUnavailable):
            adapter.fetch_subscription_state("sub_1")

    def test_subscription_states_defaults_keep_existing_ctor_calls_working(self):
        # No kwarg at all — the pre-D8 construction path.
        self.assertEqual(MockGatewayAdapter().subscription_states, {})

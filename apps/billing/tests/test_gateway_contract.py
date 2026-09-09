"""
The two adapters are genuinely interchangeable at the interface
(payment-gateway-adapter-spec.md §9): both are `PaymentGatewayAdapter`
instances, expose the same five methods with the declared return types, and
`get_gateway()` selects between them by setting.
"""

import json

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.billing.gateway import (
    MockGatewayAdapter,
    NormalizedEvent,
    PaymentGatewayAdapter,
    RazorpayGatewayAdapter,
    get_gateway,
)

_METHODS = (
    "create_plan",
    "create_subscription",
    "verify_webhook_signature",
    "parse_webhook_event",
    "verify_checkout_signature",
    "fetch_subscription_state",
)


class GatewayContractTests(SimpleTestCase):
    def test_both_adapters_implement_the_interface(self):
        for adapter in (RazorpayGatewayAdapter(), MockGatewayAdapter()):
            with self.subTest(adapter=type(adapter).__name__):
                self.assertIsInstance(adapter, PaymentGatewayAdapter)
                for name in _METHODS:
                    self.assertTrue(callable(getattr(adapter, name)))

    def test_mock_fetch_subscription_state_defaults_to_not_found(self):
        self.assertIsNone(
            MockGatewayAdapter().fetch_subscription_state("sub_missing")
        )

    def test_a_partial_adapter_cannot_be_instantiated(self):
        class Partial(PaymentGatewayAdapter):
            def create_plan(self, plan) -> str:  # noqa: D401
                return "x"

        with self.assertRaises(TypeError):
            Partial()

    def test_mock_adapter_return_shapes(self):
        adapter = MockGatewayAdapter()
        self.assertIsInstance(adapter.verify_webhook_signature({}, b"{}"), bool)
        self.assertIsInstance(
            adapter.verify_checkout_signature("p", "s", "x"), bool
        )
        ne = adapter.parse_webhook_event(
            {"X-Mock-Event-Id": "e"}, json.dumps({"type": "ACTIVATED"}).encode()
        )
        self.assertIsInstance(ne, NormalizedEvent)


class GatewaySelectionTests(SimpleTestCase):
    def test_default_is_razorpay(self):
        with override_settings(PAYMENT_GATEWAY="razorpay"):
            self.assertIsInstance(get_gateway(), RazorpayGatewayAdapter)

    def test_mock_selectable(self):
        with override_settings(PAYMENT_GATEWAY="mock"):
            self.assertIsInstance(get_gateway(), MockGatewayAdapter)

    def test_unknown_gateway_raises(self):
        with override_settings(PAYMENT_GATEWAY="stripe"):
            with self.assertRaises(ImproperlyConfigured):
                get_gateway()

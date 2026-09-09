"""
Payment gateway adapter package (docs/payment-gateway-adapter-spec.md).

    from apps.billing.gateway import get_gateway
    gateway = get_gateway()          # the active adapter, per settings.PAYMENT_GATEWAY

`get_gateway()` is the single construction point — the same discipline D1 used
for `razorpay_client.get_client()`. Tests either `@override_settings(
PAYMENT_GATEWAY="mock")` or patch `apps.billing.services.get_gateway` /
`apps.billing.views.get_gateway` with a configured adapter.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.billing.gateway.base import (
    EventType,
    NormalizedEvent,
    PaymentGatewayAdapter,
    ProviderSubscriptionState,
    ProviderSubscriptionStatus,
    ProviderUnavailable,
    WebhookParseError,
)
from apps.billing.gateway.mock import MockGatewayAdapter
from apps.billing.gateway.razorpay import RazorpayGatewayAdapter

__all__ = [
    "EventType",
    "NormalizedEvent",
    "PaymentGatewayAdapter",
    "ProviderSubscriptionState",
    "ProviderSubscriptionStatus",
    "ProviderUnavailable",
    "WebhookParseError",
    "MockGatewayAdapter",
    "RazorpayGatewayAdapter",
    "get_gateway",
]

_ADAPTERS = {
    "razorpay": RazorpayGatewayAdapter,
    "mock": MockGatewayAdapter,
}


def get_gateway() -> PaymentGatewayAdapter:
    name = getattr(settings, "PAYMENT_GATEWAY", "razorpay")
    try:
        return _ADAPTERS[name]()
    except KeyError:
        raise ImproperlyConfigured(
            f"PAYMENT_GATEWAY={name!r} is not one of {sorted(_ADAPTERS)}"
        )

"""
Property-payment gateway package (P9 — online resident payments).

    from apps.properties.gateway import get_property_gateway
    gateway = get_property_gateway()   # per settings.PROPERTY_PAYMENT_GATEWAY

The single construction point for resident -> owner bill payments. It is NOT
`apps.billing.gateway.get_gateway()`, which serves the Tenora subscription;
the two never share an adapter instance, credentials or webhook route.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.properties.gateway.base import PropertyPaymentGateway
from apps.properties.gateway.cashfree import CashfreePropertyPaymentGateway
from apps.properties.gateway.mock import MockPropertyPaymentGateway

_ADAPTERS = {
    "cashfree": CashfreePropertyPaymentGateway,
    "mock": MockPropertyPaymentGateway,
}


def get_property_gateway() -> PropertyPaymentGateway:
    name = getattr(settings, "PROPERTY_PAYMENT_GATEWAY", "cashfree")
    try:
        return _ADAPTERS[name]()
    except KeyError:
        raise ImproperlyConfigured(f"PROPERTY_PAYMENT_GATEWAY={name!r} is not one of {sorted(_ADAPTERS)}")

"""
Email-delivery adapter package (auth-production-readiness spec — Brevo fix).

    from apps.users.email_delivery import get_email_provider
    get_email_provider().send(to_email=..., subject=..., body=...)

`get_email_provider()` is the single construction point — the same
discipline apps.billing.gateway.get_gateway() already uses for the payment
provider. `EmailVerificationService` (apps/users/services.py) is the only
caller; it owns *what* to send (token issuance, the verification URL,
subject/body text) and hands this package *where* to send it.

Tests either `@override_settings(EMAIL_PROVIDER="brevo", ...)` or patch
`apps.users.email_delivery.brevo.requests.post` directly.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.users.email_delivery.base import EmailDeliveryError, EmailProvider
from apps.users.email_delivery.brevo import BrevoEmailProvider
from apps.users.email_delivery.django_provider import DjangoEmailProvider

__all__ = [
    "EmailDeliveryError",
    "EmailProvider",
    "DjangoEmailProvider",
    "BrevoEmailProvider",
    "get_email_provider",
]

_PROVIDERS = {
    "django": DjangoEmailProvider,
    "brevo": BrevoEmailProvider,
}


def get_email_provider() -> EmailProvider:
    name = getattr(settings, "EMAIL_PROVIDER", "django")
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise ImproperlyConfigured(
            f"EMAIL_PROVIDER={name!r} is not one of {sorted(_PROVIDERS)}"
        )

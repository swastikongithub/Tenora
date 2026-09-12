"""
The Brevo (https://www.brevo.com) implementation of EmailProvider — the
ONLY module that talks to Brevo, and the only one that reads
settings.BREVO_API_KEY. Uses Brevo's HTTPS transactional email API
(POST /v3/smtp/email), deliberately never Brevo's SMTP relay: Render's Free
plan blocks outbound SMTP on ports 25/465/587, which is the whole reason
this provider exists instead of just pointing EMAIL_HOST at Brevo's SMTP
server.

`requests` is already a direct dependency (google-auth's transport needs it
— see requirements/base.txt) — no new dependency was added for this.
"""

import logging

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.users.email_delivery.base import EmailDeliveryError, EmailProvider

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
_TIMEOUT_SECONDS = 10


class BrevoEmailProvider(EmailProvider):
    def send(self, *, to_email: str, subject: str, body: str) -> None:
        api_key = settings.BREVO_API_KEY
        from_email = settings.DEFAULT_FROM_EMAIL
        from_name = settings.DEFAULT_FROM_NAME

        if not api_key or not from_email:
            # config/settings.py already fails closed at process start when
            # EMAIL_PROVIDER="brevo" is missing either of these — this
            # repeats the check at the point of use so it holds even if
            # something ever constructs this provider directly (e.g. a
            # test), and so no network call is ever attempted with an empty
            # credential.
            raise ImproperlyConfigured(
                "EMAIL_PROVIDER=brevo requires both BREVO_API_KEY and "
                "DEFAULT_FROM_EMAIL to be set."
            )

        try:
            response = requests.post(
                _ENDPOINT,
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "sender": {"name": from_name, "email": from_email},
                    "to": [{"email": to_email}],
                    "subject": subject,
                    "textContent": body,
                },
                timeout=_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            # Deliberately not folding str(exc) into the raised message or
            # the log line — a transport-level requests exception can echo
            # request details (URL, sometimes header names) depending on the
            # underlying error, and the one header on this request is the
            # API key. Log only the exception type; the caller gets a fixed,
            # generic message with no provider/credential detail in it.
            logger.warning(
                "Brevo email request failed before a response was received: %s",
                type(exc).__name__,
            )
            raise EmailDeliveryError("Could not reach the email provider.") from exc

        if not response.ok:
            # Same reasoning — log/raise the status code only, never the
            # response body (which echoes back parts of the request) or any
            # header.
            logger.warning(
                "Brevo rejected the email request: HTTP %s", response.status_code
            )
            raise EmailDeliveryError(
                f"Email provider rejected the request (HTTP {response.status_code})."
            )

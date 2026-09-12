"""
Provider-neutral email-delivery boundary (auth-production-readiness spec —
the Brevo fix). `EmailVerificationService` (apps/users/services.py) stays
responsible for token issuance, hashing, expiry, resend/verify semantics,
and constructing the verification URL — it does not know how an email
actually leaves this process. That is this package's job, mirroring
apps.billing.gateway's `PaymentGatewayAdapter` seam: callers get an adapter
from `get_email_provider()` (see __init__.py) and never import a concrete
provider directly.
"""

import abc


class EmailDeliveryError(Exception):
    """
    A transactional email could not be delivered — a genuine transport/
    provider failure (network error, non-2xx API response, an SMTP error).
    Never raised for "the recipient doesn't exist" or anything else that
    isn't actually a delivery failure.

    Catching this does NOT mean nothing happened: whatever DB state the
    caller already committed (e.g. a freshly issued verification token)
    stays committed — see apps/users/views.py RegisterView for how a caller
    surfaces that rather than silently claiming the email was sent.
    """


class EmailProvider(abc.ABC):
    """
    The seam between EmailVerificationService and a concrete transport.
    Exactly the surface the one email this project sends today needs — no
    speculative HTML/templating/attachment methods.
    """

    @abc.abstractmethod
    def send(self, *, to_email: str, subject: str, body: str) -> None:
        """
        Send a plain-text email. Raises EmailDeliveryError if the provider
        could not be reached or rejected the request. Must never raise for
        anything else — an invalid `to_email` is a caller bug, not something
        this method decides how to handle.
        """

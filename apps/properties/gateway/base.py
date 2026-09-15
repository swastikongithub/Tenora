"""
Property-payment gateway boundary (P9 — online resident payments).

Deliberately separate from `apps.billing.gateway`, which serves the Tenora
subscription (workspace owner -> Tenora). This interface serves the other
financial domain — a resident paying a property bill to a workspace owner —
and never shares types, secrets, webhook routes or event vocabulary with the
subscription gateway.

Domain services talk only to `PropertyPaymentGateway` and the small value types
below. Provider request/response shapes, header names, signature constructions
and status strings stay inside the concrete adapter (`.cashfree`, `.mock`).

Money crosses this boundary as integer minor units (paise). Converting to the
provider's decimal wire format happens inside the adapter.
"""

import abc
import enum
from dataclasses import dataclass, field
from datetime import datetime


class GatewayUnavailable(Exception):
    """The provider could not be reached or answered with a server-side/unexpected
    error. Nothing is known about the operation's outcome — retry with the SAME
    idempotency key."""


class IdempotencyConflict(GatewayUnavailable):
    """The provider refused a request because another request with the same
    idempotency key is still being processed (or was received with a different
    body). The original operation may well succeed — never treat this as a
    rejection; read the resource back or retry later with the same key."""


class GatewayRejected(Exception):
    """The provider refused the request (validation, authentication, limits).
    Retrying the identical request will not help. `message` is safe to store."""

    def __init__(self, message, *, code=""):
        super().__init__(message)
        self.message = message
        self.code = code


class OrderAlreadyExists(Exception):
    """An order with this merchant order id already exists at the provider."""


class ProviderPaymentStatus(enum.StrEnum):
    SUCCESS = "SUCCESS"
    PENDING = "PENDING"
    FAILED = "FAILED"
    USER_DROPPED = "USER_DROPPED"
    CANCELLED = "CANCELLED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    UNKNOWN = "UNKNOWN"


class ProviderOrderStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"
    UNKNOWN = "UNKNOWN"


class WebhookEventKind(enum.StrEnum):
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_DROPPED = "PAYMENT_DROPPED"
    OTHER = "OTHER"


class WebhookRejected(Exception):
    """Signature/timestamp verification failed. `reason` is a short code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CustomerDetails:
    customer_id: str
    phone: str
    name: str = ""
    email: str = ""


@dataclass(frozen=True)
class CreatedOrder:
    order_id: str
    provider_order_ref: str
    payment_session_id: str
    status: ProviderOrderStatus
    expires_at: datetime | None


@dataclass(frozen=True)
class ProviderPayment:
    provider_payment_id: str
    status: ProviderPaymentStatus
    amount_cents: int
    currency: str
    message: str = ""


@dataclass(frozen=True)
class ProviderOrderState:
    order_id: str
    status: ProviderOrderStatus
    payment_session_id: str
    amount_cents: int
    currency: str
    expires_at: datetime | None


@dataclass(frozen=True)
class RefundResult:
    refund_id: str
    status: str  # SUCCESS / PENDING / ... as normalized upper-case text
    amount_cents: int


@dataclass(frozen=True)
class WebhookEvent:
    kind: WebhookEventKind
    raw_type: str
    order_id: str
    payment: ProviderPayment | None
    #: A per-delivery dedupe key: the provider's idempotency header when sent,
    #: else a digest of the verified raw body.
    dedupe_key: str
    payload: dict = field(default_factory=dict, repr=False)


class PropertyPaymentGateway(abc.ABC):
    name: str = ""

    @abc.abstractmethod
    def create_payment_order(
        self,
        *,
        order_id: str,
        amount_cents: int,
        currency: str,
        customer: CustomerDetails,
        expires_at: datetime,
        return_url: str,
        notify_url: str,
        note: str,
        tags: dict,
        idempotency_key: str,
    ) -> CreatedOrder:
        """Create a hosted-checkout order. Raises OrderAlreadyExists,
        GatewayRejected or GatewayUnavailable."""

    @abc.abstractmethod
    def get_order(self, order_id: str) -> ProviderOrderState | None:
        """Read-only. None if the provider has no such order."""

    @abc.abstractmethod
    def get_payment_status(self, order_id: str) -> list[ProviderPayment]:
        """Read-only: every payment attempt the provider holds for the order."""

    @abc.abstractmethod
    def verify_webhook(self, headers, raw_body: bytes) -> None:
        """Raise WebhookRejected unless the raw body carries a valid, fresh
        provider signature. Never parses the body before verifying."""

    @abc.abstractmethod
    def parse_webhook(self, headers, raw_body: bytes) -> WebhookEvent:
        """Parse an ALREADY VERIFIED webhook into a domain-safe event."""

    @abc.abstractmethod
    def refund_payment(
        self, *, order_id: str, refund_id: str, amount_cents: int, note: str, idempotency_key: str
    ) -> RefundResult:
        """Refund a captured payment. Idempotent on refund_id/idempotency_key."""

    @property
    @abc.abstractmethod
    def checkout_mode(self) -> str:
        """The mode the browser SDK must use ("sandbox" / "production")."""

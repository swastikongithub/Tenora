"""
Provider-neutral payment-gateway boundary (docs/payment-gateway-adapter-spec.md).

Nothing in `apps.billing`'s domain logic imports a payment provider's SDK
directly — every external call goes through `PaymentGatewayAdapter`. This
module defines the interface and the small common shapes; the concrete
adapters live in `.razorpay` and `.mock`.
"""

import abc
import enum
from dataclasses import dataclass
from datetime import datetime, timezone


def epoch_to_datetime(value) -> datetime | None:
    """
    A Unix timestamp (seconds) from a provider payload → an aware UTC datetime,
    or None if the provider didn't supply the field.

    A Unix epoch is definitionally UTC, so an aware datetime is built directly
    (`datetime.fromtimestamp(ts, tz=timezone.utc)`). Deliberately NOT
    `timezone.make_aware(datetime.fromtimestamp(ts))`, which would misread the
    epoch as naive local time. Consistent with the project's USE_TZ=True /
    TIME_ZONE="UTC" convention. Pure conversion — no provider knowledge — so it
    lives here and is shared by every adapter.
    """
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


class EventType(enum.StrEnum):
    """
    The project's own webhook-event vocabulary. Each adapter's
    `parse_webhook_event` maps its provider's specific event names into these,
    so downstream processing (D3) never touches raw provider JSON or
    provider-specific event names.
    """

    ACTIVATED = "ACTIVATED"
    CHARGED = "CHARGED"
    CANCELLED = "CANCELLED"
    PAYMENT_TROUBLE = "PAYMENT_TROUBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NormalizedEvent:
    """A provider webhook event reduced to what the billing domain needs."""

    event_type: EventType
    #: The provider's unique per-delivery event id (dedup key). Empty string if
    #: the provider didn't supply one — the webhook view rejects that with a 400.
    external_event_id: str
    #: The provider's subscription id this event concerns, if any.
    external_subscription_id: str | None
    #: The full provider payload, retained for audit / debugging.
    raw_payload: dict
    #: The billing period this event reports, when the payload carries one
    #: (a `subscription.charged` renewal does; many events don't). Aware UTC
    #: datetimes. A targeted addition to close D3's flagged gap where the CHARGED
    #: handler synthesized a local period instead of using the provider's — not
    #: speculative interface churn.
    period_start: datetime | None = None
    period_end: datetime | None = None
    #: When the PROVIDER generated this event (aware UTC), distinct from when our
    #: server received it. D4's cross-event-type ordering signal: a stale event
    #: (older than the last one already applied to a subscription) is a safe
    #: no-op. `None` when the provider's payload carried no such timestamp — the
    #: ordering guard is then simply skipped for that event.
    event_created_at: datetime | None = None


class WebhookParseError(Exception):
    """The webhook body could not be parsed (not JSON, not an object, …)."""


class ProviderSubscriptionStatus(enum.StrEnum):
    """
    The project's own vocabulary for a subscription's status AS THE PROVIDER
    reports it — the reconciliation counterpart of `EventType`. Each adapter's
    `fetch_subscription_state` maps its provider's specific status strings into
    these, so D8's comparison logic never touches a raw provider status.

    Kept separate from `Subscription.Status` on purpose: this module cannot
    import `models` (models imports from here), and the two vocabularies are
    free to diverge — `TRIALING` is a local-only concept, `PENDING` is a
    provider-only one.
    """

    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    #: Provider-side "authenticated"/"created" — the mandate exists but billing
    #: has not started. No local analogue.
    PENDING = "PENDING"
    #: A provider status with no clean mapping — recorded verbatim in
    #: `raw_status`, surfaced so a reconciliation mismatch is still visible.
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProviderSubscriptionState:
    """
    The provider's current view of one subscription, reduced to what
    reconciliation (D8) needs: the normalized `status` it compares, plus
    `raw_status` and `external_plan_id` retained for the audit record. No
    period dates — D8 deliberately does not compare them (the local period is a
    synthesized placeholder for much of a subscription's life; see
    docs/stage-d8-spec.md).
    """

    status: ProviderSubscriptionStatus
    #: The provider's own status string, exactly as returned, for the audit trail.
    raw_status: str
    #: The provider-side plan id the subscription is on, when the payload carries
    #: one. Captured for audit / a future plan-propagation stage; D8 does NOT
    #: compare it (Tenora's `change_plan` is local-only, so divergence here is
    #: expected, not drift).
    external_plan_id: str | None = None


class ProviderUnavailable(Exception):
    """
    A provider state lookup could not be completed — network error, timeout,
    auth failure, 5xx, rate-limit, or an unparseable/unexpected response shape.

    DISTINCT from an *explicit* "no such subscription", which
    `fetch_subscription_state` signals by returning `None`. Reconciliation
    catches this, records NOTHING (an infra failure is not drift), and moves to
    the next subscription.
    """


class PaymentGatewayAdapter(abc.ABC):
    """
    The seam between the billing domain and a payment provider. Exactly the
    surface D1/D2 already need, plus the event normalization D3 will need — no
    speculative methods (spec §11).

    An ABC, not a Protocol: both implementations are in-repo and there are only
    two, so instantiation-time enforcement that a new adapter implements
    everything is worth more than Protocol's structural-typing flexibility.
    """

    @abc.abstractmethod
    def create_plan(self, plan) -> str:
        """Create the provider-side plan for `plan`; return its external id."""

    @abc.abstractmethod
    def create_subscription(self, tenant, plan) -> str:
        """
        Create the provider-side subscription for `tenant` on `plan`; return its
        external id. `plan` must already have an `external_plan_id`.
        """

    @abc.abstractmethod
    def verify_webhook_signature(self, headers, raw_body: bytes) -> bool:
        """
        Whether `raw_body` carries a valid signature for this provider. Takes
        the full headers, not a pre-extracted value — which header holds the
        signature (and whether a timestamp header is also part of the HMAC, as
        for Cashfree) is provider-specific. Never raises.
        """

    @abc.abstractmethod
    def parse_webhook_event(self, headers, raw_body: bytes) -> NormalizedEvent:
        """
        Parse + normalize a provider webhook. Raises `WebhookParseError` for a
        body that isn't a JSON object. Does NOT verify the signature — call
        `verify_webhook_signature` first.
        """

    @abc.abstractmethod
    def verify_checkout_signature(
        self, payment_id: str, subscription_id: str, signature: str
    ) -> bool:
        """
        Whether a checkout success callback's signature is authentic. A
        different construction and key from the webhook signature. Never raises.
        """

    @abc.abstractmethod
    def fetch_subscription_state(
        self, external_subscription_id: str
    ) -> "ProviderSubscriptionState | None":
        """
        The provider's current state for `external_subscription_id`, for D8
        reconciliation.

        READ-ONLY — this must never create, update, cancel, charge or refund
        anything at the provider.

        Returns `None` IFF the provider explicitly reports no such subscription
        (a genuine reconciliation finding). Raises `ProviderUnavailable` for
        every other failure (network/auth/5xx/unexpected shape) — an infra
        problem that must not be mistaken for drift. Never called for a
        subscription whose `external_subscription_id` is unset.
        """

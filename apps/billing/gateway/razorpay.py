"""
The Razorpay implementation of `PaymentGatewayAdapter`.

This is the ONLY module in `apps.billing` that imports the `razorpay` SDK or
knows Razorpay's specific event names, header names, and HMAC constructions.
The logic here is relocated from D1/D2's `apps.billing.services` and
`razorpay_client` — the SDK calls, request bodies, and cryptographic checks are
byte-for-byte the same; only their container changed (spec §4.2 / §7).
"""

import hashlib
import hmac
import json

import razorpay
from django.conf import settings

from apps.billing.gateway.base import (
    EventType,
    NormalizedEvent,
    PaymentGatewayAdapter,
    ProviderSubscriptionState,
    ProviderSubscriptionStatus,
    ProviderUnavailable,
    WebhookParseError,
    epoch_to_datetime,
)

# Local Plan.interval -> Razorpay (period, interval) for plan.create.
_RAZORPAY_PERIOD = {
    "MONTHLY": ("monthly", 1),
    "ANNUAL": ("yearly", 1),
}

# stage-d2-spec.md §4.1: Razorpay requires a finite billing-cycle count. ~10
# years either way — far past any realistic subscription lifetime.
_TOTAL_COUNT = {
    "MONTHLY": 120,
    "ANNUAL": 10,
}

# Razorpay's specific subscription event names -> the project vocabulary.
# Verified against Razorpay's current webhook docs (D3's paused plan confirmed
# the same list). Anything not listed maps to UNKNOWN.
_EVENT_MAP = {
    "subscription.activated": EventType.ACTIVATED,
    "subscription.charged": EventType.CHARGED,
    "subscription.cancelled": EventType.CANCELLED,
    "subscription.pending": EventType.PAYMENT_TROUBLE,
    "subscription.halted": EventType.PAYMENT_TROUBLE,
}

# Razorpay's `subscription.status` values -> the project's normalized
# reconciliation vocabulary (D8). From Razorpay's Subscriptions docs:
#   created / authenticated → mandate set up, billing not started    → PENDING
#   active                  → billing normally                       → ACTIVE
#   pending / halted        → a charge failed; retrying / stopped    → PAST_DUE
#   cancelled / completed / expired → no longer billing              → CANCELED
# Anything unlisted maps to UNKNOWN (recorded verbatim in raw_status).
_STATUS_MAP = {
    "created": ProviderSubscriptionStatus.PENDING,
    "authenticated": ProviderSubscriptionStatus.PENDING,
    "active": ProviderSubscriptionStatus.ACTIVE,
    "pending": ProviderSubscriptionStatus.PAST_DUE,
    "halted": ProviderSubscriptionStatus.PAST_DUE,
    "cancelled": ProviderSubscriptionStatus.CANCELED,
    "completed": ProviderSubscriptionStatus.CANCELED,
    "expired": ProviderSubscriptionStatus.CANCELED,
}

# Substrings in a Razorpay BadRequestError description that mean "there is no
# such subscription" (as opposed to some other 400). Razorpay returns a 400 —
# not a 404 — for an unknown id, so the message text is the only signal. Kept
# deliberately narrow: anything not matched here is treated as
# ProviderUnavailable, because a false "not found" would record fake drift
# whereas a false "unavailable" merely retries next sweep. The exact set is a
# live-verification item (docs/stage-d8-spec.md).
_NOT_FOUND_MARKERS = ("does not exist", "not found", "no such", "not a valid id")


def _hmac_sha256_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


class RazorpayGatewayAdapter(PaymentGatewayAdapter):
    def _client(self):
        # Constructed per call (cheap), same as D1's get_client(). Kept a method
        # so tests patch exactly one thing.
        return razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

    def create_plan(self, plan) -> str:
        period, interval = _RAZORPAY_PERIOD[plan.interval]
        created = self._client().plan.create(
            {
                "period": period,
                "interval": interval,
                "item": {
                    "name": plan.name,
                    # Razorpay `amount` is the smallest currency unit — cents
                    # for USD — which is exactly what price_cents already is.
                    "amount": plan.price_cents,
                    "currency": plan.currency,
                },
                "notes": {"local_plan_id": str(plan.id)},
            }
        )
        return created["id"]

    def create_subscription(self, tenant, plan) -> str:
        created = self._client().subscription.create(
            {
                "plan_id": plan.external_plan_id,
                "total_count": _TOTAL_COUNT[plan.interval],
                "customer_notify": 1,
                "notes": {"tenant_id": str(tenant.id)},
            }
        )
        return created["id"]

    def verify_webhook_signature(self, headers, raw_body: bytes) -> bool:
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        signature = headers.get("X-Razorpay-Signature", "")
        if not secret or not signature:
            return False
        # HMAC-SHA256 over the RAW body, keyed with the webhook secret, hex,
        # timing-safe compare — Razorpay's exact construction.
        expected = _hmac_sha256_hex(secret, raw_body)
        return hmac.compare_digest(expected, signature)

    def parse_webhook_event(self, headers, raw_body: bytes) -> NormalizedEvent:
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise WebhookParseError("webhook body is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise WebhookParseError("webhook body is not a JSON object")

        raw_name = payload.get("event", "")
        entity = (
            ((payload.get("payload") or {}).get("subscription") or {}).get("entity")
            or {}
        )
        return NormalizedEvent(
            event_type=_EVENT_MAP.get(raw_name, EventType.UNKNOWN),
            # Razorpay's unique per-delivery id is a header, not a body field.
            external_event_id=headers.get("X-Razorpay-Event-Id", "") or "",
            external_subscription_id=entity.get("id"),
            raw_payload=payload,
            # The subscription entity carries the billing period as Unix
            # timestamps on a `subscription.charged` renewal (and some other
            # events); absent → None, no fabricated fallback at this layer.
            period_start=epoch_to_datetime(entity.get("current_start")),
            period_end=epoch_to_datetime(entity.get("current_end")),
            # Razorpay's webhook envelope carries a TOP-LEVEL `created_at` — when
            # Razorpay generated the event. NOT `entity["created_at"]`, which is
            # the subscription's creation time. D4's ordering signal.
            event_created_at=epoch_to_datetime(payload.get("created_at")),
        )

    def verify_checkout_signature(
        self, payment_id: str, subscription_id: str, signature: str
    ) -> bool:
        # HMAC-SHA256 over "{payment_id}|{subscription_id}" (payment_id FIRST —
        # verified against Razorpay's SDK), keyed with the API secret (a
        # different key from the webhook secret), hex, timing-safe.
        secret = settings.RAZORPAY_KEY_SECRET
        if not secret or not signature:
            return False
        expected = _hmac_sha256_hex(secret, f"{payment_id}|{subscription_id}".encode())
        return hmac.compare_digest(expected, signature)

    def fetch_subscription_state(self, external_subscription_id: str):
        """
        GET the Razorpay subscription and normalize it (D8). READ-ONLY: the only
        SDK call is `subscription.fetch` — never `.edit`/`.update`/`.cancel`/
        `.pause`/`.create`.

        `None` when Razorpay explicitly reports no such subscription;
        `ProviderUnavailable` for anything else (5xx, network, auth, an
        unrecognised 400, an unexpected body shape).
        """
        try:
            entity = self._client().subscription.fetch(external_subscription_id)
        except razorpay.errors.BadRequestError as exc:
            message = str(exc).lower()
            if any(marker in message for marker in _NOT_FOUND_MARKERS):
                return None
            raise ProviderUnavailable(
                f"Razorpay rejected the subscription fetch: {exc}"
            ) from exc
        except Exception as exc:  # ServerError, GatewayError, ConnectionError, …
            raise ProviderUnavailable(
                f"Razorpay subscription fetch failed: {exc}"
            ) from exc

        if not isinstance(entity, dict) or "status" not in entity:
            raise ProviderUnavailable(
                f"Razorpay subscription fetch returned an unexpected shape: "
                f"{type(entity).__name__}"
            )

        raw_status = str(entity.get("status") or "")
        return ProviderSubscriptionState(
            status=_STATUS_MAP.get(
                raw_status.lower(), ProviderSubscriptionStatus.UNKNOWN
            ),
            raw_status=raw_status,
            external_plan_id=entity.get("plan_id"),
        )

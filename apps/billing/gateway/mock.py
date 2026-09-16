"""
An in-memory `PaymentGatewayAdapter` with no network calls — for automated
tests and for local development without any provider credentials (spec §4.3).

Deterministic fake ids; signature verification is a configurable flag rather
than a real HMAC; the webhook format is a small provider-neutral shape this
adapter defines for itself.
"""

import json

from apps.billing.gateway.base import (
    EventType,
    ProviderCheckout,
    NormalizedEvent,
    PaymentGatewayAdapter,
    ProviderSubscriptionState,
    ProviderSubscriptionStatus,
    WebhookParseError,
    epoch_to_datetime,
)


class MockGatewayAdapter(PaymentGatewayAdapter):
    def __init__(
        self,
        *,
        webhook_signature_valid: bool = True,
        checkout_signature_valid: bool = True,
        checkout_abandoned: bool | None = False,
        subscription_states=None,
    ):
        self.webhook_signature_valid = webhook_signature_valid
        self.checkout_signature_valid = checkout_signature_valid
        self.checkout_abandoned = checkout_abandoned
        # D8 reconciliation config. Maps an external subscription id to what
        # `fetch_subscription_state` should do for it:
        #   - a dict  {"status": "ACTIVE", "raw_status": "active",
        #              "external_plan_id": "plan_x"}  -> that ProviderSubscriptionState
        #   - None                                    -> the provider disowns it
        #   - an Exception instance                   -> raised as-is
        #   - an id absent from the mapping           -> None (provider not found)
        # Default {} keeps every existing MockGatewayAdapter(...) call unchanged.
        self.subscription_states = dict(subscription_states or {})

    def create_plan(self, plan) -> str:
        return f"mock_plan_{plan.code}"

    def create_subscription(self, tenant, plan) -> ProviderCheckout:
        return ProviderCheckout(
            provider="mock",
            external_subscription_id=f"mock_sub_{tenant.id}",
            session_token=f"mock_session_{tenant.id}",
            public_key="mock_key",
            mode="sandbox",
        )

    def confirm_checkout_report(self, external_subscription_id, report) -> bool:
        return self.checkout_signature_valid

    def checkout_is_abandoned(self, external_subscription_id):
        """Whatever the test configured: False (a live checkout) by default,
        True for an abandoned one, None for "provider unreachable"."""
        return self.checkout_abandoned

    def verify_webhook_signature(self, headers, raw_body: bytes) -> bool:
        return self.webhook_signature_valid

    def parse_webhook_event(self, headers, raw_body: bytes) -> NormalizedEvent:
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise WebhookParseError("webhook body is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise WebhookParseError("webhook body is not a JSON object")

        raw_type = payload.get("type", "")
        try:
            event_type = EventType(raw_type)
        except ValueError:
            event_type = EventType.UNKNOWN
        return NormalizedEvent(
            event_type=event_type,
            external_event_id=headers.get("X-Mock-Event-Id", "") or "",
            external_subscription_id=payload.get("subscription_id"),
            raw_payload=payload,
            # Optional epoch-seconds period, so tests can drive both the
            # "provider sent real dates" and "no dates" paths deliberately.
            period_start=epoch_to_datetime(payload.get("period_start")),
            period_end=epoch_to_datetime(payload.get("period_end")),
            # Optional epoch-seconds event-generation time (D4 ordering signal);
            # distinct key in this adapter's self-defined shape.
            event_created_at=epoch_to_datetime(payload.get("event_created_at")),
        )

    def verify_checkout_signature(
        self, payment_id: str, subscription_id: str, signature: str
    ) -> bool:
        return self.checkout_signature_valid

    def fetch_subscription_state(self, external_subscription_id: str):
        """D8 reconciliation lookup, driven entirely by `subscription_states`
        (see `__init__`). Read-only by construction — there is nothing to write."""
        configured = self.subscription_states.get(external_subscription_id)
        if isinstance(configured, BaseException):
            raise configured
        if configured is None:
            return None
        if isinstance(configured, ProviderSubscriptionState):
            return configured
        raw_status = configured.get("raw_status") or configured.get("status", "")
        status = configured.get("status", ProviderSubscriptionStatus.UNKNOWN)
        return ProviderSubscriptionState(
            status=ProviderSubscriptionStatus(status),
            raw_status=str(raw_status),
            external_plan_id=configured.get("external_plan_id"),
        )

"""
In-memory property-payment gateway for local development and the automated
suite — no network, no credentials.

Orders, payments and refunds live in a class-level `MockPropertyPaymentGateway
.state` that tests reset and drive (`reset()`, `add_payment()`, `fail_next`).
Webhook verification and parsing reuse the Cashfree adapter's exact signature
construction and payload mapping, so webhook tests exercise the real checks with
a deterministic secret instead of a stub that always says yes.
"""

import uuid
from dataclasses import dataclass, field

from apps.properties.gateway.base import (
    CreatedOrder,
    GatewayRejected,
    GatewayUnavailable,
    IdempotencyConflict,
    OrderAlreadyExists,
    PropertyPaymentGateway,
    ProviderOrderState,
    ProviderOrderStatus,
    ProviderPayment,
    ProviderPaymentStatus,
    RefundResult,
)
from apps.properties.gateway.cashfree import CashfreePropertyPaymentGateway


@dataclass
class _State:
    orders: dict = field(default_factory=dict)  # order_id -> dict
    payments: dict = field(default_factory=dict)  # order_id -> [ProviderPayment]
    refunds: dict = field(default_factory=dict)  # refund_id -> RefundResult
    idempotency: dict = field(default_factory=dict)  # key -> order_id
    calls: list = field(default_factory=list)
    #: Set to GatewayUnavailable("...") / GatewayRejected("...") to fail the next call.
    fail_next: Exception | None = None


class MockPropertyPaymentGateway(PropertyPaymentGateway):
    name = "mock"
    state = _State()

    @classmethod
    def reset(cls):
        cls.state = _State()

    @classmethod
    def add_payment(cls, order_id, *, status=ProviderPaymentStatus.SUCCESS, amount_cents=None, currency="INR", payment_id=None):
        order = cls.state.orders[order_id]
        payment = ProviderPayment(
            provider_payment_id=payment_id or str(uuid.uuid4().int)[:12],
            status=status,
            amount_cents=order["amount_cents"] if amount_cents is None else amount_cents,
            currency=currency,
            message="Simulated",
        )
        cls.state.payments.setdefault(order_id, []).append(payment)
        if status == ProviderPaymentStatus.SUCCESS:
            order["status"] = ProviderOrderStatus.PAID
        return payment

    def _maybe_fail(self):
        failure, self.state.fail_next = self.state.fail_next, None
        if failure is not None:
            raise failure

    @property
    def checkout_mode(self) -> str:
        return "sandbox"

    def create_payment_order(
        self, *, order_id, amount_cents, currency, customer, expires_at, return_url, notify_url, note, tags, idempotency_key
    ) -> CreatedOrder:
        self.state.calls.append(
            ("create_payment_order", {
                "order_id": order_id, "amount_cents": amount_cents, "currency": currency,
                "customer": customer, "return_url": return_url, "idempotency_key": idempotency_key, "tags": tags,
            })
        )
        self._maybe_fail()
        if idempotency_key in self.state.idempotency:
            existing = self.state.orders[self.state.idempotency[idempotency_key]]
            return CreatedOrder(order_id, existing["ref"], existing["session"], existing["status"], existing["expires_at"])
        if order_id in self.state.orders:
            raise OrderAlreadyExists(order_id)
        order = {
            "ref": f"cf_{len(self.state.orders) + 1}",
            "session": f"session_{uuid.uuid4().hex}",
            "status": ProviderOrderStatus.ACTIVE,
            "expires_at": expires_at,
            "amount_cents": amount_cents,
            "currency": currency,
        }
        self.state.orders[order_id] = order
        self.state.idempotency[idempotency_key] = order_id
        return CreatedOrder(order_id, order["ref"], order["session"], order["status"], expires_at)

    def get_order(self, order_id):
        self.state.calls.append(("get_order", order_id))
        self._maybe_fail()
        order = self.state.orders.get(order_id)
        if order is None:
            return None
        return ProviderOrderState(order_id, order["status"], order["session"], order["amount_cents"], order["currency"], order["expires_at"])

    def get_payment_status(self, order_id):
        self.state.calls.append(("get_payment_status", order_id))
        self._maybe_fail()
        return list(self.state.payments.get(order_id, []))

    def refund_payment(self, *, order_id, refund_id, amount_cents, note, idempotency_key):
        self.state.calls.append(("refund_payment", {"order_id": order_id, "refund_id": refund_id, "amount_cents": amount_cents}))
        self._maybe_fail()
        if refund_id not in self.state.refunds:
            self.state.refunds[refund_id] = RefundResult(refund_id, "SUCCESS", amount_cents)
        return self.state.refunds[refund_id]

    def verify_webhook(self, headers, raw_body):
        return self._cashfree().verify_webhook(headers, raw_body)

    def parse_webhook(self, headers, raw_body):
        return self._cashfree().parse_webhook(headers, raw_body)

    @staticmethod
    def _cashfree():
        # Only the signature/parse code is used — never the network.
        return CashfreePropertyPaymentGateway(client_id="mock", environment="sandbox")


__all__ = ["MockPropertyPaymentGateway", "GatewayRejected", "GatewayUnavailable", "IdempotencyConflict"]

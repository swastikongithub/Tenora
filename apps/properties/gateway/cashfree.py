"""
Cashfree Payment Gateway adapter for property-bill payments (P9).

The only module that knows Cashfree's endpoints, headers, JSON shapes, status
strings and webhook signature construction. Talks to the documented REST API
(`/pg/orders`, `/pg/orders/{id}`, `/pg/orders/{id}/payments`,
`/pg/orders/{id}/refunds`) with `requests` — no provider SDK.

Verified against Cashfree's current docs:
  * Create Order: POST /orders, headers x-client-id / x-client-secret /
    x-api-version / x-idempotency-key; body order_id (3–45 chars), order_amount
    (number, 2 dp), order_currency, customer_details {customer_id (3–50),
    customer_phone (10 digits)}, order_meta {return_url, notify_url},
    order_expiry_time (ISO 8601). Returns payment_session_id and order_status.
    A repeated order_id -> 409 `order_already_exists`.
  * Webhook signature: Base64(HMAC-SHA256(x-webhook-timestamp + raw_body,
    client secret)), computed over the RAW body; x-webhook-timestamp is epoch
    milliseconds.
  * Payment webhook `type`: PAYMENT_SUCCESS_WEBHOOK / PAYMENT_FAILED_WEBHOOK /
    PAYMENT_USER_DROPPED_WEBHOOK (+ PAYMENT_CHARGES_WEBHOOK, ignored); payload
    data.order.order_id and data.payment {cf_payment_id, payment_status,
    payment_amount, payment_currency, payment_message}.

Money: the domain passes integer paise. The wire needs a JSON number with at
most two decimals; it is produced from exact integer arithmetic and parsed back
with Decimal (never float arithmetic on an amount that matters).
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

from apps.properties.gateway.base import (
    CreatedOrder,
    GatewayRejected,
    GatewayUnavailable,
    OrderAlreadyExists,
    PropertyPaymentGateway,
    ProviderOrderState,
    ProviderOrderStatus,
    ProviderPayment,
    ProviderPaymentStatus,
    RefundResult,
    WebhookEvent,
    WebhookEventKind,
    WebhookRejected,
)

logger = logging.getLogger(__name__)

BASE_URLS = {
    "sandbox": "https://sandbox.cashfree.com/pg",
    "production": "https://api.cashfree.com/pg",
}
TIMEOUT_SECONDS = 15

_EVENT_KINDS = {
    "PAYMENT_SUCCESS_WEBHOOK": WebhookEventKind.PAYMENT_SUCCESS,
    "PAYMENT_FAILED_WEBHOOK": WebhookEventKind.PAYMENT_FAILED,
    "PAYMENT_USER_DROPPED_WEBHOOK": WebhookEventKind.PAYMENT_DROPPED,
}


def cents_to_wire(cents: int) -> float:
    """Integer paise -> the JSON number Cashfree expects. Built from integer
    division, so the float always has an exact two-decimal repr (13780.55)."""
    whole, fraction = divmod(int(cents), 100)
    return float(f"{whole}.{fraction:02d}")


def wire_to_cents(value) -> int:
    """A provider amount (number or string) -> integer paise, refusing anything
    that is not a whole number of paise."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f"not an amount: {value!r}")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"amount has sub-paise precision: {value!r}")
    return int(cents)


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _order_status(value) -> ProviderOrderStatus:
    try:
        return ProviderOrderStatus(str(value).upper())
    except ValueError:
        return ProviderOrderStatus.UNKNOWN


def _payment_status(value) -> ProviderPaymentStatus:
    raw = str(value or "").upper()
    if raw == "VOID":
        return ProviderPaymentStatus.CANCELLED
    try:
        return ProviderPaymentStatus(raw)
    except ValueError:
        return ProviderPaymentStatus.UNKNOWN


def _safe_message(body) -> str:
    if isinstance(body, dict):
        return str(body.get("message") or body.get("code") or "")[:255]
    return ""


class CashfreePropertyPaymentGateway(PropertyPaymentGateway):
    name = "cashfree"

    def __init__(self, *, client_id=None, client_secret=None, environment=None, api_version=None, session=None):
        self.client_id = client_id if client_id is not None else settings.CASHFREE_CLIENT_ID
        self.client_secret = client_secret if client_secret is not None else settings.CASHFREE_CLIENT_SECRET
        self.environment = (environment or settings.CASHFREE_ENVIRONMENT).lower()
        self.api_version = api_version or settings.CASHFREE_API_VERSION
        if self.environment not in BASE_URLS:
            raise GatewayRejected("CASHFREE_ENVIRONMENT must be 'sandbox' or 'production'.", code="misconfigured")
        self.http = session or requests.Session()

    @property
    def checkout_mode(self) -> str:
        return self.environment

    # --- HTTP -----------------------------------------------------------------

    def _headers(self, idempotency_key=None):
        headers = {
            "x-client-id": self.client_id,
            "x-client-secret": self.client_secret,
            "x-api-version": self.api_version,
            "accept": "application/json",
            "content-type": "application/json",
        }
        if idempotency_key:
            headers["x-idempotency-key"] = idempotency_key
        return headers

    def _request(self, method, path, *, body=None, idempotency_key=None):
        if not self.client_id or not self.client_secret:
            raise GatewayRejected("Online payments are not configured.", code="not_configured")
        url = f"{BASE_URLS[self.environment]}{path}"
        try:
            response = self.http.request(
                method,
                url,
                headers=self._headers(idempotency_key),
                data=json.dumps(body) if body is not None else None,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            # Never log the headers: they carry the client secret.
            logger.warning("cashfree %s %s failed: %s", method, path, exc.__class__.__name__)
            raise GatewayUnavailable(exc.__class__.__name__) from exc
        try:
            payload = response.json() if response.content else None
        except ValueError:
            payload = None
        return response.status_code, payload

    # --- Orders -----------------------------------------------------------------

    def create_payment_order(
        self, *, order_id, amount_cents, currency, customer, expires_at, return_url, notify_url, note, tags, idempotency_key
    ) -> CreatedOrder:
        body = {
            "order_id": order_id,
            "order_amount": cents_to_wire(amount_cents),
            "order_currency": currency,
            "customer_details": {
                "customer_id": customer.customer_id,
                "customer_phone": customer.phone,
            },
            "order_meta": {"return_url": return_url},
            "order_expiry_time": expires_at.isoformat(timespec="seconds"),
            "order_note": note,
            "order_tags": tags,
        }
        if customer.name and len(customer.name) >= 3:
            body["customer_details"]["customer_name"] = customer.name[:100]
        if customer.email and len(customer.email) >= 3:
            body["customer_details"]["customer_email"] = customer.email[:100]
        if notify_url:
            body["order_meta"]["notify_url"] = notify_url

        status, payload = self._request("POST", "/orders", body=body, idempotency_key=idempotency_key)
        if status == 409 and isinstance(payload, dict) and payload.get("code") == "order_already_exists":
            raise OrderAlreadyExists(order_id)
        if status >= 500 or status == 429:
            raise GatewayUnavailable(f"HTTP {status}")
        if status >= 400 or not isinstance(payload, dict):
            raise GatewayRejected(_safe_message(payload) or f"HTTP {status}", code=str((payload or {}).get("code", "")))
        session_id = payload.get("payment_session_id") or ""
        if not session_id:
            raise GatewayUnavailable("order response without payment_session_id")
        return CreatedOrder(
            order_id=str(payload.get("order_id") or order_id),
            provider_order_ref=str(payload.get("cf_order_id") or ""),
            payment_session_id=session_id,
            status=_order_status(payload.get("order_status")),
            expires_at=_parse_time(payload.get("order_expiry_time")),
        )

    def get_order(self, order_id) -> ProviderOrderState | None:
        status, payload = self._request("GET", f"/orders/{order_id}")
        if status == 404:
            return None
        if status >= 400 or not isinstance(payload, dict):
            raise GatewayUnavailable(f"HTTP {status}")
        try:
            amount = wire_to_cents(payload.get("order_amount"))
        except ValueError as exc:
            raise GatewayUnavailable("unexpected order amount") from exc
        return ProviderOrderState(
            order_id=str(payload.get("order_id") or order_id),
            status=_order_status(payload.get("order_status")),
            payment_session_id=str(payload.get("payment_session_id") or ""),
            amount_cents=amount,
            currency=str(payload.get("order_currency") or ""),
            expires_at=_parse_time(payload.get("order_expiry_time")),
        )

    def get_payment_status(self, order_id) -> list[ProviderPayment]:
        status, payload = self._request("GET", f"/orders/{order_id}/payments")
        if status == 404:
            return []
        if status >= 400 or not isinstance(payload, list):
            raise GatewayUnavailable(f"HTTP {status}")
        payments = []
        for item in payload:
            try:
                payments.append(
                    ProviderPayment(
                        provider_payment_id=str(item.get("cf_payment_id") or ""),
                        status=_payment_status(item.get("payment_status")),
                        amount_cents=wire_to_cents(item.get("payment_amount")),
                        currency=str(item.get("payment_currency") or ""),
                        message=str(item.get("payment_message") or "")[:255],
                    )
                )
            except (ValueError, AttributeError) as exc:
                raise GatewayUnavailable("unexpected payment item") from exc
        return payments

    # --- Refunds ---------------------------------------------------------------

    def refund_payment(self, *, order_id, refund_id, amount_cents, note, idempotency_key) -> RefundResult:
        body = {"refund_id": refund_id, "refund_amount": cents_to_wire(amount_cents), "refund_note": note[:100]}
        status, payload = self._request("POST", f"/orders/{order_id}/refunds", body=body, idempotency_key=idempotency_key)
        if status == 409:
            # Same refund_id already exists: read it back rather than refunding twice.
            status, payload = self._request("GET", f"/orders/{order_id}/refunds/{refund_id}")
        if status >= 500 or status == 429:
            raise GatewayUnavailable(f"HTTP {status}")
        if status >= 400 or not isinstance(payload, dict):
            raise GatewayRejected(_safe_message(payload) or f"HTTP {status}", code=str((payload or {}).get("code", "")))
        return RefundResult(
            refund_id=str(payload.get("refund_id") or refund_id),
            status=str(payload.get("refund_status") or "PENDING").upper(),
            amount_cents=wire_to_cents(payload.get("refund_amount", cents_to_wire(amount_cents))),
        )

    # --- Webhooks ---------------------------------------------------------------

    def verify_webhook(self, headers, raw_body: bytes) -> None:
        signature = headers.get("x-webhook-signature") or ""
        timestamp = headers.get("x-webhook-timestamp") or ""
        if not signature or not timestamp:
            raise WebhookRejected("missing_signature")
        if not self.client_secret:
            raise WebhookRejected("not_configured")
        signed = timestamp.encode() + raw_body
        expected = base64.b64encode(hmac.new(self.client_secret.encode(), signed, hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(expected, signature.strip()):
            raise WebhookRejected("bad_signature")
        tolerance = settings.CASHFREE_WEBHOOK_TOLERANCE_SECONDS
        if tolerance:
            try:
                sent_at = int(timestamp) / 1000
            except ValueError:
                raise WebhookRejected("bad_timestamp")
            if abs(time.time() - sent_at) > tolerance:
                raise WebhookRejected("stale_timestamp")

    def parse_webhook(self, headers, raw_body: bytes) -> WebhookEvent:
        try:
            body = json.loads(raw_body, parse_float=Decimal)
        except ValueError as exc:
            raise ValueError("webhook body is not JSON") from exc
        if not isinstance(body, dict):
            raise ValueError("webhook body is not an object")
        raw_type = str(body.get("type") or "")
        data = body.get("data") or {}
        order = data.get("order") or {}
        payment_data = data.get("payment") or None
        payment = None
        if isinstance(payment_data, dict) and payment_data.get("cf_payment_id") is not None:
            payment = ProviderPayment(
                provider_payment_id=str(payment_data.get("cf_payment_id")),
                status=_payment_status(payment_data.get("payment_status")),
                amount_cents=wire_to_cents(payment_data.get("payment_amount")),
                currency=str(payment_data.get("payment_currency") or ""),
                message=str(payment_data.get("payment_message") or "")[:255],
            )
        return WebhookEvent(
            kind=_EVENT_KINDS.get(raw_type, WebhookEventKind.OTHER),
            raw_type=raw_type[:64],
            order_id=str(order.get("order_id") or ""),
            payment=payment,
            # Retries resend the same payload, so the verified body digest is a
            # stable per-event key (independent of any retry-varying header).
            dedupe_key=hashlib.sha256(raw_body).hexdigest(),
            payload=json.loads(raw_body),
        )

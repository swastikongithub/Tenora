"""
The Cashfree Subscriptions implementation of `PaymentGatewayAdapter` — the
Tenora SUBSCRIPTION domain (workspace owner -> Tenora).

Deliberately unrelated to `apps.properties.gateway.cashfree`, which serves the
other financial domain (resident -> workspace owner) through Cashfree's
Payment Gateway orders API. The two share a vendor and nothing else: different
API family (Subscriptions vs Orders), different settings, different webhook
route, different event vocabulary. Nothing is imported across that line — the
small amount of signature code that looks similar is duplicated on purpose, so
neither domain can be changed by editing the other.

This is the ONLY module in `apps.billing` that knows Cashfree's endpoints,
field names, status strings or signature construction. Everything leaves through
`base.py`'s types.

Money: Tenora stores `price_cents`; Cashfree's subscription amounts are decimal
major units, so the conversion happens here and nowhere else.

API: https://www.cashfree.com/docs/api-reference/payments/latest/subscription
(`x-api-version: 2026-01-01`; base `https://sandbox.cashfree.com/pg` /
`https://api.cashfree.com/pg`).
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from apps.billing.gateway.base import (
    EventType,
    NormalizedEvent,
    PaymentGatewayAdapter,
    ProviderCheckout,
    ProviderSubscriptionState,
    ProviderSubscriptionStatus,
    ProviderUnavailable,
    SubscriberContactRequired,
    WebhookParseError,
    parse_provider_datetime,
)
from apps.tenants.models import Membership

logger = logging.getLogger(__name__)

_TIMEOUT = 20

#: Cashfree's limit on plan_name (1-40 characters).
PLAN_NAME_MAX = 40

# Tenora's Plan.interval -> Cashfree's PERIODIC plan interval.
_INTERVAL = {
    "MONTHLY": ("MONTH", 1),
    "ANNUAL": ("YEAR", 1),
}

# Cashfree subscription webhook event types -> the project's vocabulary.
# SUBSCRIPTION_STATUS_CHANGED carries the destination state in the payload, so
# it is resolved through `_STATUS_EVENT` below rather than mapped here.
_EVENT_MAP = {
    "SUBSCRIPTION_PAYMENT_SUCCESS": EventType.CHARGED,
    "SUBSCRIPTION_PAYMENT_FAILED": EventType.PAYMENT_TROUBLE,
    "SUBSCRIPTION_PAYMENT_CANCELLED": EventType.PAYMENT_TROUBLE,
}

# `subscription_status` on a SUBSCRIPTION_STATUS_CHANGED event.
# PAUSED is deliberately UNKNOWN: it is a merchant-initiated stop to charging,
# and `SubscriptionService` has no pause transition — forcing it through
# CANCELLED (terminal, irreversible) or PAYMENT_TROUBLE (a failed charge, which
# it is not) would both be lies. It is recorded and left for reconciliation.
_STATUS_EVENT = {
    "ACTIVE": EventType.ACTIVATED,
    "ON_HOLD": EventType.PAYMENT_TROUBLE,
    "BANK_APPROVAL_PENDING": EventType.UNKNOWN,
    "PAUSED": EventType.UNKNOWN,
    "CANCELLED": EventType.CANCELLED,
    "CUSTOMER_CANCELLED": EventType.CANCELLED,
    "COMPLETED": EventType.CANCELLED,
    "EXPIRED": EventType.CANCELLED,
    "CARD_EXPIRED": EventType.PAYMENT_TROUBLE,
}

# Cashfree's subscription statuses -> the reconciliation vocabulary (D8).
_STATUS_MAP = {
    "INITIALIZED": ProviderSubscriptionStatus.PENDING,
    "PENDING": ProviderSubscriptionStatus.PENDING,
    "BANK_APPROVAL_PENDING": ProviderSubscriptionStatus.PENDING,
    "ACTIVE": ProviderSubscriptionStatus.ACTIVE,
    "ON_HOLD": ProviderSubscriptionStatus.PAST_DUE,
    "CARD_EXPIRED": ProviderSubscriptionStatus.PAST_DUE,
    # Merchant-paused: the mandate stands but nothing is being charged. Closest
    # honest match is "set up, not billing" — never ACTIVE, never CANCELED.
    "PAUSED": ProviderSubscriptionStatus.PENDING,
    "CANCELLED": ProviderSubscriptionStatus.CANCELED,
    "CUSTOMER_CANCELLED": ProviderSubscriptionStatus.CANCELED,
    "COMPLETED": ProviderSubscriptionStatus.CANCELED,
    "EXPIRED": ProviderSubscriptionStatus.CANCELED,
}


def cents_to_amount(cents: int) -> float:
    """1_050 paise -> 10.5. Exact: paise are two decimal places by definition."""
    return float(Decimal(cents) / Decimal(100))


#: Request fields that identify a PERSON rather than a plan or an amount. They
#: are replaced, not dropped, so a log line still shows the field was sent.
_PII_FIELDS = ("customer_details", "subscription_tags")


def _sanitized(payload):
    """A request body safe to log: no credentials (those are headers and never
    appear here) and no subscriber contact details."""
    if not isinstance(payload, dict):
        return "{}"
    redacted = {
        key: ("<redacted>" if key in _PII_FIELDS else value)
        for key, value in payload.items()
    }
    return json.dumps(redacted, default=str)[:600]


def _safe_error(body):
    """The provider's own error identification — code, type and message — and
    nothing else from its response."""
    if not isinstance(body, dict):
        return ""
    parts = [
        f"{key}={body[key]!r}"
        for key in ("code", "type", "message")
        if body.get(key)
    ]
    return " ".join(parts)[:400] or "(no error fields in response)"


def _says_already_exists(body) -> bool:
    text = " ".join(
        str(body.get(key, "")) for key in ("message", "code", "type", "error")
    ).lower()
    return "already exist" in text or "duplicate" in text


def _api_base() -> str:
    environment = getattr(settings, "CASHFREE_SUBSCRIPTION_ENVIRONMENT", "sandbox")
    host = "api" if environment == "production" else "sandbox"
    return f"https://{host}.cashfree.com/pg"


class CashfreeSubscriptionGatewayAdapter(PaymentGatewayAdapter):
    """
    Cashfree Subscriptions: a mandate (UPI AutoPay / card / eNACH) authorised
    once by the owner, then charged by Cashfree on its own schedule. Renewals
    therefore arrive as webhooks, never as a user action in Tenora.
    """

    name = "cashfree"

    def __init__(self, session=None):
        self.http = session or requests.Session()

    # --- HTTP -------------------------------------------------------------

    def _credentials(self):
        client_id = getattr(settings, "CASHFREE_SUBSCRIPTION_CLIENT_ID", "")
        secret = getattr(settings, "CASHFREE_SUBSCRIPTION_CLIENT_SECRET", "")
        return client_id, secret

    def _request(self, method, path, payload=None):
        client_id, secret = self._credentials()
        if not client_id or not secret:
            # Fail closed, exactly like an unconfigured Razorpay deployment.
            raise ProviderUnavailable("Cashfree subscription credentials are not configured.")
        headers = {
            "x-api-version": getattr(settings, "CASHFREE_SUBSCRIPTION_API_VERSION", "2026-01-01"),
            "x-client-id": client_id,
            "x-client-secret": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"{_api_base()}{path}"
        try:
            response = self.http.request(
                method, url, headers=headers,
                data=json.dumps(payload) if payload is not None else None,
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            # Never let the provider's message (which can echo request data)
            # reach a log line verbatim beyond its class name.
            logger.warning("cashfree subscriptions %s %s failed: %s", method, path, type(exc).__name__)
            raise ProviderUnavailable(f"{method} {path} failed") from exc
        try:
            body = response.json() if response.content else {}
        except ValueError:
            raise ProviderUnavailable(f"{method} {path} returned a non-JSON body")
        if response.status_code >= 400:
            # Diagnostics for an operator reading the service log. Credentials
            # live only in `headers`, which is never touched here; the request
            # body is sanitized because a subscription carries the subscriber's
            # email and phone.
            logger.warning(
                "cashfree subscriptions %s %s -> %s %s | request: %s",
                method,
                path,
                response.status_code,
                _safe_error(body),
                _sanitized(payload),
            )
        return response.status_code, body if isinstance(body, dict) else {"data": body}

    # --- plans ------------------------------------------------------------

    def create_plan(self, plan) -> str:
        """
        Create the Cashfree plan mirroring `plan`, returning its provider id.

        Tenora's Plan stays the single source of truth for entitlements and
        limits: only the money and the cadence are mirrored here, under an id
        derived from Tenora's own plan code, so the mapping is inspectable in
        the Cashfree dashboard and re-runnable.
        """
        interval_type, intervals = _INTERVAL.get(plan.interval, ("MONTH", 1))
        plan_id = f"tenora_{plan.code.lower()}"
        amount = cents_to_amount(plan.price_cents)
        status_code, body = self._request("POST", "/plans", {
            "plan_id": plan_id,
            # Cashfree caps plan_name at 40 characters.
            "plan_name": plan.name[:PLAN_NAME_MAX],
            "plan_type": "PERIODIC",
            "plan_currency": plan.currency or "INR",
            # The recurring charge per interval. NOT `plan_amount` — that field
            # belongs to the subscription payload; the plans API rejects it.
            "plan_recurring_amount": amount,
            # Required. The ceiling Cashfree will ever debit under this plan;
            # the mandate is authorised up to it. Equal to the recurring amount:
            # a Tenora plan charges exactly its price, so a higher ceiling would
            # authorise more than the plan can ever legitimately take.
            "plan_max_amount": amount,
            "plan_interval_type": interval_type,
            "plan_intervals": intervals,
        })
        if status_code in (200, 201):
            return body.get("plan_id") or plan_id
        # The plan id is derived from Tenora's plan code, so re-running a sync
        # hits an id Cashfree already holds. That is success, not a failure —
        # and since the docs do not pin the status code for it, both the
        # conflict code and a 400 that says so are accepted. Anything else is
        # still an error: a typo'd field must not masquerade as "already done".
        if status_code == 409 or (
            status_code in (400, 422) and _says_already_exists(body)
        ):
            return plan_id
        raise ProviderUnavailable(
            f"create plan failed ({status_code}) {_safe_error(body)}"
        )

    # --- subscriptions ----------------------------------------------------

    @staticmethod
    def _subscriber(tenant):
        """
        The workspace owner, as Cashfree's customer. Cashfree requires a phone
        number to raise a mandate; an owner who has not saved one is told to,
        rather than the checkout failing opaquely at the provider.
        """
        membership = (
            Membership.objects.filter(
                tenant=tenant,
                role=Membership.Role.OWNER,
                status=Membership.Status.ACTIVE,
            )
            .select_related("user")
            .order_by("created_at")
            .first()
        )
        if membership is None:
            raise SubscriberContactRequired("This workspace has no active owner.")
        user = membership.user
        phone = (user.phone or "").strip()
        if not phone:
            raise SubscriberContactRequired(
                "Add a mobile number in Settings before subscribing — the payment "
                "provider needs it to set up recurring payments."
            )
        name = (f"{user.first_name} {user.last_name}".strip() or user.email.split("@")[0])[:100]
        return user, phone, name

    def create_subscription(self, tenant, plan) -> ProviderCheckout:
        user, phone, name = self._subscriber(tenant)
        # Our own id for the subscription — one per checkout attempt, so a
        # retried checkout after a failed authorisation is a new mandate rather
        # than a collision on an id Cashfree already holds.
        subscription_id = f"tnrsub_{tenant.id.hex}_{int(time.time())}"[:250]
        expires_at = timezone.now() + timedelta(
            minutes=getattr(settings, "CASHFREE_SUBSCRIPTION_SESSION_TTL_MINUTES", 60)
        )
        status_code, body = self._request("POST", "/subscriptions", {
            "subscription_id": subscription_id,
            "customer_details": {
                "customer_name": name,
                "customer_email": user.email,
                "customer_phone": phone,
            },
            "plan_details": {"plan_id": plan.external_plan_id},
            "authorization_details": {
                # A token charge that proves the mandate works; Cashfree refunds
                # it. Kept at the provider's minimum rather than the plan price.
                "authorization_amount": 1,
                "authorization_amount_refund": True,
                "payment_methods": ["upi", "card", "enach"],
            },
            "subscription_meta": {
                "return_url": f"{settings.FRONTEND_URL.rstrip('/')}/subscription",
                "notification_channel": ["EMAIL"],
            },
            "subscription_expiry_time": expires_at.isoformat(),
            "subscription_tags": {"tenant_id": str(tenant.id), "plan_code": plan.code},
        })
        if status_code not in (200, 201):
            raise ProviderUnavailable(
                f"create subscription failed ({status_code}) {_safe_error(body)}"
            )
        session_id = body.get("subscription_session_id") or ""
        if not session_id:
            raise ProviderUnavailable("create subscription returned no checkout session")
        return ProviderCheckout(
            provider=self.name,
            external_subscription_id=body.get("subscription_id") or subscription_id,
            session_token=session_id,
            public_key="",
            mode="production"
            if getattr(settings, "CASHFREE_SUBSCRIPTION_ENVIRONMENT", "sandbox") == "production"
            else "sandbox",
        )

    def fetch_subscription_state(self, external_subscription_id):
        status_code, body = self._request("GET", f"/subscriptions/{external_subscription_id}")
        if status_code == 404:
            return None
        if status_code != 200:
            raise ProviderUnavailable(f"fetch subscription failed ({status_code})")
        raw_status = str(body.get("subscription_status") or "")
        return ProviderSubscriptionState(
            status=_STATUS_MAP.get(raw_status, ProviderSubscriptionStatus.UNKNOWN),
            raw_status=raw_status,
            external_plan_id=(body.get("plan_details") or {}).get("plan_id"),
        )

    # --- checkout confirmation -------------------------------------------

    def confirm_checkout_report(self, external_subscription_id, report) -> bool:
        """
        Cashfree's subscription return is a plain redirect with no signed
        payload, so the browser's report is worth nothing on its own and is
        ignored: the provider itself is asked what the mandate's state is.
        Authoritative activation still belongs to the webhook — this only
        answers "was the authorisation genuinely completed?" for UI feedback.
        """
        try:
            state = self.fetch_subscription_state(external_subscription_id)
        except ProviderUnavailable:
            return False
        if state is None:
            return False
        return state.status in (
            ProviderSubscriptionStatus.ACTIVE,
            ProviderSubscriptionStatus.PENDING,
        )

    def verify_checkout_signature(self, payment_id, subscription_id, signature) -> bool:
        """
        Not part of Cashfree's subscription flow — there is no signed browser
        callback to verify. Always False so that no code path can mistake an
        unverifiable client report for a verified one; `confirm_checkout_report`
        is what this adapter answers with.
        """
        return False

    # --- webhooks ---------------------------------------------------------

    def verify_webhook_signature(self, headers, raw_body: bytes) -> bool:
        """
        Base64(HMAC-SHA256(timestamp + raw_body, client secret)), timing-safe,
        with a freshness window on the timestamp. Never raises: a malformed
        header is simply not a valid signature.
        """
        _, secret = self._credentials()
        signature = headers.get("x-webhook-signature") or ""
        timestamp = headers.get("x-webhook-timestamp") or ""
        if not secret or not signature or not timestamp:
            return False
        tolerance = getattr(settings, "CASHFREE_SUBSCRIPTION_WEBHOOK_TOLERANCE_SECONDS", 300)
        if tolerance:
            try:
                sent_at = int(timestamp) / 1000 if len(timestamp) > 10 else int(timestamp)
            except ValueError:
                return False
            if abs(time.time() - sent_at) > tolerance:
                return False
        expected = base64.b64encode(
            hmac.new(secret.encode(), timestamp.encode() + raw_body, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(expected, signature)

    def parse_webhook_event(self, headers, raw_body: bytes) -> NormalizedEvent:
        try:
            payload = json.loads(raw_body)
        except ValueError as exc:
            raise WebhookParseError("webhook body is not JSON") from exc
        if not isinstance(payload, dict):
            raise WebhookParseError("webhook body is not a JSON object")

        data = payload.get("data") or {}
        subscription = data.get("subscription_details") or data.get("subscription") or {}
        payment = data.get("payment_details") or data.get("payment") or {}
        raw_type = str(payload.get("type") or "")

        if raw_type == "SUBSCRIPTION_STATUS_CHANGED":
            event_type = _STATUS_EVENT.get(
                str(subscription.get("subscription_status") or ""), EventType.UNKNOWN
            )
        else:
            event_type = _EVENT_MAP.get(raw_type, EventType.UNKNOWN)

        external_subscription_id = (
            subscription.get("subscription_id")
            or subscription.get("cf_subscription_id")
            or None
        )

        # Cashfree sends no per-delivery event id on subscription webhooks, so
        # the dedup key is a digest of the VERIFIED raw body. A genuine retry of
        # the same delivery is byte-identical and collides; a later, different
        # event (another renewal) hashes differently and is stored.
        external_event_id = hashlib.sha256(raw_body).hexdigest()

        period_start = parse_provider_datetime(payment.get("payment_time") or payment.get("cycle_start"))
        period_end = parse_provider_datetime(
            subscription.get("next_schedule_date") or payment.get("cycle_end")
        )

        return NormalizedEvent(
            event_type=event_type,
            external_event_id=external_event_id,
            external_subscription_id=str(external_subscription_id) if external_subscription_id else None,
            raw_payload=payload,
            period_start=period_start,
            period_end=period_end,
            event_created_at=parse_provider_datetime(payload.get("event_time")),
        )

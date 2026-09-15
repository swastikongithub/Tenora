"""The Cashfree property-payment adapter in isolation: request shape, response
translation, error classification, money conversion and webhook signature
verification with deterministic fixtures. No network."""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone as dt_timezone
from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from apps.properties.gateway.base import (
    CustomerDetails,
    GatewayRejected,
    GatewayUnavailable,
    IdempotencyConflict,
    OrderAlreadyExists,
    ProviderOrderStatus,
    ProviderPaymentStatus,
    WebhookEventKind,
    WebhookRejected,
)
from apps.properties.gateway.cashfree import CashfreePropertyPaymentGateway, cents_to_wire, wire_to_cents

SECRET = "fixture-secret"


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.content = json.dumps(payload).encode() if payload is not None else b""

    def json(self):
        return self._payload


def gateway(responses):
    session = mock.Mock()
    session.request.side_effect = responses
    return CashfreePropertyPaymentGateway(
        client_id="app_id", client_secret=SECRET, environment="sandbox", api_version="2025-01-01", session=session
    ), session


ORDER_ARGS = dict(
    order_id="TNRabc",
    amount_cents=1_078_055,
    currency="INR",
    customer=CustomerDetails(customer_id="res1", phone="9876543210", name="Rahul Sharma", email="rahul@example.com"),
    expires_at=datetime(2026, 4, 5, 10, 30, tzinfo=dt_timezone.utc),
    return_url="https://app/bills/1?online_payment=2",
    notify_url="https://api/api/webhooks/cashfree/property-payments/",
    note="Tenora bill BILL-1",
    tags={"tenora_attempt": "2"},
    idempotency_key="11111111-1111-1111-1111-111111111111",
)


class MoneyTests(SimpleTestCase):
    def test_integer_paise_round_trip_exactly(self):
        for cents in (100, 1_378_000, 1_078_055, 1, 99):
            self.assertEqual(wire_to_cents(json.loads(json.dumps(cents_to_wire(cents)))), cents)
        self.assertEqual(json.dumps(cents_to_wire(1_078_055)), "10780.55")

    def test_sub_paise_amounts_are_refused(self):
        with self.assertRaises(ValueError):
            wire_to_cents("10.005")


class CreateOrderTests(SimpleTestCase):
    def test_request_shape_headers_and_translation(self):
        gw, session = gateway([
            FakeResponse(200, {
                "cf_order_id": "2149460581", "order_id": "TNRabc", "payment_session_id": "session_xyz",
                "order_status": "ACTIVE", "order_expiry_time": "2026-04-05T16:00:00+05:30",
            })
        ])
        created = gw.create_payment_order(**ORDER_ARGS)
        method, url = session.request.call_args.args
        kwargs = session.request.call_args.kwargs
        self.assertEqual((method, url), ("POST", "https://sandbox.cashfree.com/pg/orders"))
        headers = kwargs["headers"]
        self.assertEqual(headers["x-api-version"], "2025-01-01")
        self.assertEqual(headers["x-client-id"], "app_id")
        self.assertEqual(headers["x-idempotency-key"], ORDER_ARGS["idempotency_key"])
        body = json.loads(kwargs["data"])
        self.assertEqual(body["order_amount"], 10780.55)
        self.assertIn('"order_amount": 10780.55', kwargs["data"])
        self.assertEqual(body["order_currency"], "INR")
        self.assertEqual(body["customer_details"]["customer_phone"], "9876543210")
        self.assertEqual(body["order_meta"]["notify_url"], ORDER_ARGS["notify_url"])
        self.assertEqual(body["order_expiry_time"], "2026-04-05T10:30:00+00:00")
        self.assertEqual((created.payment_session_id, created.status), ("session_xyz", ProviderOrderStatus.ACTIVE))

    def test_error_classification(self):
        cases = [
            (FakeResponse(409, {"code": "order_already_exists", "message": "order with same id is already present"}), OrderAlreadyExists),
            (FakeResponse(422, {"type": "idempotency_error", "code": "request_invalid", "message": "invalid body in request for x-idempotency-key"}), IdempotencyConflict),
            (FakeResponse(400, {"type": "invalid_request_error", "message": "customer_phone is invalid"}), GatewayRejected),
            (FakeResponse(401, {"type": "authentication_error", "message": "authentication Failed"}), GatewayRejected),
            (FakeResponse(500, {"type": "api_error"}), GatewayUnavailable),
            (FakeResponse(429, {"type": "rate_limit_error"}), GatewayUnavailable),
            (requests.ConnectTimeout("boom"), GatewayUnavailable),
        ]
        for response, expected in cases:
            with self.subTest(expected=expected.__name__):
                gw, _ = gateway([response])
                with self.assertRaises(expected):
                    gw.create_payment_order(**ORDER_ARGS)

    def test_missing_credentials_fail_closed_without_a_request(self):
        gw = CashfreePropertyPaymentGateway(client_id="", client_secret="", environment="sandbox", session=mock.Mock())
        with self.assertRaises(GatewayRejected):
            gw.create_payment_order(**ORDER_ARGS)
        gw.http.request.assert_not_called()


class StatusAndRefundTests(SimpleTestCase):
    def test_payments_for_order_are_translated(self):
        gw, session = gateway([FakeResponse(200, [
            {"cf_payment_id": 12376123, "payment_status": "SUCCESS", "payment_amount": 10780.55, "payment_currency": "INR", "payment_message": "ok"},
            {"cf_payment_id": "9", "payment_status": "VOID", "payment_amount": 1, "payment_currency": "INR"},
        ])])
        payments = gw.get_payment_status("TNRabc")
        self.assertEqual(session.request.call_args.args, ("GET", "https://sandbox.cashfree.com/pg/orders/TNRabc/payments"))
        self.assertEqual((payments[0].status, payments[0].amount_cents), (ProviderPaymentStatus.SUCCESS, 1_078_055))
        self.assertEqual(payments[1].status, ProviderPaymentStatus.CANCELLED)

    def test_refund_is_idempotent_on_refund_id(self):
        gw, session = gateway([
            FakeResponse(409, {"code": "refund_already_exists"}),
            FakeResponse(200, {"refund_id": "RFabc", "refund_status": "SUCCESS", "refund_amount": 10780.55}),
        ])
        result = gw.refund_payment(order_id="TNRabc", refund_id="RFabc", amount_cents=1_078_055, note="n", idempotency_key="k")
        self.assertEqual(session.request.call_args_list[1].args, ("GET", "https://sandbox.cashfree.com/pg/orders/TNRabc/refunds/RFabc"))
        self.assertEqual((result.status, result.amount_cents), ("SUCCESS", 1_078_055))


class WebhookSignatureTests(SimpleTestCase):
    RAW = (
        b'{"data":{"order":{"order_id":"TNRabc","order_amount":10780.55,"order_currency":"INR"},'
        b'"payment":{"cf_payment_id":"5114933189368","payment_status":"SUCCESS","payment_amount":10780.55,'
        b'"payment_currency":"INR","payment_message":"ok"}},"event_time":"2026-04-05T10:00:00+05:30",'
        b'"type":"PAYMENT_SUCCESS_WEBHOOK"}'
    )

    def headers(self, raw, ts=None, secret=SECRET):
        ts = str(ts or int(time.time() * 1000))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + raw, hashlib.sha256).digest()).decode()
        return {"x-webhook-signature": sig, "x-webhook-timestamp": ts}

    @override_settings(CASHFREE_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_valid_signature_over_timestamp_plus_raw_body(self):
        gw, _ = gateway([])
        gw.verify_webhook(self.headers(self.RAW), self.RAW)
        event = gw.parse_webhook({}, self.RAW)
        self.assertEqual(event.kind, WebhookEventKind.PAYMENT_SUCCESS)
        self.assertEqual((event.order_id, event.payment.amount_cents), ("TNRabc", 1_078_055))
        self.assertEqual(event.dedupe_key, hashlib.sha256(self.RAW).hexdigest())

    def test_known_vector(self):
        # Fixed timestamp + body + secret -> a fixed Base64 signature, computed
        # independently of the adapter.
        ts = "1617695238078"
        expected = base64.b64encode(hmac.new(SECRET.encode(), (ts + self.RAW.decode()).encode(), hashlib.sha256).digest()).decode()
        gw, _ = gateway([])
        with override_settings(CASHFREE_WEBHOOK_TOLERANCE_SECONDS=0):
            gw.verify_webhook({"x-webhook-signature": expected, "x-webhook-timestamp": ts}, self.RAW)

    @override_settings(CASHFREE_WEBHOOK_TOLERANCE_SECONDS=300)
    def test_rejections(self):
        gw, _ = gateway([])
        good = self.headers(self.RAW)
        cases = {
            "missing_signature": ({}, self.RAW),
            "bad_signature": (self.headers(self.RAW, secret="wrong"), self.RAW),
            "tampered_body": (good, self.RAW.replace(b"10780.55", b"1.00")),
            "stale_timestamp": (self.headers(self.RAW, ts=int((time.time() - 3600) * 1000)), self.RAW),
        }
        for name, (headers, raw) in cases.items():
            with self.subTest(name):
                with self.assertRaises(WebhookRejected):
                    gw.verify_webhook(headers, raw)

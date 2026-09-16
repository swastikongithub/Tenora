"""
The Cashfree Subscriptions adapter in isolation: request shapes, response
translation, failure classification, mandate-status mapping and webhook
signature verification, against deterministic fixtures. No network.

The Tenora subscription domain only — nothing here touches P9's property
payments, which speak a different Cashfree API through their own adapter.
"""

import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest import mock

import requests
from django.test import TestCase, override_settings

from apps.billing.gateway import EventType, ProviderUnavailable, WebhookParseError
from apps.billing.gateway.base import ProviderSubscriptionStatus, SubscriberContactRequired
from apps.billing.gateway.cashfree import CashfreeSubscriptionGatewayAdapter, cents_to_amount
from apps.properties.tests.factories import make_workspace

CLIENT_ID = "sub_app_id"
SECRET = "sub-fixture-secret"

SETTINGS = dict(
    CASHFREE_SUBSCRIPTION_CLIENT_ID=CLIENT_ID,
    CASHFREE_SUBSCRIPTION_CLIENT_SECRET=SECRET,
    CASHFREE_SUBSCRIPTION_ENVIRONMENT="sandbox",
    CASHFREE_SUBSCRIPTION_API_VERSION="2026-01-01",
    FRONTEND_URL="https://app.example.com",
)


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.content = json.dumps(payload).encode() if payload is not None else b""

    def json(self):
        return self._payload


def adapter(responses=()):
    session = mock.Mock()
    session.request.side_effect = list(responses)
    return CashfreeSubscriptionGatewayAdapter(session=session), session


def plan(code="PRO", interval="MONTHLY", price_cents=200_000):
    return SimpleNamespace(
        code=code, name="Pro", interval=interval, price_cents=price_cents,
        currency="INR", external_plan_id="tenora_pro",
    )


@override_settings(**SETTINGS)
class MoneyTests(TestCase):
    def test_paise_convert_to_major_units_exactly(self):
        self.assertEqual(cents_to_amount(200_000), 2000.0)
        self.assertEqual(cents_to_amount(50_050), 500.5)
        self.assertEqual(cents_to_amount(1), 0.01)


@override_settings(**SETTINGS)
class CreatePlanTests(TestCase):
    def test_request_shape_and_returned_id(self):
        gw, session = adapter([FakeResponse(200, {"plan_id": "tenora_pro"})])
        self.assertEqual(gw.create_plan(plan()), "tenora_pro")
        method, url = session.request.call_args.args
        body = json.loads(session.request.call_args.kwargs["data"])
        headers = session.request.call_args.kwargs["headers"]
        self.assertEqual((method, url), ("POST", "https://sandbox.cashfree.com/pg/plans"))
        self.assertEqual(headers["x-api-version"], "2026-01-01")
        self.assertEqual(headers["x-client-id"], CLIENT_ID)
        self.assertEqual(body["plan_type"], "PERIODIC")
        self.assertEqual(body["plan_amount"], 2000.0)
        self.assertEqual((body["plan_interval_type"], body["plan_intervals"]), ("MONTH", 1))

    def test_annual_plans_use_a_yearly_interval(self):
        gw, session = adapter([FakeResponse(200, {"plan_id": "tenora_pro_annual"})])
        gw.create_plan(plan(code="PRO_ANNUAL", interval="ANNUAL"))
        body = json.loads(session.request.call_args.kwargs["data"])
        self.assertEqual((body["plan_interval_type"], body["plan_intervals"]), ("YEAR", 1))

    def test_an_already_mirrored_plan_is_not_an_error(self):
        # Cashfree's docs don't pin the status code for a duplicate plan id, so
        # both shapes it can take are treated as "already mirrored".
        for response in (
            FakeResponse(409, {"message": "plan already exists"}),
            FakeResponse(400, {"message": "plan_id already exists"}),
            FakeResponse(422, {"code": "duplicate_plan_id"}),
        ):
            with self.subTest(status=response.status_code):
                gw, _ = adapter([response])
                self.assertEqual(gw.create_plan(plan()), "tenora_pro")

    def test_a_genuine_validation_error_is_not_mistaken_for_a_duplicate(self):
        gw, _ = adapter([FakeResponse(400, {"message": "plan_amount is invalid"})])
        with self.assertRaises(ProviderUnavailable):
            gw.create_plan(plan())

    def test_server_errors_and_transport_failures_are_unavailable(self):
        for response in (FakeResponse(500, {}), requests.ConnectTimeout("boom")):
            gw, _ = adapter([response])
            with self.assertRaises(ProviderUnavailable):
                gw.create_plan(plan())

    def test_a_rejection_is_logged_with_the_providers_error_but_no_secrets(self):
        gw, _ = adapter([
            FakeResponse(400, {
                "code": "plan_recurring_amount_missing",
                "type": "invalid_request_error",
                "message": "plan_recurring_amount is required for PERIODIC plans",
            })
        ])
        with self.assertLogs("apps.billing.gateway.cashfree", level="WARNING") as logs:
            with self.assertRaises(ProviderUnavailable) as raised:
                gw.create_plan(plan())
        line = chr(10).join(logs.output)
        # The provider's own identification of the problem reaches the log…
        self.assertIn("plan_recurring_amount_missing", line)
        self.assertIn("invalid_request_error", line)
        self.assertIn("POST /plans", line)
        self.assertIn("400", line)
        # …and so does the exception, which the platform view logs.
        self.assertIn("plan_recurring_amount_missing", str(raised.exception))
        # Credentials never appear: they are headers, and headers are not logged.
        self.assertNotIn(SECRET, line)
        self.assertNotIn(CLIENT_ID, line)

    def test_a_subscription_rejection_never_logs_subscriber_contact_details(self):
        tenant, owner = make_workspace("cf-log")
        owner.phone = "9876543210"
        owner.save(update_fields=["phone"])
        gw, _ = adapter([FakeResponse(400, {"code": "plan_id_invalid", "message": "no such plan"})])
        with self.assertLogs("apps.billing.gateway.cashfree", level="WARNING") as logs:
            with self.assertRaises(ProviderUnavailable):
                gw.create_subscription(tenant, plan())
        line = chr(10).join(logs.output)
        self.assertIn("plan_id_invalid", line)
        self.assertIn("<redacted>", line)
        self.assertNotIn("9876543210", line)
        self.assertNotIn(owner.email, line)
        self.assertNotIn(SECRET, line)

    def test_missing_credentials_fail_closed_without_a_request(self):
        with override_settings(CASHFREE_SUBSCRIPTION_CLIENT_ID="", CASHFREE_SUBSCRIPTION_CLIENT_SECRET=""):
            gw, session = adapter([FakeResponse(200, {})])
            with self.assertRaises(ProviderUnavailable):
                gw.create_plan(plan())
            session.request.assert_not_called()


@override_settings(**SETTINGS)
class CreateSubscriptionTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = make_workspace("cashfree-subs")
        self.owner.phone = "9876543210"
        self.owner.save(update_fields=["phone"])

    def test_mandate_request_carries_plan_customer_and_return_url(self):
        gw, session = adapter([
            FakeResponse(200, {
                "subscription_id": "tnrsub_x", "cf_subscription_id": "999",
                "subscription_status": "INITIALIZED",
                "subscription_session_id": "sess_abc",
            })
        ])
        created = gw.create_subscription(self.tenant, plan())

        method, url = session.request.call_args.args
        body = json.loads(session.request.call_args.kwargs["data"])
        self.assertEqual((method, url), ("POST", "https://sandbox.cashfree.com/pg/subscriptions"))
        self.assertEqual(body["plan_details"], {"plan_id": "tenora_pro"})
        self.assertEqual(body["customer_details"]["customer_phone"], "9876543210")
        self.assertEqual(body["customer_details"]["customer_email"], self.owner.email)
        self.assertEqual(body["subscription_meta"]["return_url"], "https://app.example.com/subscription")
        self.assertEqual(body["subscription_tags"]["tenant_id"], str(self.tenant.id))
        # Recurring, not a one-off charge.
        self.assertIn("upi", body["authorization_details"]["payment_methods"])

        self.assertEqual(created.provider, "cashfree")
        self.assertEqual(created.external_subscription_id, "tnrsub_x")
        self.assertEqual(created.session_token, "sess_abc")
        self.assertEqual(created.public_key, "")  # never a key or secret
        self.assertEqual(created.mode, "sandbox")

    def test_an_owner_without_a_phone_is_told_to_add_one(self):
        self.owner.phone = ""
        self.owner.save(update_fields=["phone"])
        gw, session = adapter([FakeResponse(200, {})])
        with self.assertRaises(SubscriberContactRequired):
            gw.create_subscription(self.tenant, plan())
        session.request.assert_not_called()

    def test_a_response_without_a_session_is_unavailable_not_a_half_checkout(self):
        gw, _ = adapter([FakeResponse(200, {"subscription_id": "s", "subscription_session_id": ""})])
        with self.assertRaises(ProviderUnavailable):
            gw.create_subscription(self.tenant, plan())

    def test_rejections_are_unavailable(self):
        gw, _ = adapter([FakeResponse(400, {"message": "plan_id is invalid"})])
        with self.assertRaises(ProviderUnavailable):
            gw.create_subscription(self.tenant, plan())


@override_settings(**SETTINGS)
class SubscriptionStateTests(TestCase):
    def test_statuses_map_to_the_reconciliation_vocabulary(self):
        cases = {
            "INITIALIZED": ProviderSubscriptionStatus.PENDING,
            "BANK_APPROVAL_PENDING": ProviderSubscriptionStatus.PENDING,
            "ACTIVE": ProviderSubscriptionStatus.ACTIVE,
            "ON_HOLD": ProviderSubscriptionStatus.PAST_DUE,
            "PAUSED": ProviderSubscriptionStatus.PENDING,
            "CANCELLED": ProviderSubscriptionStatus.CANCELED,
            "COMPLETED": ProviderSubscriptionStatus.CANCELED,
            "SOMETHING_NEW": ProviderSubscriptionStatus.UNKNOWN,
        }
        for raw, expected in cases.items():
            with self.subTest(raw):
                gw, _ = adapter([FakeResponse(200, {"subscription_status": raw})])
                state = gw.fetch_subscription_state("tnrsub_x")
                self.assertEqual(state.status, expected)
                self.assertEqual(state.raw_status, raw)

    def test_an_unknown_subscription_is_none_not_an_outage(self):
        gw, _ = adapter([FakeResponse(404, {"message": "not found"})])
        self.assertIsNone(gw.fetch_subscription_state("tnrsub_missing"))

    def test_an_outage_is_distinct_from_not_found(self):
        gw, _ = adapter([FakeResponse(503, {})])
        with self.assertRaises(ProviderUnavailable):
            gw.fetch_subscription_state("tnrsub_x")

    def test_confirm_reads_the_mandate_and_ignores_the_browsers_report(self):
        gw, session = adapter([FakeResponse(200, {"subscription_status": "ACTIVE"})])
        self.assertTrue(gw.confirm_checkout_report("tnrsub_x", {"anything": "the client says"}))
        self.assertEqual(session.request.call_args.args[0], "GET")

    def test_confirm_is_false_when_the_mandate_is_not_authorised(self):
        gw, _ = adapter([FakeResponse(200, {"subscription_status": "CANCELLED"})])
        self.assertFalse(gw.confirm_checkout_report("tnrsub_x", {}))

    def test_confirm_is_false_when_the_provider_cannot_be_reached(self):
        gw, _ = adapter([requests.ConnectTimeout("boom")])
        self.assertFalse(gw.confirm_checkout_report("tnrsub_x", {}))

    def test_a_browser_signature_is_never_accepted_for_this_provider(self):
        gw, _ = adapter([])
        self.assertFalse(gw.verify_checkout_signature("pay", "sub", "sig"))


def signed(raw, ts=None, secret=SECRET):
    ts = str(ts or int(time.time() * 1000))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + raw, hashlib.sha256).digest()).decode()
    return {"x-webhook-signature": sig, "x-webhook-timestamp": ts}


ACTIVATED = json.dumps({
    "type": "SUBSCRIPTION_STATUS_CHANGED",
    "event_time": "2026-09-16T10:00:00+05:30",
    "data": {"subscription_details": {
        "subscription_id": "tnrsub_x", "cf_subscription_id": "999",
        "subscription_status": "ACTIVE", "next_schedule_date": "2026-10-16T00:00:00+05:30",
    }},
}).encode()

CHARGED = json.dumps({
    "type": "SUBSCRIPTION_PAYMENT_SUCCESS",
    "event_time": "2026-10-16T10:00:00+05:30",
    "data": {
        "subscription_details": {"subscription_id": "tnrsub_x", "next_schedule_date": "2026-11-16T00:00:00+05:30"},
        "payment_details": {"cf_payment_id": "5114", "payment_amount": 2000.0, "payment_time": "2026-10-16T09:59:00+05:30"},
    },
}).encode()


@override_settings(**SETTINGS, CASHFREE_SUBSCRIPTION_WEBHOOK_TOLERANCE_SECONDS=300)
class WebhookSignatureTests(TestCase):
    def test_a_valid_signature_over_timestamp_plus_raw_body_is_accepted(self):
        gw, _ = adapter([])
        self.assertTrue(gw.verify_webhook_signature(signed(ACTIVATED), ACTIVATED))

    def test_missing_wrong_stale_and_tampered_deliveries_are_rejected(self):
        gw, _ = adapter([])
        good = signed(ACTIVATED)
        cases = {
            "missing": ({}, ACTIVATED),
            "wrong_secret": (signed(ACTIVATED, secret="not-it"), ACTIVATED),
            "stale": (signed(ACTIVATED, ts=int((time.time() - 3600) * 1000)), ACTIVATED),
            "tampered_body": (good, ACTIVATED.replace(b"ACTIVE", b"ON_HOLD")),
            "malformed_timestamp": ({**good, "x-webhook-timestamp": "not-a-time"}, ACTIVATED),
        }
        for name, (headers, raw) in cases.items():
            with self.subTest(name):
                self.assertFalse(gw.verify_webhook_signature(headers, raw))

    def test_the_property_payment_secret_does_not_verify_subscription_webhooks(self):
        # The two Cashfree domains must not be interchangeable even though the
        # signature construction looks alike.
        gw, _ = adapter([])
        with override_settings(CASHFREE_CLIENT_SECRET="p9-secret"):
            self.assertFalse(
                gw.verify_webhook_signature(signed(ACTIVATED, secret="p9-secret"), ACTIVATED)
            )


@override_settings(**SETTINGS)
class WebhookParsingTests(TestCase):
    def parse(self, raw):
        gw, _ = adapter([])
        return gw.parse_webhook_event(signed(raw), raw)

    def test_an_authorised_mandate_is_an_activation(self):
        event = self.parse(ACTIVATED)
        self.assertEqual(event.event_type, EventType.ACTIVATED)
        self.assertEqual(event.external_subscription_id, "tnrsub_x")
        self.assertIsNotNone(event.event_created_at)

    def test_a_recurring_charge_is_a_renewal_and_carries_the_next_period(self):
        event = self.parse(CHARGED)
        self.assertEqual(event.event_type, EventType.CHARGED)
        self.assertEqual(event.period_end.isoformat(), "2026-11-15T18:30:00+00:00")

    def test_status_changes_map_to_the_project_vocabulary(self):
        cases = {
            "ON_HOLD": EventType.PAYMENT_TROUBLE,
            "CANCELLED": EventType.CANCELLED,
            "CUSTOMER_CANCELLED": EventType.CANCELLED,
            "EXPIRED": EventType.CANCELLED,
            "COMPLETED": EventType.CANCELLED,
        }
        for raw_status, expected in cases.items():
            with self.subTest(raw_status):
                raw = ACTIVATED.replace(b'"subscription_status": "ACTIVE"', f'"subscription_status": "{raw_status}"'.encode())
                self.assertEqual(self.parse(raw).event_type, expected)

    def test_a_merchant_pause_changes_no_subscription_state(self):
        raw = ACTIVATED.replace(b'"subscription_status": "ACTIVE"', b'"subscription_status": "PAUSED"')
        self.assertEqual(self.parse(raw).event_type, EventType.UNKNOWN)

    def test_a_failed_recurring_charge_is_payment_trouble(self):
        raw = CHARGED.replace(b"SUBSCRIPTION_PAYMENT_SUCCESS", b"SUBSCRIPTION_PAYMENT_FAILED")
        self.assertEqual(self.parse(raw).event_type, EventType.PAYMENT_TROUBLE)

    def test_unknown_event_types_are_parsed_but_not_acted_on(self):
        raw = ACTIVATED.replace(b"SUBSCRIPTION_STATUS_CHANGED", b"SUBSCRIPTION_CARD_EXPIRY_REMINDER")
        self.assertEqual(self.parse(raw).event_type, EventType.UNKNOWN)

    def test_the_dedupe_key_is_the_digest_of_the_verified_body(self):
        event = self.parse(ACTIVATED)
        self.assertEqual(event.external_event_id, hashlib.sha256(ACTIVATED).hexdigest())
        # A redelivery is byte-identical, so it collides on the same key…
        self.assertEqual(self.parse(ACTIVATED).external_event_id, event.external_event_id)
        # …while a later, genuinely different event does not.
        self.assertNotEqual(self.parse(CHARGED).external_event_id, event.external_event_id)

    def test_a_body_that_is_not_a_json_object_is_refused(self):
        gw, _ = adapter([])
        for raw in (b"not json", b"[1, 2]"):
            with self.subTest(raw=raw):
                with self.assertRaises(WebhookParseError):
                    gw.parse_webhook_event({}, raw)

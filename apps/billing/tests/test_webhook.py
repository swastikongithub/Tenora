"""
POST /api/webhooks/razorpay/ — endpoint behaviour (stage-d1-spec.md §4.4 / §9),
now going through the active gateway adapter.

The signature is a REAL HMAC (not mocked), so `RazorpayGatewayAdapter
.verify_webhook_signature` genuinely runs — same principle as the subscription
API tests minting real JWTs. The adapter's own methods (name mapping, id
extraction) are covered in test_gateway_razorpay.py.
"""

import hashlib
import hmac
import json
from unittest import mock

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.gateway import MockGatewayAdapter
from apps.billing.models import Subscription, WebhookEvent

URL = "/api/webhooks/razorpay/"
SECRET = "whsec_test_d1"

EVENT_ID = "evt_test_00000000000001"
PAYLOAD = {
    "entity": "event",
    "account_id": "acc_TESTACCOUNT",
    "event": "subscription.activated",
    "contains": ["subscription"],
    "payload": {
        "subscription": {"entity": {"id": "sub_TEST123", "status": "active"}}
    },
    "created_at": 1725000000,
}


def _sign(raw_body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


@override_settings(PAYMENT_GATEWAY="razorpay", RAZORPAY_WEBHOOK_SECRET=SECRET)
class RazorpayWebhookTests(APITestCase):
    def _post(self, raw_body: bytes, *, signature=None, event_id=EVENT_ID):
        extra = {"content_type": "application/json"}
        if signature is not None:
            extra["HTTP_X_RAZORPAY_SIGNATURE"] = signature
        if event_id is not None:
            extra["HTTP_X_RAZORPAY_EVENT_ID"] = event_id
        return self.client.post(URL, data=raw_body, **extra)

    def test_valid_signature_and_event_id_stores_the_event(self):
        raw = json.dumps(PAYLOAD).encode()

        resp = self._post(raw, signature=_sign(raw))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        event = WebhookEvent.objects.get()
        self.assertEqual(event.external_event_id, EVENT_ID)
        # Stored as the project vocabulary now (the adapter mapped
        # "subscription.activated" → ACTIVATED); the raw name stays in the payload.
        self.assertEqual(event.event_type, "ACTIVATED")
        self.assertEqual(event.raw_payload["event"], "subscription.activated")
        self.assertEqual(event.raw_payload, PAYLOAD)
        # D3: the event is processed inline after storage. This ACTIVATED
        # fixture matches no SubscriptionCheckout, so processing is a logged
        # no-op — but the row is still marked processed (it has been handled).
        self.assertTrue(event.processed)
        self.assertEqual(event.external_subscription_id, "sub_TEST123")
        self.assertEqual(Subscription.objects.count(), 0)

    def test_tampered_body_is_rejected_and_nothing_is_stored(self):
        raw = json.dumps(PAYLOAD).encode()
        good_sig = _sign(raw)
        tampered = json.dumps({**PAYLOAD, "event": "subscription.charged"}).encode()

        resp = self._post(tampered, signature=good_sig)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_signature_from_a_different_secret_is_rejected(self):
        raw = json.dumps(PAYLOAD).encode()

        resp = self._post(raw, signature=_sign(raw, "not-the-real-secret"))

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_missing_signature_header_is_a_clean_400(self):
        raw = json.dumps(PAYLOAD).encode()

        resp = self._post(raw, signature=None)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_missing_event_id_header_is_a_400_even_with_a_valid_signature(self):
        raw = json.dumps(PAYLOAD).encode()

        resp = self._post(raw, signature=_sign(raw), event_id=None)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_valid_signature_but_body_is_not_json_is_a_400(self):
        raw = b"this is not json"

        resp = self._post(raw, signature=_sign(raw))

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_valid_signature_but_json_body_is_not_an_object_is_a_400(self):
        raw = b"[1, 2, 3]"

        resp = self._post(raw, signature=_sign(raw))

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_the_same_event_delivered_twice_stores_exactly_one_row(self):
        # Razorpay's own docs describe at-least-once delivery — a redelivery is
        # expected, not a bug. Second POST is a 200 no-op.
        raw = json.dumps(PAYLOAD).encode()
        sig = _sign(raw)

        first = self._post(raw, signature=sig)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        original = WebhookEvent.objects.get()

        second = self._post(raw, signature=sig)
        self.assertEqual(second.status_code, status.HTTP_200_OK)

        self.assertEqual(WebhookEvent.objects.count(), 1)
        unchanged = WebhookEvent.objects.get()
        self.assertEqual(unchanged.id, original.id)
        self.assertEqual(unchanged.received_at, original.received_at)
        # Processed on the first delivery; the redelivery re-runs processing,
        # which no-ops on the already-processed row (D3 idempotency).
        self.assertTrue(unchanged.processed)


@override_settings(PAYMENT_GATEWAY="mock")
class MockGatewayWebhookTests(APITestCase):
    """The same endpoint contract holds with a completely different adapter —
    proof the view itself is provider-neutral."""

    def _post(self, body: dict, *, event_id="mock_evt_1"):
        extra = {"content_type": "application/json"}
        if event_id is not None:
            extra["HTTP_X_MOCK_EVENT_ID"] = event_id
        return self.client.post(URL, data=json.dumps(body).encode(), **extra)

    def test_valid_mock_event_is_stored_normalized(self):
        resp = self._post({"type": "ACTIVATED", "subscription_id": "mock_sub_9"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        event = WebhookEvent.objects.get()
        self.assertEqual(event.external_event_id, "mock_evt_1")
        self.assertEqual(event.event_type, "ACTIVATED")

    def test_missing_event_id_is_400(self):
        resp = self._post({"type": "CHARGED"}, event_id=None)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_invalid_signature_is_400(self):
        with mock.patch(
            "apps.billing.views.get_gateway",
            return_value=MockGatewayAdapter(webhook_signature_valid=False),
        ):
            resp = self._post({"type": "ACTIVATED", "subscription_id": "s"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WebhookEvent.objects.count(), 0)

"""
P9 online resident payments (Cashfree), exercised through the real API with
real JWTs and the mock property gateway. Webhooks are signed with the exact
Cashfree construction (Base64 HMAC-SHA256 over timestamp + raw body) using a
deterministic test secret — nothing here marks a bill paid directly.
"""

import base64
import hashlib
import hmac
import json
import threading
import time
from datetime import date, timedelta
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.properties.gateway.base import GatewayRejected, GatewayUnavailable, ProviderPaymentStatus
from apps.properties.gateway.mock import MockPropertyPaymentGateway
from apps.properties.models import Bill, OnlinePaymentAttempt, Payment, PropertyPaymentWebhookEvent, Receipt
from apps.properties.online_payments import OnlinePaymentService
from apps.properties.services import PaymentService
from apps.properties.tests.factories import Scenario, add_resident, bearer

SECRET = "cf_test_secret_do_not_use"
WEBHOOK = "/api/webhooks/cashfree/property-payments/"

P9_SETTINGS = dict(
    PROPERTY_ONLINE_PAYMENTS_ENABLED=True,
    PROPERTY_PAYMENT_GATEWAY="mock",
    CASHFREE_CLIENT_SECRET=SECRET,
    CASHFREE_WEBHOOK_TOLERANCE_SECONDS=3600,
    FRONTEND_URL="https://app.tenora.test",
    BACKEND_PUBLIC_URL="https://api.tenora.test",
)


def signed_headers(raw_body: bytes, *, timestamp=None, secret=SECRET):
    ts = str(timestamp if timestamp is not None else int(time.time() * 1000))
    signature = base64.b64encode(hmac.new(secret.encode(), ts.encode() + raw_body, hashlib.sha256).digest()).decode()
    return {"HTTP_X_WEBHOOK_SIGNATURE": signature, "HTTP_X_WEBHOOK_TIMESTAMP": ts, "HTTP_X_WEBHOOK_VERSION": "2025-01-01"}


def success_body(attempt, *, amount=None, currency="INR", payment_id="5114933189368", status="SUCCESS", kind="PAYMENT_SUCCESS_WEBHOOK"):
    cents = attempt.amount_cents if amount is None else amount
    # A raw JSON string with a 2-dp decimal amount, exactly as a provider sends it.
    return (
        '{"data":{"order":{"order_id":"%s","order_amount":%d.%02d,"order_currency":"INR"},'
        '"payment":{"cf_payment_id":"%s","payment_status":"%s","payment_amount":%d.%02d,'
        '"payment_currency":"%s","payment_message":"Simulated","payment_group":"upi"}},'
        '"event_time":"2026-04-05T10:00:00+05:30","type":"%s"}'
        % (attempt.provider_order_id, cents // 100, cents % 100, payment_id, status, cents // 100, cents % 100, currency, kind)
    ).encode()


def phone(scenario, number="9876543210"):
    scenario.resident.phone = number
    scenario.resident.save(update_fields=["phone"])


@override_settings(**P9_SETTINGS)
class OnlinePaymentTestBase(APITestCase):
    def setUp(self):
        MockPropertyPaymentGateway.reset()
        self.s = Scenario(slug="sunrise")
        phone(self.s)
        self.bill = self.s.march_bill()  # published, 13,780.00 due

    def as_resident(self, scenario=None):
        scenario = scenario or self.s
        bearer(self.client, scenario.user, scenario.tenant)

    def start(self, body=None, bill=None, expect=201):
        resp = self.client.post(f"/api/bills/{(bill or self.bill).id}/online-payment/", body or {}, format="json")
        self.assertEqual(resp.status_code, expect, getattr(resp, "data", resp.content))
        return resp

    def webhook(self, raw, headers=None, expect=200):
        resp = self.client.generic("POST", WEBHOOK, raw, content_type="application/json", **(headers if headers is not None else signed_headers(raw)))
        self.assertEqual(resp.status_code, expect, resp.content)
        return resp


class AuthorizationTests(OnlinePaymentTestBase):
    def test_resident_can_start_payment_for_own_published_bill(self):
        self.as_resident()
        data = self.start().data
        self.assertEqual(data["amount_cents"], 1_378_000)
        self.assertEqual(data["currency"], "INR")
        self.assertTrue(data["payment_session_id"].startswith("session_"))
        self.assertEqual(data["checkout_mode"], "sandbox")
        self.assertEqual(data["display_state"], "processing")
        for leaked in ("payload", "client_secret", "idempotency_key"):
            self.assertNotIn(leaked, data)

    def test_another_resident_in_the_workspace_gets_404(self):
        other, _ = add_resident(self.s.tenant, self.s.owner, "priya@example.com", first_name="Priya")
        bearer(self.client, other, self.s.tenant)
        self.start(expect=404)
        self.assertFalse(OnlinePaymentAttempt.objects.exists())

    def test_the_owner_cannot_pay_a_residents_bill(self):
        bearer(self.client, self.s.owner, self.s.tenant)
        self.start(expect=404)

    def test_a_bill_from_another_workspace_is_404(self):
        b = Scenario(slug="green-valley")
        phone(b)
        other_bill = b.march_bill()
        self.as_resident()
        self.start(bill=other_bill, expect=404)

    def test_unauthenticated_is_rejected(self):
        resp = self.client.post(f"/api/bills/{self.bill.id}/online-payment/", {}, format="json", HTTP_X_TENANT_ID=str(self.s.tenant.id))
        self.assertEqual(resp.status_code, 401)

    @override_settings(PROPERTY_ONLINE_PAYMENTS_ENABLED=False)
    def test_disabled_workspace_setting_refuses(self):
        self.as_resident()
        self.assertEqual(self.start(expect=409).data["code"], "ONLINE_PAYMENTS_DISABLED")

    def test_a_resident_without_a_phone_is_told_to_add_one(self):
        phone(self.s, "")
        self.as_resident()
        self.assertEqual(self.start(expect=409).data["code"], "PHONE_REQUIRED")


class AmountTests(OnlinePaymentTestBase):
    def test_client_supplied_amount_and_ids_are_ignored(self):
        self.as_resident()
        for body in ({"amount": 1}, {"amount": 999999, "amount_cents": 1, "tenant_id": "x", "resident_id": "y"}):
            MockPropertyPaymentGateway.reset()
            OnlinePaymentAttempt.objects.all().delete()
            data = self.start(body=body).data
            self.assertEqual(data["amount_cents"], 1_378_000)
            call = MockPropertyPaymentGateway.state.calls[-1][1]
            self.assertEqual(call["amount_cents"], 1_378_000)

    def test_a_partially_offline_paid_bill_charges_only_the_remainder(self):
        self.s.pay(self.bill, 300_000)
        self.as_resident()
        self.assertEqual(self.start().data["amount_cents"], 1_078_000)

    def test_a_paid_bill_cannot_start_an_online_payment(self):
        self.s.pay(self.bill, 1_378_000)
        self.as_resident()
        self.assertEqual(self.start(expect=409).data["code"], "BILL_NOT_PAYABLE")

    def test_bill_detail_reports_eligibility_per_viewer(self):
        self.as_resident()
        block = self.client.get(f"/api/bills/{self.bill.id}/").data["online_payment"]
        self.assertEqual((block["available"], block["amount_cents"]), (True, 1_378_000))
        bearer(self.client, self.s.owner, self.s.tenant)
        self.assertEqual(self.client.get(f"/api/bills/{self.bill.id}/").data["online_payment"]["reason"], "NOT_RESIDENT")
        self.s.pay(self.bill, 1_378_000)
        self.as_resident()
        self.assertEqual(self.client.get(f"/api/bills/{self.bill.id}/").data["online_payment"]["reason"], "NOTHING_DUE")


class OrderCreationTests(OnlinePaymentTestBase):
    def test_the_provider_order_carries_authoritative_details(self):
        self.as_resident()
        data = self.start().data
        attempt = OnlinePaymentAttempt.objects.get()
        name, call = MockPropertyPaymentGateway.state.calls[-1]
        self.assertEqual(name, "create_payment_order")
        self.assertEqual(call["order_id"], attempt.provider_order_id)
        self.assertEqual((call["amount_cents"], call["currency"]), (1_378_000, "INR"))
        self.assertEqual(call["customer"].phone, "9876543210")
        self.assertEqual(call["customer"].customer_id, self.s.resident.id.hex)
        self.assertEqual(call["idempotency_key"], str(attempt.idempotency_key))
        self.assertEqual(call["return_url"], f"https://app.tenora.test/bills/{self.bill.id}?online_payment={attempt.id}")
        self.assertEqual(data["order_id"], attempt.provider_order_id)
        self.assertEqual(attempt.status, OnlinePaymentAttempt.Status.ACTIVE)

    def test_a_repeated_click_reuses_the_open_checkout(self):
        self.as_resident()
        first = self.start().data
        second = self.start().data
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["payment_session_id"], second["payment_session_id"])
        self.assertEqual(OnlinePaymentAttempt.objects.count(), 1)
        self.assertEqual(len(MockPropertyPaymentGateway.state.orders), 1)

    def test_a_provider_timeout_is_retried_with_the_same_order_id_and_key(self):
        self.as_resident()
        MockPropertyPaymentGateway.state.fail_next = GatewayUnavailable("timeout")
        self.assertEqual(self.start(expect=503).data["code"], "PAYMENT_PROVIDER_UNAVAILABLE")
        attempt = OnlinePaymentAttempt.objects.get()
        self.assertEqual(attempt.status, OnlinePaymentAttempt.Status.CREATED)

        self.start()
        calls = [c for n, c in MockPropertyPaymentGateway.state.calls if n == "create_payment_order"]
        self.assertEqual(len(calls), 2)
        self.assertEqual({c["order_id"] for c in calls}, {attempt.provider_order_id})
        self.assertEqual({c["idempotency_key"] for c in calls}, {str(attempt.idempotency_key)})
        self.assertEqual(OnlinePaymentAttempt.objects.count(), 1)

    def test_a_provider_rejection_fails_the_attempt_and_a_retry_starts_fresh(self):
        self.as_resident()
        MockPropertyPaymentGateway.state.fail_next = GatewayRejected("customer_phone is invalid")
        self.assertEqual(self.start(expect=502).data["code"], "PAYMENT_PROVIDER_REJECTED")
        failed = OnlinePaymentAttempt.objects.get()
        self.assertEqual(failed.status, OnlinePaymentAttempt.Status.FAILED)
        new = self.start().data
        self.assertNotEqual(new["id"], str(failed.id))

    def test_a_changed_bill_replaces_the_open_checkout(self):
        self.as_resident()
        first = self.start().data
        self.s.pay(self.bill, 100_000)
        second = self.start().data
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(second["amount_cents"], 1_278_000)
        self.assertEqual(OnlinePaymentAttempt.objects.get(pk=first["id"]).status, OnlinePaymentAttempt.Status.EXPIRED)


class WebhookSecurityTests(OnlinePaymentTestBase):
    def setUp(self):
        super().setUp()
        self.as_resident()
        self.start()
        self.attempt = OnlinePaymentAttempt.objects.get()
        self.client.credentials()

    def test_a_valid_signature_is_accepted_and_settles(self):
        self.webhook(success_body(self.attempt))
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).status, Bill.Status.PAID)

    def test_invalid_missing_and_wrong_secret_signatures_are_rejected_and_nothing_is_stored(self):
        raw = success_body(self.attempt)
        bad = signed_headers(raw)
        bad["HTTP_X_WEBHOOK_SIGNATURE"] = base64.b64encode(b"x" * 32).decode()
        self.webhook(raw, bad, expect=400)
        self.webhook(raw, {}, expect=400)
        self.webhook(raw, signed_headers(raw, secret="another-secret"), expect=400)
        self.assertFalse(PropertyPaymentWebhookEvent.objects.exists())
        self.assertEqual(Payment.objects.count(), 0)

    def test_a_stale_timestamp_is_rejected(self):
        raw = success_body(self.attempt)
        old = int((time.time() - 7200) * 1000)
        self.webhook(raw, signed_headers(raw, timestamp=old), expect=400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_the_raw_body_is_what_is_verified(self):
        raw = success_body(self.attempt)
        headers = signed_headers(raw)
        # Same JSON meaning, re-serialized: the signature no longer matches.
        reserialized = json.dumps(json.loads(raw), indent=2).encode()
        self.webhook(reserialized, headers, expect=400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_a_duplicate_delivery_is_acknowledged_without_a_second_payment(self):
        raw = success_body(self.attempt)
        self.webhook(raw)
        resp = self.webhook(raw)
        self.assertEqual(resp.json()["status"], "duplicate")
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Receipt.objects.count(), 1)

    def test_unknown_orders_are_acknowledged_and_ignored(self):
        raw = success_body(self.attempt).replace(self.attempt.provider_order_id.encode(), b"TNRunknownorder000000000000000000000")
        self.webhook(raw)
        self.assertEqual(PropertyPaymentWebhookEvent.objects.get().outcome, "unknown_order")
        self.assertEqual(Payment.objects.count(), 0)


class SettlementTests(OnlinePaymentTestBase):
    def setUp(self):
        super().setUp()
        self.as_resident()
        self.start()
        self.attempt = OnlinePaymentAttempt.objects.get()

    def test_success_creates_one_payment_marks_paid_and_issues_one_receipt(self):
        self.webhook(success_body(self.attempt))
        self.bill.refresh_from_db()
        self.attempt.refresh_from_db()
        payment = Payment.objects.get()
        self.assertEqual((payment.method, payment.amount_cents, payment.recorded_by), ("ONLINE", 1_378_000, None))
        self.assertEqual(payment.reference, "cashfree:5114933189368")
        self.assertEqual(self.bill.status, Bill.Status.PAID)
        self.assertEqual(Receipt.objects.filter(payment=payment).count(), 1)
        self.assertEqual(self.attempt.status, OnlinePaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(self.attempt.payment_id, payment.id)

        status = self.client.get(f"/api/online-payments/{self.attempt.id}/").data
        self.assertEqual(status["display_state"], "succeeded")
        self.assertEqual(status["receipt_id"], str(payment.receipt.id))

    def test_amount_or_currency_mismatch_is_quarantined_not_applied(self):
        self.webhook(success_body(self.attempt, amount=100))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, OnlinePaymentAttempt.Status.UNAPPLIED)
        self.assertEqual(self.attempt.unapplied_reason, "AMOUNT_MISMATCH")
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).status, Bill.Status.PUBLISHED)

    def test_a_failed_payment_leaves_the_bill_unpaid_and_retryable(self):
        self.webhook(success_body(self.attempt, status="FAILED", kind="PAYMENT_FAILED_WEBHOOK", payment_id="1"))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, OnlinePaymentAttempt.Status.ACTIVE)
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).status, Bill.Status.PUBLISHED)
        self.assertEqual(self.client.get(f"/api/online-payments/{self.attempt.id}/").data["display_state"], "failed")
        # Retrying reuses the still-valid checkout.
        self.assertEqual(self.start().data["id"], str(self.attempt.id))

    def test_a_pending_payment_stays_processing(self):
        self.webhook(success_body(self.attempt, status="PENDING", kind="PAYMENT_SUCCESS_WEBHOOK", payment_id="2"))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, OnlinePaymentAttempt.Status.ACTIVE)
        self.assertEqual(Payment.objects.count(), 0)

    def test_offline_payment_first_then_capture_does_not_over_credit(self):
        self.s.pay(self.bill, 1_378_000)  # the owner records cash meanwhile
        self.webhook(success_body(self.attempt))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, OnlinePaymentAttempt.Status.UNAPPLIED)
        self.assertEqual(self.attempt.unapplied_reason, "BILL_ALREADY_SETTLED")
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).amount_paid_cents, 1_378_000)
        self.assertEqual(self.client.get(f"/api/online-payments/{self.attempt.id}/").data["display_state"], "already_paid")

    def test_the_return_page_reconciles_with_the_provider_when_the_webhook_is_late(self):
        before = self.client.get(f"/api/online-payments/{self.attempt.id}/").data
        self.assertEqual(before["display_state"], "processing")
        MockPropertyPaymentGateway.add_payment(self.attempt.provider_order_id)
        with mock.patch("apps.properties.online_payments.RECHECK_INTERVAL", timedelta(0)):
            after = self.client.get(f"/api/online-payments/{self.attempt.id}/").data
        self.assertEqual(after["display_state"], "succeeded")
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).status, Bill.Status.PAID)
        # And the webhook arriving afterwards changes nothing.
        payment = MockPropertyPaymentGateway.state.payments[self.attempt.provider_order_id][0]
        self.webhook(success_body(self.attempt, payment_id=payment.provider_payment_id))
        self.assertEqual(Payment.objects.count(), 1)

    def test_other_residents_cannot_read_the_status(self):
        other, _ = add_resident(self.s.tenant, self.s.owner, "priya@example.com", first_name="Priya")
        bearer(self.client, other, self.s.tenant)
        self.assertEqual(self.client.get(f"/api/online-payments/{self.attempt.id}/").status_code, 404)
        b = Scenario(slug="green-valley")
        bearer(self.client, b.owner, b.tenant)
        self.assertEqual(self.client.get(f"/api/online-payments/{self.attempt.id}/").status_code, 404)

    def test_online_payments_cannot_be_voided(self):
        self.webhook(success_body(self.attempt))
        bearer(self.client, self.s.owner, self.s.tenant)
        resp = self.client.post(f"/api/payments/{Payment.objects.get().id}/void/", {"reason": "oops"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "ONLINE_PAYMENT_NOT_VOIDABLE")


class ExpiryAndReconciliationTests(OnlinePaymentTestBase):
    def setUp(self):
        super().setUp()
        self.as_resident()
        self.start()
        self.attempt = OnlinePaymentAttempt.objects.get()

    def age(self, **delta):
        OnlinePaymentAttempt.objects.filter(pk=self.attempt.pk).update(
            created_at=timezone.now() - timedelta(**delta), expires_at=timezone.now() - timedelta(minutes=1), last_checked_at=None
        )

    def test_an_unpaid_attempt_past_expiry_is_expired_and_a_new_one_can_start(self):
        self.age(hours=1)
        counts = OnlinePaymentService.reconcile_open()
        self.assertEqual(counts["expired"], 1)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, OnlinePaymentAttempt.Status.EXPIRED)
        self.assertEqual(self.client.get(f"/api/online-payments/{self.attempt.id}/").data["display_state"], "expired")
        new = self.start().data
        self.assertNotEqual(new["id"], str(self.attempt.id))

    def test_the_sweep_settles_a_paid_order_whose_webhook_never_came(self):
        MockPropertyPaymentGateway.add_payment(self.attempt.provider_order_id)
        self.age(minutes=10)
        self.assertEqual(OnlinePaymentService.reconcile_open()["settled"], 1)
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).status, Bill.Status.PAID)
        self.assertEqual(OnlinePaymentService.reconcile_open()["checked"], 0)
        self.assertEqual(Payment.objects.count(), 1)

    def test_a_provider_outage_never_expires_or_settles(self):
        self.age(hours=1)
        MockPropertyPaymentGateway.state.fail_next = GatewayUnavailable("down")
        OnlinePaymentService.reconcile_open()
        self.assertEqual(OnlinePaymentAttempt.objects.get(pk=self.attempt.pk).status, OnlinePaymentAttempt.Status.ACTIVE)

    def test_a_late_capture_on_an_expired_attempt_still_applies_when_it_fits(self):
        self.age(hours=1)
        OnlinePaymentService.reconcile_open()
        self.webhook(success_body(self.attempt))
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).status, Bill.Status.PAID)
        self.assertEqual(Payment.objects.count(), 1)

    def test_the_scheduled_task_is_registered(self):
        import apps.properties.tasks  # noqa: F401 — registration happens on import, as autodiscovery does
        from config.celery import app

        self.assertIn("properties.reconcile_online_payments", app.tasks)
        result = apps.properties.tasks.reconcile_online_payments_task.delay().get()
        self.assertFalse(result["lock_skipped"])


class RefundTests(OnlinePaymentTestBase):
    def setUp(self):
        super().setUp()
        self.as_resident()
        self.start()
        self.attempt = OnlinePaymentAttempt.objects.get()

    def test_owner_refunds_an_unapplied_capture_once(self):
        self.s.pay(self.bill, 1_378_000)
        self.webhook(success_body(self.attempt))
        bearer(self.client, self.s.owner, self.s.tenant)
        listing = self.client.get("/api/online-payments/?status=UNAPPLIED").data
        self.assertEqual([r["id"] for r in listing["results"]], [str(self.attempt.id)])

        first = self.client.post(f"/api/online-payments/{self.attempt.id}/refund/")
        second = self.client.post(f"/api/online-payments/{self.attempt.id}/refund/")
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(second.data["status"], "REFUNDED")
        refunds = [c for n, c in MockPropertyPaymentGateway.state.calls if n == "refund_payment"]
        self.assertEqual(len(refunds), 1)
        self.assertEqual(refunds[0]["amount_cents"], 1_378_000)

    def test_a_settled_online_payment_is_not_refundable_here(self):
        self.webhook(success_body(self.attempt))
        bearer(self.client, self.s.owner, self.s.tenant)
        resp = self.client.post(f"/api/online-payments/{self.attempt.id}/refund/")
        self.assertEqual((resp.status_code, resp.data["code"]), (409, "REFUND_NOT_ALLOWED"))

    def test_residents_cannot_refund_or_list(self):
        self.assertEqual(self.client.post(f"/api/online-payments/{self.attempt.id}/refund/").status_code, 403)
        self.assertEqual(self.client.get("/api/online-payments/").status_code, 403)


@override_settings(**P9_SETTINGS)
class ConcurrentSettlementTests(TransactionTestCase):
    """Two finalizations for the same captured payment racing on separate
    connections — webhook vs. status query — settle the bill exactly once."""

    def setUp(self):
        MockPropertyPaymentGateway.reset()
        self.s = Scenario(slug="race")
        phone(self.s)
        self.bill = self.s.march_bill()
        self.attempt = OnlinePaymentService.start(user=self.s.user, tenant=self.s.tenant, bill=self.bill)

    def test_concurrent_finalization_settles_once(self):
        payment = MockPropertyPaymentGateway.add_payment(self.attempt.provider_order_id)
        outcomes = []
        barrier = threading.Barrier(4)

        def run():
            try:
                barrier.wait()
                outcomes.append(OnlinePaymentService.apply_payment(order_id=self.attempt.provider_order_id, payment=payment))
            finally:
                connection.close()

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(outcomes).count("settled"), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertEqual(Bill.objects.get(pk=self.bill.pk).amount_paid_cents, 1_378_000)

    def test_offline_payment_racing_the_capture_never_over_credits(self):
        payment = MockPropertyPaymentGateway.add_payment(self.attempt.provider_order_id)
        barrier = threading.Barrier(2)

        def offline():
            try:
                barrier.wait()
                try:
                    PaymentService.record(
                        actor=self.s.owner, tenant=self.s.tenant, bill=Bill.objects.get(pk=self.bill.pk),
                        amount_cents=1_378_000, payment_date=date(2026, 4, 5), method="CASH",
                    )
                except Exception:
                    pass
            finally:
                connection.close()

        def online():
            try:
                barrier.wait()
                OnlinePaymentService.apply_payment(order_id=self.attempt.provider_order_id, payment=payment)
            finally:
                connection.close()

        threads = [threading.Thread(target=offline), threading.Thread(target=online)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        bill = Bill.objects.get(pk=self.bill.pk)
        self.assertEqual(bill.amount_paid_cents, 1_378_000)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Receipt.objects.count(), 1)
        attempt = OnlinePaymentAttempt.objects.get(pk=self.attempt.pk)
        self.assertIn(attempt.status, (OnlinePaymentAttempt.Status.SUCCEEDED, OnlinePaymentAttempt.Status.UNAPPLIED))


class StatusMappingTests(OnlinePaymentTestBase):
    def test_provider_statuses_map_to_resident_states(self):
        from apps.properties.online_payments import display_state

        a = OnlinePaymentAttempt(status="ACTIVE", last_payment_status=ProviderPaymentStatus.USER_DROPPED)
        self.assertEqual(display_state(a), "failed")
        a.last_payment_status = ProviderPaymentStatus.PENDING
        self.assertEqual(display_state(a), "processing")
        self.assertEqual(display_state(OnlinePaymentAttempt(status="UNAPPLIED", unapplied_reason="AMOUNT_MISMATCH")), "needs_review")

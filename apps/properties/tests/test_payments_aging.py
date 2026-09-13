import threading
from datetime import date, timedelta
from unittest import mock

from django.db import connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APITestCase

from apps.properties import aging
from apps.properties.models import Bill, Payment, Receipt
from apps.properties.services import DomainError, PaymentService
from apps.properties.tests.factories import Scenario


class PaymentTests(TestCase):
    def test_full_payment_marks_paid_and_issues_receipt(self):
        s = Scenario()
        bill = s.march_bill()
        payment, created = s.pay(bill, 1_378_000)
        self.assertTrue(created)
        bill.refresh_from_db()
        self.assertEqual(bill.status, Bill.Status.PAID)
        self.assertEqual(bill.amount_due_cents, 0)
        receipt = payment.receipt
        self.assertRegex(receipt.receipt_number, r"^REC-\d{4}-000001$")
        self.assertEqual(receipt.amount_cents, 1_378_000)
        self.assertEqual(receipt.resident_name, bill.resident_name)

    def test_partial_then_final_payment(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 800_000)
        bill.refresh_from_db()
        self.assertEqual(bill.status, Bill.Status.PARTIALLY_PAID)
        self.assertEqual(bill.amount_due_cents, 578_000)
        s.pay(bill, 578_000)
        bill.refresh_from_db()
        self.assertEqual(bill.status, Bill.Status.PAID)
        numbers = list(Receipt.objects.filter(bill=bill).order_by("issued_at").values_list("receipt_number", flat=True))
        self.assertEqual(len(numbers), 2)
        self.assertEqual(len(set(numbers)), 2)
        self.assertTrue(numbers[1].endswith("000002"))

    def test_overpayment_is_refused(self):
        s = Scenario()
        bill = s.march_bill()
        with self.assertRaises(DomainError) as ctx:
            s.pay(bill, 1_378_001)
        self.assertEqual(ctx.exception.code, "OVERPAYMENT")

    def test_draft_bill_is_not_payable(self):
        s = Scenario()
        bill = s.march_bill(publish=False)
        with self.assertRaises(DomainError) as ctx:
            s.pay(bill, 100)
        self.assertEqual(ctx.exception.code, "BILL_NOT_PAYABLE")

    def test_idempotency_key_returns_original_payment(self):
        s = Scenario()
        bill = s.march_bill()
        first, created = s.pay(bill, 1000, idempotency_key="k-1")
        second, created_again = s.pay(bill, 1000, idempotency_key="k-1")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        bill.refresh_from_db()
        self.assertEqual(bill.amount_paid_cents, 1000)

    def test_idempotency_key_reuse_with_different_amount_conflicts(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 1000, idempotency_key="k-1")
        with self.assertRaises(DomainError) as ctx:
            s.pay(bill, 2000, idempotency_key="k-1")
        self.assertEqual(ctx.exception.code, "IDEMPOTENCY_KEY_REUSED")

    def test_duplicate_reference_is_refused(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 1000, reference="UTR123")
        with self.assertRaises(DomainError) as ctx:
            s.pay(bill, 1000, reference="UTR123")
        self.assertEqual(ctx.exception.code, "DUPLICATE_PAYMENT_REFERENCE")
        bill.refresh_from_db()
        self.assertEqual(bill.amount_paid_cents, 1000)

    def test_future_payment_date_refused(self):
        s = Scenario()
        bill = s.march_bill()
        with self.assertRaises(DomainError):
            s.pay(bill, 1000, payment_date=date.today() + timedelta(days=5))

    def test_void_reverses_bill_balance_and_keeps_receipt(self):
        s = Scenario()
        bill = s.march_bill()
        payment, _ = s.pay(bill, 1_378_000)
        PaymentService.void(actor=s.owner, payment=payment, reason="Bounced")
        bill.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.VOIDED)
        self.assertEqual(bill.status, Bill.Status.PUBLISHED)
        self.assertEqual(bill.amount_paid_cents, 0)
        self.assertTrue(Receipt.objects.filter(payment=payment).exists())


class ConcurrentPaymentTests(TransactionTestCase):
    def test_two_simultaneous_full_payments_credit_once(self):
        s = Scenario(slug="race")
        bill = s.march_bill()
        barrier = threading.Barrier(2)
        outcomes = []

        def attempt():
            try:
                barrier.wait()
                s.pay(Bill.objects.get(pk=bill.pk), 1_378_000)
                outcomes.append("ok")
            except DomainError as exc:
                outcomes.append(exc.code)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        bill.refresh_from_db()
        self.assertEqual(sorted(outcomes), ["BILL_NOT_PAYABLE", "ok"])
        self.assertEqual(bill.amount_paid_cents, 1_378_000)
        self.assertEqual(Payment.objects.filter(bill=bill).count(), 1)


class AgingTests(APITestCase):
    def test_buckets_and_overdue_days_are_deterministic(self):
        self.assertEqual(aging.bucket_for_days(0), "CURRENT")
        self.assertEqual(aging.bucket_for_days(1), "1_30")
        self.assertEqual(aging.bucket_for_days(30), "1_30")
        self.assertEqual(aging.bucket_for_days(31), "31_60")
        self.assertEqual(aging.bucket_for_days(61), "61_90")
        self.assertEqual(aging.bucket_for_days(91), "90_PLUS")

    def test_overdue_days_from_due_date(self):
        s = Scenario()
        bill = s.march_bill()  # due 2026-04-10
        self.assertEqual(bill.due_date, date(2026, 4, 10))
        self.assertEqual(aging.overdue_days(bill, date(2026, 4, 10)), 0)
        self.assertEqual(aging.overdue_days(bill, date(2026, 4, 22)), 12)
        self.assertEqual(aging.display_status(bill, date(2026, 4, 22)), "OVERDUE")
        s.pay(bill, 1_378_000)
        bill.refresh_from_db()
        self.assertEqual(aging.overdue_days(bill, date(2026, 6, 1)), 0)

    def test_aging_report_totals(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 378_000)
        report = aging.aging_report(Bill.objects.filter(pk=bill.pk), date(2026, 5, 17))  # 37 days
        self.assertEqual(report["total_outstanding_cents"], 1_000_000)
        self.assertEqual(report["total_overdue_cents"], 1_000_000)
        bucket = {b["key"]: b for b in report["buckets"]}
        self.assertEqual(bucket["31_60"]["amount_cents"], 1_000_000)
        self.assertEqual(report["rows"][0][1], 37)

    def test_aging_api_uses_server_date(self):
        from apps.properties.tests.factories import bearer

        s = Scenario()
        s.march_bill()
        bearer(self.client, s.owner, s.tenant)
        with mock.patch("apps.properties.aging.server_today", return_value=date(2026, 7, 15)):
            resp = self.client.get("/api/billing/aging/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["rows"][0]["overdue_days"], 96)
        self.assertEqual(resp.data["rows"][0]["bucket"], "90_PLUS")

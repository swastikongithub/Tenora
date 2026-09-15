"""The scheduled property billing reminder task: registered and scheduled,
idempotent across runs, lock-guarded, audited only when it notified someone."""

from datetime import date
from unittest import mock

from django.test import TransactionTestCase

from apps.billing.tasks import RETRY_POLICY as SUBSCRIPTION_RETRY_POLICY
from apps.billing.tests.test_scheduler import _lock_on_another_connection
from apps.notifications.models import Notification
from apps.platform.models import AuditEvent
from apps.properties import tasks
from apps.properties.tests.factories import Scenario
from config.celery import app as celery_app


class ReminderTaskTests(TransactionTestCase):
    def setUp(self):
        self.scenario = Scenario()
        self.bill = self.scenario.march_bill()  # due 2026-04-10

    def run_task(self, today):
        with mock.patch("apps.properties.aging.server_today", return_value=today):
            return tasks.send_billing_reminders_task.delay().get()

    def test_is_registered_and_scheduled_daily(self):
        self.assertIn("properties.send_billing_reminders", celery_app.tasks)
        entries = [c for c in celery_app.conf.beat_schedule.values() if c["task"] == "properties.send_billing_reminders"]
        self.assertEqual(len(entries), 1)

    def test_uses_the_same_bounded_retry_policy_as_the_subscription_sweeps(self):
        self.assertEqual(tasks.RETRY_POLICY, SUBSCRIPTION_RETRY_POLICY)
        self.assertEqual(tasks.send_billing_reminders_task.max_retries, SUBSCRIPTION_RETRY_POLICY["max_retries"])

    def test_a_second_run_notifies_nobody_twice(self):
        first = self.run_task(date(2026, 4, 20))
        self.assertFalse(first["lock_skipped"])
        self.assertEqual(first["overdue"], 1)
        count = Notification.objects.filter(recipient=self.scenario.user).count()
        self.assertGreater(count, 0)

        second = self.run_task(date(2026, 4, 20))
        self.assertEqual(second["overdue"], 0)
        self.assertEqual(Notification.objects.filter(recipient=self.scenario.user).count(), count)

    def test_skips_while_another_process_holds_the_lock(self):
        with _lock_on_another_connection(tasks.LOCK_NAME) as held:
            self.assertTrue(held)
            result = self.run_task(date(2026, 4, 20))
        self.assertTrue(result["lock_skipped"])
        self.assertFalse(Notification.objects.filter(recipient=self.scenario.user, kind__icontains="overdue").exists())

    def test_audits_only_a_run_that_notified_someone(self):
        self.run_task(date(2026, 4, 20))
        self.assertEqual(AuditEvent.objects.filter(action="scheduled.billing_reminders").count(), 1)
        event = AuditEvent.objects.get(action="scheduled.billing_reminders")
        self.assertFalse(event.is_critical)
        self.assertIsNone(event.actor)

        self.run_task(date(2026, 4, 20))  # nothing new to send
        self.assertEqual(AuditEvent.objects.filter(action="scheduled.billing_reminders").count(), 1)

    def test_changes_no_billing_state(self):
        before = (self.bill.status, self.bill.total_cents, self.bill.amount_paid_cents)
        self.run_task(date(2026, 6, 30))
        self.bill.refresh_from_db()
        self.assertEqual((self.bill.status, self.bill.total_cents, self.bill.amount_paid_cents), before)

"""
Stage D7 — the two scheduled Celery tasks (docs/stage-d7-spec.md §9).

Under `manage.py test`, `CELERY_TASK_ALWAYS_EAGER` is on, so the tasks execute
in-process — no Redis. Each task is a thin caller of the SAME service method the
matching management command calls; these tests prove the task drives that real
service path and produces the same observable effect.
"""

from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.billing.gateway.base import EventType
from apps.billing.models import (
    ReconciliationDiscrepancy,
    Subscription,
    UsageRecord,
    WebhookEvent,
)
from apps.billing.services import WebhookProcessingService
from apps.billing.tasks import meter_usage as meter_usage_task
from apps.billing.tasks import process_webhook_events as sweep_task
from apps.billing.tasks import reconcile_subscriptions as reconcile_task
from apps.billing.tests.test_reconciliation import ReconciliationTestBase
from apps.billing.tests.test_usage_metering import UsageMeteringTestBase
from apps.billing.tests.test_webhook_processing import ProcessingTestBase, _event


class EagerModeTests(TestCase):
    def test_the_suite_runs_tasks_in_process_with_no_broker(self):
        self.assertIs(settings.CELERY_TASK_ALWAYS_EAGER, True)


class ProcessWebhookEventsTaskTests(ProcessingTestBase):
    def test_task_drives_the_real_sweep(self):
        self._checkout()
        _event(EventType.ACTIVATED)

        # .delay() proves the eager path; .get() returns the task's result.
        result = sweep_task.delay().get()

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["processed"], 1)
        self.assertTrue(WebhookEvent.objects.get().processed)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_task_defers_an_unmatched_charged_then_a_later_run_recovers_it(self):
        start = timezone.now()
        charged = _event(
            EventType.CHARGED,
            event_id="chg",
            period_start=start,
            period_end=start + timedelta(days=30),
        )

        r1 = sweep_task()
        self.assertEqual(r1["deferred"], 1)
        charged.refresh_from_db()
        self.assertFalse(charged.processed)

        # ACTIVATED lands and creates the subscription.
        self._checkout()
        WebhookProcessingService.process_event(
            _event(EventType.ACTIVATED, event_id="act")
        )

        r2 = sweep_task()
        self.assertEqual(r2["processed"], 1)
        charged.refresh_from_db()
        self.assertTrue(charged.processed)
        sub = Subscription.objects.get()
        self.assertEqual(sub.current_period_start, start)

    def test_task_tolerates_a_row_that_raises(self):
        self._checkout()
        _event(EventType.ACTIVATED, event_id="ok")
        _event(
            EventType.CHARGED, event_id="boom", external_subscription_id="other"
        )

        real = WebhookProcessingService.process_event

        def flaky(event):
            if event.external_event_id == "boom":
                raise RuntimeError("kaboom")
            return real(event)

        with mock.patch.object(
            WebhookProcessingService, "process_event", side_effect=flaky
        ):
            result = sweep_task()

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_nothing_pending_is_a_clean_zero_result(self):
        result = sweep_task()
        # `lock_skipped` joined every task result in Phase 6 (the overlap
        # guard — docs/worker-scheduler-operations.md §3). The count keys are
        # unchanged; this run took the lock, so the flag is False.
        self.assertEqual(
            result,
            {
                "lock_skipped": False,
                "total": 0,
                "processed": 0,
                "deferred": 0,
                "failed": 0,
            },
        )


class MeterUsageTaskTests(UsageMeteringTestBase):
    def test_task_snapshots_every_subscribed_tenant(self):
        self._tenant("acme", members=3)  # OWNER + 3 = 4
        self._tenant("nosub", subscription=False)

        result = meter_usage_task.delay().get()

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["created"], 1)
        self.assertEqual(UsageRecord.objects.count(), 1)
        self.assertEqual(UsageRecord.objects.get().quantity, 4)

    def test_a_second_run_records_nothing_new(self):
        self._tenant("acme", members=1)

        meter_usage_task()
        result = meter_usage_task()

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["existing"], 1)
        self.assertEqual(UsageRecord.objects.count(), 1)

    def test_task_and_command_produce_the_same_effect(self):
        from io import StringIO

        from django.core.management import call_command

        self._tenant("acme", members=2)

        meter_usage_task()
        out = StringIO()
        call_command("meter_usage", stdout=out)

        # The command re-run finds the snapshot already recorded — one row total.
        self.assertEqual(UsageRecord.objects.count(), 1)
        self.assertIn("0 new", out.getvalue())


class ReconcileSubscriptionsTaskTests(ReconciliationTestBase):
    def test_task_drives_the_real_sweep_and_records_drift(self):
        self._sub("acme", status=Subscription.Status.ACTIVE, external_id="sub_acme")
        self._gateway(
            {"sub_acme": {"status": "CANCELED", "raw_status": "cancelled"}}
        )

        result = reconcile_task.delay().get()

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["discrepancies"], 1)
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 1)

    def test_task_and_command_share_the_service_method(self):
        from io import StringIO

        from django.core.management import call_command

        self._sub("acme", status=Subscription.Status.ACTIVE, external_id="sub_acme")
        self._gateway(
            {"sub_acme": {"status": "CANCELED", "raw_status": "cancelled"}}
        )

        reconcile_task()
        out = StringIO()
        call_command("reconcile_subscriptions", stdout=out)

        # Immutable append: the task's row plus the command's row.
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 2)
        self.assertIn("1 discrepancies", out.getvalue())

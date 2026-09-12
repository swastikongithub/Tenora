"""
Phase 6 — the worker/scheduler architecture around the three scheduled sweeps
(master plan §6, docs/worker-scheduler-operations.md).

What D7 shipped — the tasks themselves, and their being thin callers of the
same service methods the management commands call — is covered by
apps/billing/tests/test_tasks.py and is not re-tested here. This module covers
what Phase 6 added AROUND that call:

  - task registration and the beat schedule (§6.8 "task registration/discovery",
    "correct schedule configuration")
  - idempotency under repeat and duplicate execution (§6.3)
  - the cross-process advisory lock (§6.4)
  - observability that does not flood the audit log (§6.5)
  - retry and failure handling (§6.7)
  - the manual fallback path still being valid (§6.6)

The advisory-lock tests use a SECOND database connection to genuinely hold the
lock from elsewhere. A same-connection test would prove nothing: Postgres
advisory locks are re-entrant within one session, so `pg_try_advisory_lock`
called twice on one connection succeeds twice. Holding it on another connection
is the only way to exercise the case the lock exists for.
"""

import threading
from unittest import mock

from celery.exceptions import Retry
from celery.schedules import crontab
from django.db import connection, connections
from django.db.backends.postgresql.base import DatabaseWrapper
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from apps.billing.locks import LOCK_NAMESPACE, advisory_lock, lock_key
from apps.billing.models import UsageRecord, WebhookEvent
from apps.billing.gateway.base import EventType
from apps.billing.tasks import meter_usage as meter_usage_task
from apps.billing.tasks import process_webhook_events as sweep_task
from apps.billing.tasks import RETRY_POLICY
from apps.billing.tasks import reconcile_subscriptions as reconcile_task
from apps.billing.tests.test_reconciliation import ReconciliationTestBase
from apps.billing.tests.test_usage_metering import UsageMeteringTestBase
from apps.billing.tests.test_webhook_processing import ProcessingTestBase, _event
from apps.billing.models import Subscription
from apps.platform.models import AuditEvent
from config.celery import app as celery_app


class TaskRegistrationTests(SimpleTestCase):
    """The tasks must actually be discoverable by the worker, and the beat
    schedule must name tasks that exist. A schedule entry pointing at a
    misspelled task name fails silently at runtime — never in a unit test that
    imports the function directly."""

    EXPECTED = {
        "billing.process_webhook_events",
        "billing.meter_usage",
        "billing.reconcile_subscriptions",
    }

    def test_every_task_is_registered_with_the_celery_app(self):
        for name in self.EXPECTED:
            with self.subTest(task=name):
                self.assertIn(name, celery_app.tasks)

    def test_every_beat_entry_points_at_a_registered_task(self):
        for entry, config in celery_app.conf.beat_schedule.items():
            with self.subTest(entry=entry):
                self.assertIn(config["task"], celery_app.tasks)

    def test_all_three_sweeps_are_actually_scheduled(self):
        scheduled = {c["task"] for c in celery_app.conf.beat_schedule.values()}
        self.assertEqual(scheduled, self.EXPECTED)

    def test_the_cadences_are_the_documented_ones(self):
        by_task = {
            c["task"]: c["schedule"]
            for c in celery_app.conf.beat_schedule.values()
        }
        self.assertEqual(
            by_task["billing.process_webhook_events"], crontab(minute="*/5")
        )
        self.assertEqual(
            by_task["billing.reconcile_subscriptions"], crontab(minute=0)
        )
        self.assertEqual(
            by_task["billing.meter_usage"], crontab(hour=3, minute=0)
        )

    def test_every_task_retries_a_bounded_number_of_times(self):
        for name in self.EXPECTED:
            with self.subTest(task=name):
                task = celery_app.tasks[name]
                self.assertIsNotNone(task.max_retries)
                self.assertGreater(task.max_retries, 0)
                self.assertLessEqual(task.max_retries, 5)


class AdvisoryLockTests(TransactionTestCase):
    """The lock primitive itself — apps/billing/locks.py."""

    def test_a_free_lock_is_acquired(self):
        with advisory_lock("test.free") as acquired:
            self.assertTrue(acquired)

    def test_the_lock_is_released_on_exit(self):
        with advisory_lock("test.release") as first:
            self.assertTrue(first)
        # A second connection can take it now, which it could not before.
        self.assertTrue(self._held_elsewhere_is_free("test.release"))

    def test_the_lock_is_released_even_when_the_body_raises(self):
        with self.assertRaises(RuntimeError):
            with advisory_lock("test.raise") as acquired:
                self.assertTrue(acquired)
                raise RuntimeError("boom")
        self.assertTrue(self._held_elsewhere_is_free("test.raise"))

    def test_a_lock_held_by_another_connection_is_not_acquired(self):
        with _lock_on_another_connection("test.busy"):
            with advisory_lock("test.busy") as acquired:
                self.assertFalse(acquired)

    def test_different_names_do_not_block_each_other(self):
        with _lock_on_another_connection("test.a"):
            with advisory_lock("test.b") as acquired:
                self.assertTrue(acquired)

    def test_the_key_is_stable_across_calls(self):
        self.assertEqual(lock_key("billing.meter_usage"), lock_key("billing.meter_usage"))
        self.assertNotEqual(lock_key("a"), lock_key("b"))

    def test_the_key_fits_postgres_int4(self):
        for name in ("billing.meter_usage", "x", "a" * 500):
            with self.subTest(name=name):
                self.assertGreaterEqual(lock_key(name), -(2**31))
                self.assertLess(lock_key(name), 2**31)

    def _held_elsewhere_is_free(self, name):
        with _lock_on_another_connection(name) as got:
            return got


class _LockHolder:
    """
    Holds an advisory lock on a genuinely separate database connection, so the
    lock is contended the way it would be between two worker processes.

    A second connection is the only way to test this: Postgres advisory locks
    are re-entrant within one session, so taking the same lock twice on the
    default connection would succeed twice and prove nothing.

    Builds its own DatabaseWrapper from the default connection's settings
    rather than registering an alias on the connection handler — the settings
    dict already points at the TEST database during a test run, and this leaves
    no global state to unwind.
    """

    def __init__(self, name):
        self.name = name
        self.conn = None
        self.acquired = False

    def __enter__(self):
        self.conn = DatabaseWrapper(
            connection.settings_dict.copy(), alias="lock_holder"
        )
        with self.conn.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                [LOCK_NAMESPACE, lock_key(self.name)],
            )
            self.acquired = bool(cursor.fetchone()[0])
        return self.acquired

    def __exit__(self, *exc):
        # Closing the connection releases every advisory lock it held — which
        # is exactly the property that keeps a killed worker from wedging a job.
        self.conn.close()
        return False


def _lock_on_another_connection(name):
    return _LockHolder(name)


class SweepLockingTests(ProcessingTestBase):
    """A scheduled sweep must not run while another holds its lock."""

    def test_the_webhook_sweep_skips_when_its_lock_is_held(self):
        self._checkout()
        _event(EventType.ACTIVATED)

        with _lock_on_another_connection("billing.process_webhook_events"):
            result = sweep_task()

        self.assertTrue(result["lock_skipped"])
        self.assertEqual(result["total"], 0)
        # Untouched — the point is that the work did not run, not that it ran
        # and was discarded.
        self.assertFalse(WebhookEvent.objects.get().processed)
        self.assertEqual(Subscription.objects.count(), 0)

    def test_the_sweep_runs_normally_once_the_lock_is_free(self):
        self._checkout()
        _event(EventType.ACTIVATED)

        with _lock_on_another_connection("billing.process_webhook_events"):
            self.assertTrue(sweep_task()["lock_skipped"])

        result = sweep_task()
        self.assertFalse(result["lock_skipped"])
        self.assertEqual(result["processed"], 1)
        self.assertTrue(WebhookEvent.objects.get().processed)

    def test_a_skipped_run_is_not_an_error_and_records_nothing(self):
        self._checkout()
        _event(EventType.ACTIVATED)
        with _lock_on_another_connection("billing.process_webhook_events"):
            sweep_task()
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_each_sweep_has_its_own_lock(self):
        # Holding the usage lock must not stop the webhook sweep: they touch
        # different work and share no backlog.
        self._checkout()
        _event(EventType.ACTIVATED)
        with _lock_on_another_connection("billing.meter_usage"):
            result = sweep_task()
        self.assertFalse(result["lock_skipped"])
        self.assertEqual(result["processed"], 1)


class ConcurrentSweepTests(TransactionTestCase):
    """
    Two workers firing the same sweep at the same instant. TransactionTestCase
    (not TestCase) because the threads need genuinely committed rows to see —
    inside a test transaction they would each see an empty backlog and the test
    would pass for the wrong reason.
    """

    def setUp(self):
        from apps.billing.models import Plan, SubscriptionCheckout
        from apps.tenants.models import Tenant

        self.plan = Plan.objects.create(
            name="Pro",
            code="PRO",
            price_cents=2900,
            currency="USD",
            external_plan_id="plan_PRO",
        )
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        SubscriptionCheckout.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            external_subscription_id="sub_ext_1",
            status=SubscriptionCheckout.Status.CONFIRMED,
        )
        WebhookEvent.objects.create(
            external_event_id="evt_1",
            external_subscription_id="sub_ext_1",
            event_type=EventType.ACTIVATED,
            raw_payload={},
            event_created_at=timezone.now(),
        )

    def tearDown(self):
        connections.close_all()

    def test_two_concurrent_sweeps_do_not_both_process_the_backlog(self):
        barrier = threading.Barrier(2, timeout=10)
        results = []

        def run():
            try:
                barrier.wait()
                results.append(sweep_task())
            except threading.BrokenBarrierError:
                pass
            finally:
                connections.close_all()

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        # Whichever ordering the threads take, the backlog is applied exactly
        # once: either one run skipped on the lock, or the second found nothing
        # left to do. The subscription count is the real assertion — the
        # unique external_subscription_id would reject a duplicate anyway,
        # which is the belt to the lock's braces.
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(r["processed"] for r in results), 1)
        self.assertEqual(Subscription.objects.count(), 1)


class SweepIdempotencyTests(UsageMeteringTestBase):
    """§6.3 — safe when executed twice, retried, or run after a previous
    success. These assert the guarantee at the TASK level; the underlying
    constraints are covered by each stage's own suite."""

    def test_a_repeated_usage_run_creates_no_second_snapshot(self):
        self._tenant("acme", members=2)

        first = meter_usage_task()
        second = meter_usage_task()
        third = meter_usage_task()

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(third["created"], 0)
        self.assertEqual(UsageRecord.objects.count(), 1)

    def test_a_usage_run_after_a_previous_success_is_a_clean_no_op(self):
        self._tenant("acme", members=1)
        meter_usage_task()
        result = meter_usage_task()
        self.assertEqual(result["existing"], 1)
        self.assertEqual(result["created"], 0)


class WebhookSweepIdempotencyTests(ProcessingTestBase):
    def test_a_repeated_webhook_sweep_applies_nothing_twice(self):
        self._checkout()
        _event(EventType.ACTIVATED)

        sweep_task()
        second = sweep_task()

        self.assertEqual(second["total"], 0)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_a_partially_completed_sweep_leaves_the_rest_pending(self):
        # One row raises; the sweep still commits the row it handled and
        # reports the failure rather than losing it.
        self._checkout()
        _event(EventType.ACTIVATED, event_id="ok")
        _event(EventType.CHARGED, event_id="boom", external_subscription_id="other")

        from apps.billing.services import WebhookProcessingService

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
        self.assertTrue(WebhookEvent.objects.get(external_event_id="ok").processed)
        self.assertFalse(WebhookEvent.objects.get(external_event_id="boom").processed)


class SchedulerObservabilityTests(ProcessingTestBase):
    """§6.5 — record what an operator needs, and nothing else. A five-minute
    sweep runs 288 times a day; a row per idle run would bury the rows that
    matter."""

    def test_a_run_that_changed_nothing_writes_no_audit_row(self):
        result = sweep_task()
        self.assertEqual(result["total"], 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_a_run_that_processed_something_writes_one_observational_row(self):
        self._checkout()
        _event(EventType.ACTIVATED)

        sweep_task()

        self.assertEqual(AuditEvent.objects.count(), 1)
        event = AuditEvent.objects.get()
        self.assertFalse(event.is_critical)
        self.assertEqual(event.action, "scheduled.webhook_sweep")
        self.assertEqual(event.target_type, "ScheduledTask")
        self.assertEqual(event.metadata["processed"], 1)

    def test_a_scheduled_run_has_no_actor(self):
        # The FK is nullable precisely so a machine-driven action needs no
        # synthetic user account in the audit trail.
        self._checkout()
        _event(EventType.ACTIVATED)
        sweep_task()
        self.assertIsNone(AuditEvent.objects.get().actor)

    def test_a_run_with_only_deferrals_writes_nothing(self):
        # A deferred event is the steady state for one still waiting on its
        # subscription — not something an operator needs told every 5 minutes.
        _event(EventType.CHARGED, event_id="chg", external_subscription_id="nope")
        result = sweep_task()
        self.assertEqual(result["deferred"], 1)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_a_run_with_a_failure_is_recorded(self):
        self._checkout()
        _event(EventType.ACTIVATED, event_id="ok")
        _event(EventType.CHARGED, event_id="boom", external_subscription_id="other")

        from apps.billing.services import WebhookProcessingService

        real = WebhookProcessingService.process_event

        def flaky(event):
            if event.external_event_id == "boom":
                raise RuntimeError("kaboom")
            return real(event)

        with mock.patch.object(
            WebhookProcessingService, "process_event", side_effect=flaky
        ):
            sweep_task()

        event = AuditEvent.objects.get()
        self.assertEqual(event.metadata["failed"], 1)

    def test_audit_metadata_carries_counts_only_never_a_payload_or_secret(self):
        self._checkout()
        _event(EventType.ACTIVATED)
        sweep_task()

        event = AuditEvent.objects.get()
        self.assertTrue(all(isinstance(v, int) for v in event.metadata.values()))
        forbidden = {"password", "secret", "token", "raw_payload", "email"}
        self.assertFalse(forbidden & set(event.metadata.keys()))

    def test_an_audit_failure_never_breaks_the_sweep(self):
        # Observational by contract: the sweep's real effects are already
        # durably recorded, so a failed audit write must not undo them.
        self._checkout()
        _event(EventType.ACTIVATED)

        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("audit down"),
        ):
            result = sweep_task()

        self.assertEqual(result["processed"], 1)
        self.assertTrue(WebhookEvent.objects.get().processed)
        self.assertEqual(Subscription.objects.count(), 1)


class ReconciliationObservabilityTests(ReconciliationTestBase):
    def test_a_clean_sweep_writes_nothing(self):
        self._sub("acme", status=Subscription.Status.ACTIVE, external_id="sub_acme")
        self._gateway({"sub_acme": {"status": "ACTIVE", "raw_status": "active"}})

        result = reconcile_task()

        self.assertEqual(result["discrepancies"], 0)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_drift_is_recorded_for_an_operator(self):
        self._sub("acme", status=Subscription.Status.ACTIVE, external_id="sub_acme")
        self._gateway({"sub_acme": {"status": "CANCELED", "raw_status": "cancelled"}})

        reconcile_task()

        event = AuditEvent.objects.get()
        self.assertEqual(event.action, "scheduled.reconciliation_sweep")
        self.assertFalse(event.is_critical)
        self.assertEqual(event.metadata["discrepancies"], 1)


class SchedulerFailureHandlingTests(ProcessingTestBase):
    """§6.7 — an infrastructure failure retries and then surfaces; it never
    disappears quietly."""

    def test_an_infrastructure_failure_asks_to_be_retried(self):
        """
        Dispatched the way beat dispatches it, a raising task schedules a
        retry rather than dying — Celery signals that by raising `Retry`,
        carrying the original exception. Without the autoretry policy the bare
        RuntimeError would come straight out, so this asserts the policy is
        actually wired to these tasks, not merely declared.

        The backoff itself is not exercised here: under
        CELERY_TASK_ALWAYS_EAGER there is no broker to schedule the next
        attempt on, so asserting a retry COUNT would be asserting the test
        harness, not the deployed behaviour.
        """
        with mock.patch(
            "apps.billing.services.WebhookProcessingService.process_pending",
            side_effect=RuntimeError("database is gone"),
        ):
            with self.assertRaises(Retry) as caught:
                sweep_task.delay().get()

        self.assertIsInstance(caught.exception.exc, RuntimeError)
        self.assertIn("database is gone", str(caught.exception.exc))

    def test_every_scheduled_task_carries_the_same_retry_policy(self):
        for task in (sweep_task, meter_usage_task, reconcile_task):
            with self.subTest(task=task.name):
                self.assertEqual(task.max_retries, RETRY_POLICY["max_retries"])
                self.assertIn(Exception, task.autoretry_for)

    def test_a_direct_call_surfaces_the_failure_immediately(self):
        # The management-command / manual path: an operator running this by
        # hand wants the error now, not three backed-off attempts later.
        with mock.patch(
            "apps.billing.services.WebhookProcessingService.process_pending",
            side_effect=RuntimeError("database is gone"),
        ):
            with self.assertRaises(RuntimeError):
                sweep_task()

    def test_a_failing_task_releases_its_lock(self):
        with mock.patch(
            "apps.billing.services.WebhookProcessingService.process_pending",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                sweep_task()

        # If the lock leaked, this would report skipped instead of running.
        self.assertFalse(sweep_task()["lock_skipped"])

    def test_a_per_row_failure_does_not_trigger_a_whole_sweep_retry(self):
        # A bad row is data, not infrastructure: it is reported on the result
        # and the sweep completes. Retrying the whole sweep for it would
        # reprocess every good row for nothing.
        self._checkout()
        _event(EventType.ACTIVATED, event_id="ok")
        _event(EventType.CHARGED, event_id="boom", external_subscription_id="other")

        from apps.billing.services import WebhookProcessingService

        real = WebhookProcessingService.process_event
        calls = {"sweeps": 0}

        def flaky(event):
            if event.external_event_id == "boom":
                raise RuntimeError("kaboom")
            return real(event)

        real_pending = WebhookProcessingService.process_pending

        def counting_pending():
            calls["sweeps"] += 1
            return real_pending()

        with mock.patch.object(
            WebhookProcessingService, "process_event", side_effect=flaky
        ):
            with mock.patch.object(
                WebhookProcessingService,
                "process_pending",
                side_effect=counting_pending,
            ):
                result = sweep_task()

        self.assertEqual(calls["sweeps"], 1)
        self.assertEqual(result["failed"], 1)


class ManualFallbackStillWorksTests(ProcessingTestBase):
    """§6.6 — the manual controls stay valid alongside the scheduled path, and
    a manual run cannot collide with a scheduled one."""

    def test_the_management_command_still_drives_the_same_service(self):
        from io import StringIO

        from django.core.management import call_command

        self._checkout()
        _event(EventType.ACTIVATED)

        out = StringIO()
        call_command("process_webhook_events", stdout=out)

        self.assertTrue(WebhookEvent.objects.get().processed)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_a_scheduled_run_cannot_collide_with_a_manual_one(self):
        # The management command path is unlocked by design (an operator asking
        # for a run should get one), so the guard that matters is the other
        # direction: a scheduled run yields while the manual one holds the lock.
        self._checkout()
        _event(EventType.ACTIVATED)

        with _lock_on_another_connection("billing.process_webhook_events"):
            self.assertTrue(sweep_task()["lock_skipped"])

        # And the work is still there to do afterwards.
        self.assertFalse(WebhookEvent.objects.get().processed)

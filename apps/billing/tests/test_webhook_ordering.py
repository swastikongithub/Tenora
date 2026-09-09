"""
Stage D4 — out-of-order webhook event handling (docs/stage-d4-spec.md §9).

Deliberately-constructed out-of-order sequences, processed through
`WebhookProcessingService`. No live provider, no HTTP.

Three mechanisms under test:
  - CHARGED period monotonicity (reuses period_start/period_end).
  - The cross-event-type staleness guard (event_created_at + Subscription.last_event_at).
  - Bounded retry for an unmatched CHARGED (DEFERRED until an age cutoff).
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from apps.billing.gateway.base import EventType
from apps.billing.models import Subscription, WebhookEvent
from apps.billing.services import (
    PERIOD_LENGTH,
    UNMATCHED_CHARGED_RETRY_WINDOW,
    WebhookProcessingService,
)

from apps.billing.tests.test_webhook_processing import ProcessingTestBase, SUB_ID

T0 = datetime(2027, 1, 1, tzinfo=dt_timezone.utc)


def _evt(
    event_type,
    *,
    event_id,
    external_subscription_id=SUB_ID,
    period_start=None,
    period_end=None,
    event_created_at=None,
    received_at=None,
):
    evt = WebhookEvent.objects.create(
        external_event_id=event_id,
        external_subscription_id=external_subscription_id,
        event_type=event_type.value,
        raw_payload={"synthetic": True, "type": event_type.value},
        period_start=period_start,
        period_end=period_end,
        event_created_at=event_created_at,
    )
    if received_at is not None:
        WebhookEvent.objects.filter(pk=evt.pk).update(received_at=received_at)
        evt.refresh_from_db()
    return evt


class ChargedPeriodMonotonicityTests(ProcessingTestBase):
    def test_older_period_charged_processed_last_is_a_noop(self):
        # Subscription created by ACTIVATED with a synthesized default period.
        sub = self._subscription(status=Subscription.Status.ACTIVE)

        p1_start, p1_end = T0, T0 + timedelta(days=30)
        p2_start, p2_end = p1_end, p1_end + timedelta(days=30)

        # The NEWER period lands first...
        WebhookProcessingService.process_event(
            _evt(EventType.CHARGED, event_id="chg_new",
                 period_start=p2_start, period_end=p2_end)
        )
        sub.refresh_from_db()
        self.assertEqual(sub.current_period_start, p2_start)
        self.assertEqual(sub.current_period_end, p2_end)

        # ...then the OLDER period is redelivered and processed.
        outcome = WebhookProcessingService.process_event(
            _evt(EventType.CHARGED, event_id="chg_old",
                 period_start=p1_start, period_end=p1_end)
        )

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        sub.refresh_from_db()
        # The newer period still stands — nothing moved backward.
        self.assertEqual(sub.current_period_start, p2_start)
        self.assertEqual(sub.current_period_end, p2_end)

    def test_first_real_charged_after_activated_is_never_rejected(self):
        # Regression guard for the deviation from the spec's literal rule: the
        # first real CHARGED's provider period starts ≈ the subscription's
        # synthesized default_period start, which must NOT read as "stale".
        now = timezone.now().replace(microsecond=0)
        sub = self._subscription(
            status=Subscription.Status.ACTIVE, period=(now, now + timedelta(days=30))
        )
        real_start = now - timedelta(seconds=5)  # provider clock a hair earlier
        real_end = real_start + timedelta(days=28)  # a short billing month

        WebhookProcessingService.process_event(
            _evt(EventType.CHARGED, event_id="chg_first",
                 period_start=real_start, period_end=real_end)
        )

        sub.refresh_from_db()
        self.assertEqual(sub.current_period_start, real_start)
        self.assertEqual(sub.current_period_end, real_end)


class CrossTypeStalenessTests(ProcessingTestBase):
    def test_stale_payment_trouble_after_newer_charged_is_a_noop(self):
        sub = self._subscription(status=Subscription.Status.ACTIVE)

        # A CHARGED at t0+100 advances the high-water mark.
        WebhookProcessingService.process_event(
            _evt(EventType.CHARGED, event_id="chg_1",
                 period_start=T0, period_end=T0 + timedelta(days=30),
                 event_created_at=T0 + timedelta(seconds=100))
        )
        sub.refresh_from_db()
        self.assertEqual(sub.last_event_at, T0 + timedelta(seconds=100))

        # A PAYMENT_TROUBLE the provider generated BEFORE that charge, delivered
        # late — must not flip the recovered subscription back to PAST_DUE.
        outcome = WebhookProcessingService.process_event(
            _evt(EventType.PAYMENT_TROUBLE, event_id="pt_stale",
                 event_created_at=T0 + timedelta(seconds=90))
        )

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)

    def test_newer_payment_trouble_applies_and_advances_the_mark(self):
        sub = self._subscription(status=Subscription.Status.ACTIVE)
        WebhookProcessingService.process_event(
            _evt(EventType.CHARGED, event_id="chg_1",
                 period_start=T0, period_end=T0 + timedelta(days=30),
                 event_created_at=T0 + timedelta(seconds=100))
        )

        outcome = WebhookProcessingService.process_event(
            _evt(EventType.PAYMENT_TROUBLE, event_id="pt_new",
                 event_created_at=T0 + timedelta(seconds=200))
        )

        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)
        self.assertEqual(sub.last_event_at, T0 + timedelta(seconds=200))

    def test_cancelled_is_exempt_from_the_staleness_guard(self):
        sub = self._subscription(status=Subscription.Status.ACTIVE)
        Subscription.objects.filter(pk=sub.pk).update(
            last_event_at=T0 + timedelta(seconds=500)
        )

        outcome = WebhookProcessingService.process_event(
            _evt(EventType.CANCELLED, event_id="cxl_old",
                 event_created_at=T0 + timedelta(seconds=100))
        )

        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.CANCELED)

    def test_event_without_a_timestamp_bypasses_the_guard(self):
        # D3 behaviour preserved: no event_created_at → guard never fires.
        sub = self._subscription(status=Subscription.Status.ACTIVE)
        Subscription.objects.filter(pk=sub.pk).update(
            last_event_at=T0 + timedelta(seconds=500)
        )

        outcome = WebhookProcessingService.process_event(
            _evt(EventType.PAYMENT_TROUBLE, event_id="pt_no_ts")
        )

        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Subscription.Status.PAST_DUE)
        # Mark not advanced (the event carried no timestamp).
        self.assertEqual(sub.last_event_at, T0 + timedelta(seconds=500))

    def test_creating_activated_leaves_the_mark_unset(self):
        self._checkout()

        WebhookProcessingService.process_event(
            _evt(EventType.ACTIVATED, event_id="act_1",
                 event_created_at=T0 + timedelta(seconds=10))
        )

        sub = Subscription.objects.get()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertIsNone(sub.last_event_at)


class UnmatchedChargedRetryTests(ProcessingTestBase):
    def test_deferred_then_recovered_once_activated_creates_the_subscription(self):
        real_start = T0
        real_end = T0 + timedelta(days=31)

        # CHARGED arrives first — no Subscription, no Checkout yet.
        charged = _evt(EventType.CHARGED, event_id="chg_early",
                       period_start=real_start, period_end=real_end,
                       event_created_at=T0 + timedelta(seconds=5))
        self.assertEqual(
            WebhookProcessingService.process_event(charged),
            WebhookProcessingService.DEFERRED,
        )
        charged.refresh_from_db()
        self.assertFalse(charged.processed)

        # ACTIVATED lands, creating the Subscription.
        self._checkout()
        WebhookProcessingService.process_event(
            _evt(EventType.ACTIVATED, event_id="act_late",
                 event_created_at=T0)
        )

        # Retry the deferred CHARGED — its real period data is recovered.
        outcome = WebhookProcessingService.process_event(charged)
        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        charged.refresh_from_db()
        self.assertTrue(charged.processed)
        sub = Subscription.objects.get()
        self.assertEqual(sub.current_period_start, real_start)
        self.assertEqual(sub.current_period_end, real_end)

    def test_command_reports_deferred_and_retries_on_the_next_run(self):
        _evt(EventType.CHARGED, event_id="chg_orphan",
             period_start=T0, period_end=T0 + timedelta(days=30))

        out = StringIO()
        call_command("process_webhook_events", stdout=out)
        self.assertIn("DEFERRED", out.getvalue())
        self.assertEqual(WebhookEvent.objects.get(processed=False).external_event_id,
                         "chg_orphan")

        # Next run: still deferred (still no subscription).
        out2 = StringIO()
        call_command("process_webhook_events", stdout=out2)
        self.assertIn("DEFERRED", out2.getvalue())

    def test_aged_out_unmatched_charged_is_given_up_on(self):
        evt = _evt(
            EventType.CHARGED, event_id="chg_ancient",
            received_at=timezone.now() - (UNMATCHED_CHARGED_RETRY_WINDOW
                                          + timedelta(hours=1)),
        )

        with self.assertLogs("apps.billing.services", level="WARNING") as logs:
            outcome = WebhookProcessingService.process_event(evt)

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        evt.refresh_from_db()
        self.assertTrue(evt.processed)
        self.assertTrue(any("giving up" in m for m in logs.output))


class D3IdempotencyStillHoldsTests(ProcessingTestBase):
    def test_same_charged_event_twice_is_still_safe(self):
        # D4 must not regress D3's per-event idempotency.
        sub = self._subscription(status=Subscription.Status.ACTIVE)
        evt = _evt(EventType.CHARGED, event_id="chg_dup",
                   period_start=T0, period_end=T0 + timedelta(days=30),
                   event_created_at=T0 + timedelta(seconds=10))

        first = WebhookProcessingService.process_event(evt)
        second = WebhookProcessingService.process_event(evt)

        self.assertEqual(first, WebhookProcessingService.APPLIED)
        self.assertEqual(second, WebhookProcessingService.SKIPPED)
        sub.refresh_from_db()
        self.assertEqual(sub.current_period_start, T0)
        self.assertEqual(sub.current_period_end, T0 + timedelta(days=30))

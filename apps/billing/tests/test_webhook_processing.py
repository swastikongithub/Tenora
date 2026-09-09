"""
Stage D3 (v2) — turning stored, normalized `WebhookEvent` rows into
`Subscription` state changes (docs/stage-d3-v2-spec.md §4.2 / §9).

All synthetic: `WebhookEvent` rows are created directly and processed through
`WebhookProcessingService`. No live provider, no HTTP. The endpoint-level
"response stays 200 when processing fails" guarantee is at the bottom.
"""

from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.gateway.base import EventType
from apps.billing.models import (
    Plan,
    Subscription,
    SubscriptionCheckout,
    WebhookEvent,
)
from apps.billing.services import (
    PERIOD_LENGTH,
    SubscriptionService,
    WebhookProcessingService,
)
from apps.tenants.models import Tenant

SUB_ID = "sub_D3TEST"


def _event(
    event_type,
    *,
    external_subscription_id=SUB_ID,
    event_id="evt_1",
    period_start=None,
    period_end=None,
    event_created_at=None,
):
    return WebhookEvent.objects.create(
        external_event_id=event_id,
        external_subscription_id=external_subscription_id,
        event_type=event_type.value,
        raw_payload={"synthetic": True, "type": event_type.value},
        period_start=period_start,
        period_end=period_end,
        event_created_at=event_created_at,
    )


class ProcessingTestBase(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD",
            interval=Plan.Interval.MONTHLY, external_plan_id="plan_PRO",
        )
        self.annual_plan = Plan.objects.create(
            name="Yearly", code="YEARLY", price_cents=29000, currency="USD",
            interval=Plan.Interval.ANNUAL, external_plan_id="plan_YEARLY",
        )
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")

    def _checkout(self, plan=None, sub_id=SUB_ID):
        return SubscriptionCheckout.objects.create(
            tenant=self.tenant,
            plan=plan or self.plan,
            external_subscription_id=sub_id,
            status=SubscriptionCheckout.Status.CONFIRMED,
        )

    def _subscription(self, *, status=Subscription.Status.ACTIVE, sub_id=SUB_ID,
                      plan=None, period=None):
        plan = plan or self.plan
        start, end = period or SubscriptionService.default_period(plan)
        sub = SubscriptionService.create_subscription(
            tenant=self.tenant, plan=plan,
            current_period_start=start, current_period_end=end,
            external_subscription_id=sub_id,
        )
        if status != Subscription.Status.TRIALING:
            Subscription.objects.filter(pk=sub.pk).update(status=status)
            sub.refresh_from_db()
        return sub


class ActivatedTests(ProcessingTestBase):
    def test_creates_an_active_subscription_from_a_matched_checkout(self):
        self._checkout()

        outcome = WebhookProcessingService.process_event(_event(EventType.ACTIVATED))

        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        sub = Subscription.objects.get()
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.external_subscription_id, SUB_ID)
        self.assertEqual(sub.tenant, self.tenant)
        self.assertEqual(sub.plan, self.plan)
        self.assertTrue(WebhookEvent.objects.get().processed)

    def test_no_matching_checkout_is_a_logged_noop(self):
        outcome = WebhookProcessingService.process_event(_event(EventType.ACTIVATED))

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        self.assertEqual(Subscription.objects.count(), 0)
        self.assertTrue(WebhookEvent.objects.get().processed)

    def test_already_active_is_a_noop(self):
        self._subscription(status=Subscription.Status.ACTIVE)

        outcome = WebhookProcessingService.process_event(_event(EventType.ACTIVATED))

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.ACTIVE)

    def test_past_due_transitions_to_active(self):
        self._subscription(status=Subscription.Status.PAST_DUE)

        outcome = WebhookProcessingService.process_event(_event(EventType.ACTIVATED))

        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.ACTIVE)

    def test_canceled_is_not_reactivated(self):
        self._subscription(status=Subscription.Status.CANCELED)

        outcome = WebhookProcessingService.process_event(_event(EventType.ACTIVATED))

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.CANCELED)

    def test_reprocessing_twice_is_a_noop(self):
        self._checkout()
        first = _event(EventType.ACTIVATED)
        WebhookProcessingService.process_event(first)

        # a redelivery would re-run process_event on the same (now processed) row
        self.assertEqual(
            WebhookProcessingService.process_event(first),
            WebhookProcessingService.SKIPPED,
        )
        # and even a deliberate re-run with the guard cleared converges
        WebhookEvent.objects.filter(pk=first.pk).update(processed=False)
        WebhookProcessingService.process_event(first)

        self.assertEqual(Subscription.objects.count(), 1)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.ACTIVE)


class ChargedTests(ProcessingTestBase):
    def test_rolls_the_period_forward_contiguously_monthly(self):
        start = timezone.now() - timedelta(days=3)
        end = start + PERIOD_LENGTH[Plan.Interval.MONTHLY]
        sub = self._subscription(
            status=Subscription.Status.ACTIVE, period=(start, end)
        )

        WebhookProcessingService.process_event(_event(EventType.CHARGED))

        sub.refresh_from_db()
        self.assertEqual(sub.current_period_start, end)
        self.assertEqual(
            sub.current_period_end, end + PERIOD_LENGTH[Plan.Interval.MONTHLY]
        )
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)

    def test_rolls_the_period_forward_contiguously_annual(self):
        start = timezone.now()
        end = start + PERIOD_LENGTH[Plan.Interval.ANNUAL]
        sub = self._subscription(
            status=Subscription.Status.ACTIVE, plan=self.annual_plan,
            period=(start, end),
        )

        WebhookProcessingService.process_event(_event(EventType.CHARGED))

        sub.refresh_from_db()
        self.assertEqual(sub.current_period_start, end)
        self.assertEqual(
            sub.current_period_end, end + PERIOD_LENGTH[Plan.Interval.ANNUAL]
        )

    def test_uses_real_provider_period_dates_when_present(self):
        # The core proof: given real dates on the event, the subscription's
        # period is set to those EXACT values, not the default_period fallback.
        old_start = timezone.now() - timedelta(days=40)
        old_end = old_start + PERIOD_LENGTH[Plan.Interval.MONTHLY]
        sub = self._subscription(
            status=Subscription.Status.ACTIVE, period=(old_start, old_end)
        )
        real_start = timezone.now().replace(microsecond=0)
        real_end = real_start + timedelta(days=31)  # deliberately NOT 30

        WebhookProcessingService.process_event(
            _event(EventType.CHARGED, period_start=real_start, period_end=real_end)
        )

        sub.refresh_from_db()
        self.assertEqual(sub.current_period_start, real_start)
        self.assertEqual(sub.current_period_end, real_end)
        # not the contiguous-from-old_end fallback
        self.assertNotEqual(sub.current_period_start, old_end)

    def test_falls_back_to_synthesized_period_and_warns_when_dates_absent(self):
        start = timezone.now() - timedelta(days=3)
        end = start + PERIOD_LENGTH[Plan.Interval.MONTHLY]
        sub = self._subscription(
            status=Subscription.Status.ACTIVE, period=(start, end)
        )

        with self.assertLogs("apps.billing.services", level="WARNING") as logs:
            WebhookProcessingService.process_event(_event(EventType.CHARGED))

        sub.refresh_from_db()
        self.assertEqual(sub.current_period_start, end)
        self.assertEqual(
            sub.current_period_end, end + PERIOD_LENGTH[Plan.Interval.MONTHLY]
        )
        self.assertTrue(
            any("no provider period dates" in m for m in logs.output)
        )

    def test_idempotent_with_real_dates_even_with_guard_cleared(self):
        sub = self._subscription(status=Subscription.Status.ACTIVE)
        real_start = timezone.now().replace(microsecond=0)
        real_end = real_start + timedelta(days=30)
        evt = _event(
            EventType.CHARGED, period_start=real_start, period_end=real_end
        )
        WebhookProcessingService.process_event(evt)
        WebhookEvent.objects.filter(pk=evt.pk).update(processed=False)
        WebhookProcessingService.process_event(evt)

        sub.refresh_from_db()
        self.assertEqual(sub.current_period_start, real_start)
        self.assertEqual(sub.current_period_end, real_end)

    def test_past_due_is_recovered_to_active(self):
        self._subscription(status=Subscription.Status.PAST_DUE)

        outcome = WebhookProcessingService.process_event(_event(EventType.CHARGED))

        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.ACTIVE)

    def test_canceled_subscription_is_left_untouched(self):
        sub = self._subscription(status=Subscription.Status.CANCELED)
        before = (sub.current_period_start, sub.current_period_end)

        outcome = WebhookProcessingService.process_event(_event(EventType.CHARGED))

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        sub.refresh_from_db()
        self.assertEqual((sub.current_period_start, sub.current_period_end), before)
        self.assertEqual(sub.status, Subscription.Status.CANCELED)

    def test_no_match_young_charged_is_deferred_for_retry(self):
        # D4: an unmatched CHARGED (possibly arrived before its ACTIVATED) is
        # kept retryable, not permanently discarded like D3 did.
        evt = _event(EventType.CHARGED)

        outcome = WebhookProcessingService.process_event(evt)

        self.assertEqual(outcome, WebhookProcessingService.DEFERRED)
        evt.refresh_from_db()
        self.assertFalse(evt.processed)

    def test_no_match_aged_out_charged_gives_up(self):
        # D4: past the retry window, a still-unmatched CHARGED is given up on.
        evt = _event(EventType.CHARGED)
        WebhookEvent.objects.filter(pk=evt.pk).update(
            received_at=timezone.now() - timedelta(hours=25)
        )

        with self.assertLogs("apps.billing.services", level="WARNING") as logs:
            outcome = WebhookProcessingService.process_event(evt)

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        evt.refresh_from_db()
        self.assertTrue(evt.processed)
        self.assertTrue(any("giving up" in m for m in logs.output))

    def test_no_correlation_id_charged_is_a_permanent_noop(self):
        evt = _event(EventType.CHARGED, external_subscription_id=None)

        outcome = WebhookProcessingService.process_event(evt)

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        evt.refresh_from_db()
        self.assertTrue(evt.processed)

    def test_reprocessing_with_guard_cleared_only_rolls_once(self):
        start = timezone.now()
        end = start + PERIOD_LENGTH[Plan.Interval.MONTHLY]
        sub = self._subscription(
            status=Subscription.Status.ACTIVE, period=(start, end)
        )
        evt = _event(EventType.CHARGED)
        WebhookProcessingService.process_event(evt)

        # SKIPPED — the processed guard is the idempotency for a non-convergent
        # effect (period rollover isn't state a re-check can detect).
        self.assertEqual(
            WebhookProcessingService.process_event(evt),
            WebhookProcessingService.SKIPPED,
        )
        sub.refresh_from_db()
        self.assertEqual(sub.current_period_end, end + PERIOD_LENGTH[Plan.Interval.MONTHLY])


class CancelledTests(ProcessingTestBase):
    def test_active_transitions_to_canceled(self):
        self._subscription(status=Subscription.Status.ACTIVE)

        outcome = WebhookProcessingService.process_event(_event(EventType.CANCELLED))

        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.CANCELED)

    def test_already_canceled_is_a_noop(self):
        self._subscription(status=Subscription.Status.CANCELED)

        outcome = WebhookProcessingService.process_event(_event(EventType.CANCELLED))

        self.assertEqual(outcome, WebhookProcessingService.NOOP)

    def test_double_cancellation_event_is_idempotent(self):
        self._subscription(status=Subscription.Status.ACTIVE)
        evt = _event(EventType.CANCELLED)
        WebhookProcessingService.process_event(evt)
        WebhookEvent.objects.filter(pk=evt.pk).update(processed=False)
        WebhookProcessingService.process_event(evt)

        self.assertEqual(Subscription.objects.get().status, Subscription.Status.CANCELED)

    def test_no_match_is_a_logged_noop(self):
        outcome = WebhookProcessingService.process_event(_event(EventType.CANCELLED))
        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        self.assertTrue(WebhookEvent.objects.get().processed)


class PaymentTroubleTests(ProcessingTestBase):
    def test_active_transitions_to_past_due(self):
        self._subscription(status=Subscription.Status.ACTIVE)

        outcome = WebhookProcessingService.process_event(
            _event(EventType.PAYMENT_TROUBLE)
        )

        self.assertEqual(outcome, WebhookProcessingService.APPLIED)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.PAST_DUE)

    def test_already_past_due_is_a_noop(self):
        self._subscription(status=Subscription.Status.PAST_DUE)

        outcome = WebhookProcessingService.process_event(
            _event(EventType.PAYMENT_TROUBLE)
        )

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.PAST_DUE)

    def test_canceled_is_a_noop(self):
        self._subscription(status=Subscription.Status.CANCELED)

        outcome = WebhookProcessingService.process_event(
            _event(EventType.PAYMENT_TROUBLE)
        )

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.CANCELED)

    def test_trialing_is_a_noop_no_illegal_transition(self):
        self._subscription(status=Subscription.Status.TRIALING)

        outcome = WebhookProcessingService.process_event(
            _event(EventType.PAYMENT_TROUBLE)
        )

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.TRIALING)

    def test_reprocessing_twice_is_a_noop(self):
        self._subscription(status=Subscription.Status.ACTIVE)
        evt = _event(EventType.PAYMENT_TROUBLE)
        WebhookProcessingService.process_event(evt)
        WebhookEvent.objects.filter(pk=evt.pk).update(processed=False)
        WebhookProcessingService.process_event(evt)

        self.assertEqual(Subscription.objects.get().status, Subscription.Status.PAST_DUE)


class UnknownTests(ProcessingTestBase):
    def test_unknown_event_is_a_processed_noop(self):
        self._subscription(status=Subscription.Status.ACTIVE)

        outcome = WebhookProcessingService.process_event(_event(EventType.UNKNOWN))

        self.assertEqual(outcome, WebhookProcessingService.NOOP)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.ACTIVE)
        self.assertTrue(WebhookEvent.objects.get().processed)


class ProcessWebhookEventsCommandTests(ProcessingTestBase):
    def test_processes_pending_leaves_processed_alone(self):
        self._checkout()
        pending = _event(EventType.ACTIVATED, event_id="evt_pending")
        done = _event(EventType.CANCELLED, event_id="evt_done")
        WebhookEvent.objects.filter(pk=done.pk).update(processed=True)

        out = StringIO()
        call_command("process_webhook_events", stdout=out)

        pending.refresh_from_db()
        self.assertTrue(pending.processed)
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.ACTIVE)
        self.assertIn("evt_pending", out.getvalue())
        self.assertNotIn("evt_done", out.getvalue())

    def test_nothing_to_do(self):
        out = StringIO()
        call_command("process_webhook_events", stdout=out)
        self.assertIn("Nothing to do", out.getvalue())

    def test_a_row_that_raises_does_not_abort_the_run(self):
        self._checkout()
        _event(EventType.ACTIVATED, event_id="evt_ok")
        _event(EventType.CHARGED, event_id="evt_boom", external_subscription_id="sub_OTHER")

        real = WebhookProcessingService.process_event

        def flaky(event):
            if event.external_event_id == "evt_boom":
                raise RuntimeError("boom")
            return real(event)

        out, err = StringIO(), StringIO()
        with mock.patch.object(
            WebhookProcessingService, "process_event", side_effect=flaky
        ):
            call_command("process_webhook_events", stdout=out, stderr=err)

        self.assertEqual(Subscription.objects.get().status, Subscription.Status.ACTIVE)
        self.assertIn("evt_boom", err.getvalue())


class WebhookEndpointProcessingFailureTests(APITestCase):
    """The HTTP response must stay 200 when inline processing raises — the event
    is stored and left for the retry command (spec §1)."""

    URL = "/api/webhooks/razorpay/"

    def test_processing_exception_does_not_change_the_200(self):
        import hashlib
        import hmac
        import json

        secret = "whsec_x"
        payload = {
            "event": "subscription.activated",
            "payload": {"subscription": {"entity": {"id": "sub_Z"}}},
        }
        raw = json.dumps(payload).encode()
        sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

        with self.settings(
            PAYMENT_GATEWAY="razorpay", RAZORPAY_WEBHOOK_SECRET=secret
        ), mock.patch(
            "apps.billing.views.WebhookProcessingService.process_event",
            side_effect=RuntimeError("kaboom"),
        ):
            resp = self.client.post(
                self.URL, data=raw, content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=sig,
                HTTP_X_RAZORPAY_EVENT_ID="evt_fail_1",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        event = WebhookEvent.objects.get()
        self.assertEqual(event.external_event_id, "evt_fail_1")
        self.assertFalse(event.processed)
        self.assertEqual(event.external_subscription_id, "sub_Z")

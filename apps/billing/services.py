import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing.gateway import get_gateway
from apps.billing.gateway.base import (
    EventType,
    ProviderSubscriptionStatus,
    ProviderUnavailable,
)
from apps.billing.models import (
    Plan,
    ProrationRecord,
    ReconciliationDiscrepancy,
    Subscription,
    SubscriptionCheckout,
    UsageRecord,
    WebhookEvent,
)
from apps.tenants.models import Membership, Tenant

logger = logging.getLogger(__name__)

# Placeholder billing-period lengths, keyed by Plan.interval. Nothing
# real depends on these in Phase 1 — Stripe owns period boundaries in
# Phase 2. Fixed timedeltas (not calendar months) so no date library
# is needed.
PERIOD_LENGTH = {
    Plan.Interval.MONTHLY: timedelta(days=30),
    Plan.Interval.ANNUAL: timedelta(days=365),
}

# D4: a CHARGED event with no matching Subscription/SubscriptionCheckout yet is
# kept retryable (it may be a CHARGED that arrived before its ACTIVATED) instead
# of D3's permanent discard — but only for this long. The real CHARGED↔ACTIVATED
# gap is seconds-to-minutes; this window generously covers redelivery/backfill
# lag while ensuring a genuinely unmatchable event (garbage id) stops retrying.
UNMATCHED_CHARGED_RETRY_WINDOW = timedelta(hours=24)

# Explicit legal-transition table. Anything not listed here is
# rejected — including CANCELED -> ACTIVE, which is not allowed
# until Phase 2 defines actual reactivation semantics.
LEGAL_TRANSITIONS = {
    Subscription.Status.TRIALING: {Subscription.Status.ACTIVE, Subscription.Status.CANCELED},
    Subscription.Status.ACTIVE: {Subscription.Status.PAST_DUE, Subscription.Status.CANCELED},
    Subscription.Status.PAST_DUE: {Subscription.Status.ACTIVE, Subscription.Status.CANCELED},
    Subscription.Status.CANCELED: set(),  # terminal
}


class IllegalStateTransition(Exception):
    pass


class SubscriptionAlreadyExists(Exception):
    """
    Raised when create_subscription hits the Tenant OneToOne
    constraint — the tenant already has a subscription. Changing an
    existing subscription is PATCH's job, not a second POST.
    """


class SubscriptionService:
    """
    All subscription mutations go through here, not through
    serializers or views directly. This is the seam Phase 2 (Stripe)
    will hook into — the same business operation will eventually
    touch the DB, Stripe, webhook state, and Celery, and that
    can't live inside a DRF serializer.
    """

    @staticmethod
    def default_period(plan, start=None):
        """
        Phase 1 placeholder billing period: now -> now + interval
        length. Returned as a (start, end) tuple for create_subscription.
        """
        start = start or timezone.now()
        return start, start + PERIOD_LENGTH[plan.interval]

    @staticmethod
    def create_subscription(
        tenant,
        plan,
        current_period_start,
        current_period_end,
        external_subscription_id=None,
    ):
        try:
            with transaction.atomic():
                return Subscription.objects.create(
                    tenant=tenant,
                    plan=plan,
                    status=Subscription.Status.TRIALING,
                    current_period_start=current_period_start,
                    current_period_end=current_period_end,
                    external_subscription_id=external_subscription_id,
                )
        except IntegrityError:
            # Caught OUTSIDE the atomic block that raised it — the `with`
            # opened a savepoint that is already rolled back here, so the
            # surrounding transaction stays usable (same pattern as
            # MembershipService.add_member). A DB constraint, not a pre-check,
            # is the real guarantee — either the Tenant OneToOne or (since D3)
            # the unique `external_subscription_id`; both mean "this
            # subscription already exists", so both collapse to one exception.
            raise SubscriptionAlreadyExists()

    @staticmethod
    @transaction.atomic
    def transition_status(subscription, new_status):
        allowed = LEGAL_TRANSITIONS.get(subscription.status, set())
        if new_status not in allowed:
            raise IllegalStateTransition(
                f"Cannot transition from {subscription.status} to {new_status}."
            )
        subscription.status = new_status
        subscription.save(update_fields=["status", "updated_at"])
        return subscription

    @staticmethod
    @transaction.atomic
    def change_plan(subscription, new_plan):
        # CANCELED is terminal for the plan field too, not just for status.
        # Master spec §B.5 names change_plan as one of the state machine's
        # enforcement points, but this guard was missing — without it a
        # canceled subscription could have its plan silently reassigned, which
        # has no meaning (there is no active period to apply it to) and no DB
        # constraint to catch it. Same exception as an illegal status move:
        # conceptually the same guarantee, "a terminal subscription cannot
        # change", regardless of which field the caller aimed at.
        if subscription.status == Subscription.Status.CANCELED:
            raise IllegalStateTransition(
                f"Cannot change the plan of a {subscription.status} subscription."
            )
        from_plan = subscription.plan
        # D6: record the mid-cycle proration calculation as an audit entry.
        # Best-effort and never-raising by contract — a proration failure must
        # not block the plan swap that already works (stage-d6-spec.md §4.3/§11).
        # This does NOT change whether the swap is accepted (a same-plan call
        # still succeeds, records nothing — see record_for_plan_change).
        ProrationService.record_for_plan_change(subscription, from_plan, new_plan)
        subscription.plan = new_plan
        subscription.save(update_fields=["plan", "updated_at"])
        return subscription

    @staticmethod
    def cancel_subscription(subscription):
        return SubscriptionService.transition_status(
            subscription, Subscription.Status.CANCELED
        )


# --- Payment gateway orchestration ---------------------------------------
#
# These are provider-NEUTRAL domain services. Every external call goes through
# `get_gateway()` — the request bodies, HMAC constructions and SDK calls live in
# `apps.billing.gateway.razorpay`, not here (payment-gateway-adapter-spec.md §1).


class PlanSyncService:
    """
    Maps each local Plan to a gateway-side plan. The gateway call lives in the
    adapter; this orchestrates the check-then-create and the local write-back.
    """

    @staticmethod
    def sync_plan(plan):
        """
        Ensure `plan` has an `external_plan_id`, creating the gateway plan if
        not. Idempotent: a plan that already has an id is a no-op.

        Not transaction-wrapped around the gateway call (create-plan has no
        idempotency key): the local id is written immediately after a successful
        create, so the only failure window is a crash *between* the two, which
        would orphan a gateway-side plan.
        """
        if plan.external_plan_id:
            return plan.external_plan_id

        external_plan_id = get_gateway().create_plan(plan)
        Plan.objects.filter(pk=plan.pk).update(external_plan_id=external_plan_id)
        plan.external_plan_id = external_plan_id
        return external_plan_id


class PlanNotSyncedToGateway(Exception):
    """The plan has no external_plan_id — `sync_razorpay_plans` hasn't run for
    it (or the gateway's subscriptions product isn't active yet). Checkout can't
    proceed; surfaced as a clean 400, never a crash."""


class CheckoutPlanMismatch(Exception):
    """A checkout for a different plan is already in flight for this tenant."""


class CheckoutSignatureInvalid(Exception):
    """Bad, tampered, or mismatched Checkout success signature."""


class CheckoutService:
    """
    Creates the gateway subscription for a tenant's checkout and verifies the
    checkout success handshake. Never creates or mutates a local `Subscription`
    row — only D3's verified webhook may (spec §1/§11).
    """

    @staticmethod
    def create_checkout(tenant, plan):
        """
        Ensure a gateway subscription exists for this tenant's in-flight
        checkout of `plan`, and return the `SubscriptionCheckout` row.

        Double-click safe: the row is OneToOne on tenant and the
        `select_for_update()` serialises concurrent calls, so the gateway's
        `create_subscription` runs AT MOST ONCE per tenant — a second caller
        blocks, then sees the id and reuses it. The gateway call sits inside the
        transaction on purpose: it's one short call, and it's the price of
        "exactly once" when the remote API has no idempotency key.
        """
        if not plan.external_plan_id:
            raise PlanNotSyncedToGateway()

        with transaction.atomic():
            # select_for_update on the get_or_create: the winner of a concurrent
            # INSERT holds the row lock; the loser's IntegrityError makes
            # get_or_create retry the (now locked) get, which BLOCKS until the
            # winner commits and then returns the winner's row. So exactly one
            # request proceeds to create the gateway subscription.
            checkout, _ = (
                SubscriptionCheckout.objects.select_for_update()
                .select_related("plan")
                .get_or_create(tenant=tenant, defaults={"plan": plan})
            )

            if checkout.external_subscription_id:
                if checkout.plan_id == plan.id:
                    return checkout  # reuse — a second click re-opens the same Checkout
                raise CheckoutPlanMismatch()

            external_subscription_id = get_gateway().create_subscription(
                tenant, plan
            )
            checkout.plan = plan
            checkout.external_subscription_id = external_subscription_id
            checkout.status = SubscriptionCheckout.Status.CREATED
            checkout.save(
                update_fields=[
                    "plan",
                    "external_subscription_id",
                    "status",
                    "updated_at",
                ]
            )
            return checkout

    @staticmethod
    def confirm_checkout(tenant, payment_id, subscription_id, signature):
        """
        Verify the checkout success callback for this tenant's checkout. On
        success, mark the `SubscriptionCheckout` CONFIRMED — a UI-feedback /
        audit flag, NOT a subscription activation. Returns nothing; raises
        `SubscriptionCheckout.DoesNotExist` if there's no checkout, or
        `CheckoutSignatureInvalid` on a bad/tampered/mismatched signature.

        Never creates or touches a local `Subscription` row.
        """
        checkout = SubscriptionCheckout.objects.for_tenant(tenant).get()

        # The subscription_id the signature is verified against comes from OUR
        # record, not the client's body — and the body's value must match it,
        # or the callback isn't about this checkout.
        stored_id = checkout.external_subscription_id
        if not stored_id or subscription_id != stored_id:
            raise CheckoutSignatureInvalid()
        if not get_gateway().verify_checkout_signature(
            payment_id, stored_id, signature
        ):
            raise CheckoutSignatureInvalid()

        if checkout.status != SubscriptionCheckout.Status.CONFIRMED:
            checkout.status = SubscriptionCheckout.Status.CONFIRMED
            checkout.save(update_fields=["status", "updated_at"])


class WebhookService:
    """DB-backed storage + dedup for verified, normalized gateway events."""

    @staticmethod
    def record_event(
        external_event_id,
        event_type,
        raw_payload,
        external_subscription_id=None,
        period_start=None,
        period_end=None,
        event_created_at=None,
    ):
        """
        Store one verified event and return its `WebhookEvent` row — the freshly
        created one, or the existing row if an event with this id was already
        stored (a gateway redelivery — expected, not an error). Returning the row
        either way lets the caller (re)run D3 processing against it; the
        `processed` guard makes a redelivery's reprocessing a safe no-op.

        The unique constraint on `external_event_id` is the real guarantee. The
        IntegrityError is caught OUTSIDE the atomic block that raised it
        (CLAUDE.md) — a nested savepoint, so the surrounding request transaction
        stays usable.
        """
        try:
            with transaction.atomic():
                return WebhookEvent.objects.create(
                    external_event_id=external_event_id,
                    event_type=event_type,
                    raw_payload=raw_payload,
                    external_subscription_id=external_subscription_id,
                    period_start=period_start,
                    period_end=period_end,
                    event_created_at=event_created_at,
                )
        except IntegrityError:
            return WebhookEvent.objects.get(external_event_id=external_event_id)


@dataclass(frozen=True)
class SweptEvent:
    """One `WebhookEvent` handled by `WebhookProcessingService.process_pending`."""

    external_event_id: str
    event_type: str
    #: `WebhookProcessingService.APPLIED` / `NOOP` / `SKIPPED` / `DEFERRED`, or
    #: `None` when `process_event` raised.
    outcome: "str | None"
    #: `str(exc)` when `process_event` raised, else `None`.
    error: "str | None"


@dataclass(frozen=True)
class WebhookSweepResult:
    """The outcome of one retry sweep — consumed identically by the
    `process_webhook_events` management command and the
    `billing.process_webhook_events` Celery task."""

    events: list

    @property
    def total(self):
        return len(self.events)

    @property
    def deferred(self):
        return [
            e for e in self.events
            if e.outcome == WebhookProcessingService.DEFERRED
        ]

    @property
    def failed(self):
        return [e for e in self.events if e.error is not None]

    @property
    def processed(self):
        """Events applied or already-settled (APPLIED / NOOP / SKIPPED) — i.e.
        neither deferred nor failed."""
        return [
            e for e in self.events
            if e.error is None
            and e.outcome != WebhookProcessingService.DEFERRED
        ]


class WebhookProcessingService:
    """
    stage-d3-v2-spec.md §4.2 — apply a stored, normalized `WebhookEvent` to
    `Subscription` state, idempotently, switching on `EventType` ONLY (never a
    provider event name, never `raw_payload` shape — §11).

    All status changes go through `SubscriptionService`; this service never
    assigns `Subscription.status` directly.
    """

    #: process_event outcomes — for the management command's summary / tests.
    APPLIED = "APPLIED"
    SKIPPED = "SKIPPED"  # already processed
    NOOP = "NOOP"  # handled, but nothing to change
    DEFERRED = "DEFERRED"  # D4: not applied, deliberately left retryable

    @staticmethod
    @transaction.atomic
    def process_event(event):
        """
        Process one `WebhookEvent`. Everything below runs in ONE transaction (the
        decorator): an unexpected exception rolls it all back, leaving
        `processed=False` for the retry command. Ordered steps, each holding its
        lock until COMMIT so a concurrent delivery observes all of them together
        or none:

          0. select_for_update the event row; re-check `processed` (D3 per-event
             idempotency).
          1. D4: select_for_update the subscription row (when one exists).
          2. D4: staleness check — an event the provider generated before the
             last one already applied to this subscription is a safe no-op
             (CANCELLED exempt — terminal state is a safety floor).
          3. dispatch to the per-EventType handler.
          4. D4: advance `Subscription.last_event_at` when a newer event was
             actually APPLIED to a pre-existing subscription.
          5. mark `processed=True` — unless the outcome is DEFERRED.
        """
        event = WebhookEvent.objects.select_for_update().get(pk=event.pk)
        if event.processed:
            return WebhookProcessingService.SKIPPED

        # 1. Lock the subscription so the staleness check and the last_event_at
        #    advance see a consistent view against a concurrent trigger for
        #    another event on the same subscription.
        sub_before = (
            Subscription.objects.select_for_update()
            .filter(external_subscription_id=event.external_subscription_id)
            .first()
            if event.external_subscription_id
            else None
        )

        # 2. Out-of-order guard.
        if WebhookProcessingService._is_stale(event, sub_before):
            logger.warning(
                "webhook %s (%s): provider-generated %s, older than the last "
                "applied event %s for subscription %s — superseded, no-op",
                event.external_event_id,
                event.event_type,
                event.event_created_at,
                sub_before.last_event_at,
                event.external_subscription_id,
            )
            outcome = WebhookProcessingService.NOOP
        else:
            handler = {
                EventType.ACTIVATED: WebhookProcessingService._handle_activated,
                EventType.CHARGED: WebhookProcessingService._handle_charged,
                EventType.CANCELLED: WebhookProcessingService._handle_cancelled,
                EventType.PAYMENT_TROUBLE: WebhookProcessingService._handle_payment_trouble,
                EventType.UNKNOWN: WebhookProcessingService._handle_unknown,
            }.get(event.event_type, WebhookProcessingService._handle_unknown)

            try:
                outcome = handler(event)
            except IllegalStateTransition as exc:
                # A rejected transition is a permanent decision, not a transient
                # failure — mark processed so the retry command doesn't loop.
                logger.warning(
                    "webhook %s (%s): illegal transition, marking processed: %s",
                    event.external_event_id,
                    event.event_type,
                    exc,
                )
                outcome = WebhookProcessingService.NOOP

            # 4. Advance the high-water mark. Only when a real change was applied
            #    to a subscription that ALREADY existed — the creating ACTIVATED
            #    is the baseline, not a "later" event, so it leaves the mark
            #    unset and the first CHARGED is never encumbered.
            if (
                outcome == WebhookProcessingService.APPLIED
                and sub_before is not None
                and event.event_created_at is not None
                and (
                    sub_before.last_event_at is None
                    or event.event_created_at > sub_before.last_event_at
                )
            ):
                sub_before.last_event_at = event.event_created_at
                sub_before.save(update_fields=["last_event_at", "updated_at"])

        # 5. A DEFERRED event stays retryable (processed=False).
        if outcome is not WebhookProcessingService.DEFERRED:
            event.processed = True
            event.save(update_fields=["processed"])
        return outcome

    @staticmethod
    def _is_stale(event, subscription):
        """D4: whether `event` is chronologically behind what's already been
        applied to `subscription`. CANCELLED is never stale — a terminal state
        must not be blocked by a missing or confused timestamp."""
        return (
            subscription is not None
            and event.event_type != EventType.CANCELLED
            and event.event_created_at is not None
            and subscription.last_event_at is not None
            and event.event_created_at < subscription.last_event_at
        )

    # -- handlers: each returns APPLIED or NOOP; each matches by the normalized
    #    external_subscription_id and treats "no match" as a logged no-op ------

    @staticmethod
    def _subscription_for(event):
        if not event.external_subscription_id:
            return None
        return Subscription.objects.filter(
            external_subscription_id=event.external_subscription_id
        ).select_related("plan").first()

    @staticmethod
    def _log_no_match(event):
        logger.warning(
            "webhook %s (%s): no subscription matches external_subscription_id=%r",
            event.external_event_id,
            event.event_type,
            event.external_subscription_id,
        )

    @staticmethod
    def _handle_activated(event):
        subscription = WebhookProcessingService._subscription_for(event)
        if subscription is not None:
            if subscription.status == Subscription.Status.ACTIVE:
                return WebhookProcessingService.NOOP
            if subscription.status == Subscription.Status.CANCELED:
                logger.warning(
                    "webhook %s: ACTIVATED for a CANCELED subscription %s — "
                    "no reactivation",
                    event.external_event_id,
                    subscription.external_subscription_id,
                )
                return WebhookProcessingService.NOOP
            SubscriptionService.transition_status(
                subscription, Subscription.Status.ACTIVE
            )
            return WebhookProcessingService.APPLIED

        # No local row yet — this event is what creates it. Match the in-flight
        # checkout for tenant + plan.
        checkout = (
            SubscriptionCheckout.objects.filter(
                external_subscription_id=event.external_subscription_id
            )
            .select_related("plan", "tenant")
            .first()
            if event.external_subscription_id
            else None
        )
        if checkout is None:
            WebhookProcessingService._log_no_match(event)
            return WebhookProcessingService.NOOP

        start, end = SubscriptionService.default_period(checkout.plan)
        try:
            subscription = SubscriptionService.create_subscription(
                tenant=checkout.tenant,
                plan=checkout.plan,
                current_period_start=start,
                current_period_end=end,
                external_subscription_id=event.external_subscription_id,
            )
        except SubscriptionAlreadyExists:
            # A concurrent trigger (or a stale in-flight checkout for a tenant
            # that already subscribed) beat us to it — converge on the existing
            # row rather than crash.
            logger.info(
                "webhook %s: subscription already exists — converging",
                event.external_event_id,
            )
            subscription = WebhookProcessingService._subscription_for(event)
            if subscription is None:
                subscription = Subscription.objects.select_related("plan").get(
                    tenant=checkout.tenant
                )

        if subscription.status not in (
            Subscription.Status.ACTIVE,
            Subscription.Status.CANCELED,
        ):
            SubscriptionService.transition_status(
                subscription, Subscription.Status.ACTIVE
            )
        return WebhookProcessingService.APPLIED

    @staticmethod
    def _handle_charged(event):
        subscription = WebhookProcessingService._subscription_for(event)
        if subscription is None:
            # D4: a CHARGED with no local row yet may be one that arrived BEFORE
            # its ACTIVATED (which is what creates the row). Keep it retryable so
            # a later `process_webhook_events` run — after ACTIVATED lands —
            # recovers its real period data, instead of D3's permanent discard.
            # Bounded so a genuinely unmatchable id doesn't retry forever.
            if not event.external_subscription_id:
                WebhookProcessingService._log_no_match(event)
                return WebhookProcessingService.NOOP
            age = timezone.now() - event.received_at
            if age > UNMATCHED_CHARGED_RETRY_WINDOW:
                logger.warning(
                    "webhook %s: CHARGED still unmatched after %s (> %s) — "
                    "giving up",
                    event.external_event_id,
                    age,
                    UNMATCHED_CHARGED_RETRY_WINDOW,
                )
                return WebhookProcessingService.NOOP
            logger.info(
                "webhook %s: CHARGED has no subscription yet (age %s) — "
                "deferring for retry",
                event.external_event_id,
                age,
            )
            return WebhookProcessingService.DEFERRED
        if subscription.status == Subscription.Status.CANCELED:
            logger.warning(
                "webhook %s: CHARGED for a CANCELED subscription %s — ignored",
                event.external_event_id,
                subscription.external_subscription_id,
            )
            return WebhookProcessingService.NOOP

        # Prefer the provider's real billing period, persisted on the event row
        # at storage time (fix-real-period-dates-spec.md). Real dates are
        # absolute values from the event, so applying them is convergent — a
        # reprocess can't drift the period. The synthesized fallback stays as an
        # honest, LOGGED safety net for a payload that legitimately carried no
        # period (deterministic, contiguous from the current end).
        if event.period_start and event.period_end:
            # D4 period monotonicity: a CHARGED whose whole billing period ends
            # at or before the current period's START is chronologically stale
            # (an older redelivery processed after a newer CHARGED already
            # advanced us). Safe no-op — no period write, no status change.
            # Checked against period_start (not period_end) so the FIRST real
            # CHARGED after ACTIVATED — whose provider period starts ≈ the
            # subscription's synthesized default_period start — is never rejected.
            if event.period_end <= subscription.current_period_start:
                logger.warning(
                    "webhook %s: CHARGED period %s–%s ends at/before the current "
                    "period start %s — stale, no-op",
                    event.external_event_id,
                    event.period_start,
                    event.period_end,
                    subscription.current_period_start,
                )
                return WebhookProcessingService.NOOP
            start, end = event.period_start, event.period_end
        else:
            start, end = SubscriptionService.default_period(
                subscription.plan, start=subscription.current_period_end
            )
            logger.warning(
                "webhook %s: CHARGED carried no provider period dates — "
                "using synthesized fallback period",
                event.external_event_id,
            )
        subscription.current_period_start = start
        subscription.current_period_end = end
        subscription.save(
            update_fields=[
                "current_period_start",
                "current_period_end",
                "updated_at",
            ]
        )
        if subscription.status in (
            Subscription.Status.PAST_DUE,
            Subscription.Status.TRIALING,
        ):
            SubscriptionService.transition_status(
                subscription, Subscription.Status.ACTIVE
            )
        return WebhookProcessingService.APPLIED

    @staticmethod
    def _handle_cancelled(event):
        subscription = WebhookProcessingService._subscription_for(event)
        if subscription is None:
            WebhookProcessingService._log_no_match(event)
            return WebhookProcessingService.NOOP
        if subscription.status == Subscription.Status.CANCELED:
            return WebhookProcessingService.NOOP
        SubscriptionService.cancel_subscription(subscription)
        return WebhookProcessingService.APPLIED

    @staticmethod
    def _handle_payment_trouble(event):
        subscription = WebhookProcessingService._subscription_for(event)
        if subscription is None:
            WebhookProcessingService._log_no_match(event)
            return WebhookProcessingService.NOOP
        if subscription.status == Subscription.Status.ACTIVE:
            SubscriptionService.transition_status(
                subscription, Subscription.Status.PAST_DUE
            )
            return WebhookProcessingService.APPLIED
        # PAST_DUE / CANCELED → nothing to do. TRIALING → PAST_DUE isn't a legal
        # transition and this stage doesn't redesign the state machine.
        if subscription.status == Subscription.Status.TRIALING:
            logger.warning(
                "webhook %s: PAYMENT_TROUBLE for a TRIALING subscription %s — "
                "no legal transition, ignored",
                event.external_event_id,
                subscription.external_subscription_id,
            )
        return WebhookProcessingService.NOOP

    @staticmethod
    def _handle_unknown(event):
        logger.info(
            "webhook %s: event_type=%r has no D3 handler — stored, no state change",
            event.external_event_id,
            event.event_type,
        )
        return WebhookProcessingService.NOOP

    @staticmethod
    def process_pending():
        """
        Run `process_event` over every unprocessed `WebhookEvent`, oldest first
        (stage-d1-spec.md §4.3 / stage-d4-spec.md §4.2). Inline processing in
        `RazorpayWebhookView` is best-effort — a row it couldn't handle stays
        `processed=False`; a D4 `DEFERRED` row stays `processed=False` until its
        matching subscription exists. This is the sweep that resolves both.

        A per-row exception is captured (logged, recorded on the result), never
        propagated — one bad row must not abort the sweep.

        The orchestration lives HERE, once: the `process_webhook_events`
        management command and the `billing.process_webhook_events` Celery task
        are both thin callers of this (docs/stage-d7-spec.md §5).
        """
        events = []
        pending = WebhookEvent.objects.filter(processed=False).order_by(
            "received_at"
        )
        for event in pending:
            try:
                outcome = WebhookProcessingService.process_event(event)
                events.append(
                    SweptEvent(
                        event.external_event_id, event.event_type, outcome, None
                    )
                )
            except Exception as exc:  # noqa: BLE001 — one bad row can't abort the sweep
                logger.exception(
                    "webhook sweep: %s (%s) failed",
                    event.external_event_id,
                    event.event_type,
                )
                events.append(
                    SweptEvent(
                        event.external_event_id, event.event_type, None, str(exc)
                    )
                )
        return WebhookSweepResult(events)


@dataclass(frozen=True)
class UsageSnapshotBatchResult:
    """The outcome of one metering run — consumed identically by the
    `meter_usage` management command and the `billing.meter_usage` Celery task."""

    #: The `UsageRecord` rows newly created this run.
    records: list
    #: Tenants whose snapshot for this period already existed (a re-run no-op).
    existing: int
    #: Tenants skipped for `NoBillingPeriod` (the queryset excludes these; a
    #: defensive tally only).
    skipped: int
    #: Total tenants considered.
    total: int


class UsageMeteringService:
    """
    Snapshot metering (docs/stage-d5-spec.md). Records real, already-tracked
    usage per tenant per billing period — the foundation D6 (proration) builds
    on. Nothing is fabricated: the only metric is `active_members`, a count of
    the tenant's real `Membership` rows.

    Eligibility rule: **a tenant is metered iff it has a `Subscription` row.
    Subscription STATUS is irrelevant** — TRIALING, ACTIVE, PAST_DUE and
    CANCELED are all metered, because the row's `current_period_start` /
    `current_period_end` are the real billing-period boundaries and the snapshot
    is recorded against them verbatim (spec §8: a canceled/plan-changed
    subscription "uses whatever period is currently on the Subscription at
    snapshot time"). The ONLY tenant skipped is one with no `Subscription` row
    at all — it has no real period and is never given an invented one.

    Idempotency is the DB constraint `UNIQUE(tenant, metric, period_start,
    period_end)`, not an application pre-check — a re-run for an already-recorded
    period is a safe no-op that does NOT refresh the count (the row is
    immutable).
    """

    class NoBillingPeriod(Exception):
        """The tenant has no `Subscription` — no billing period to snapshot
        against. Not an error condition, a skip condition."""

    @staticmethod
    def _count(metric, tenant):
        """The real current quantity of `metric` for `tenant`."""
        if metric == UsageRecord.Metric.ACTIVE_MEMBERS:
            # Every Membership row is an occupied seat — there is no is_active
            # flag and no removal path. Not filtered by `user.is_active` (an
            # admin-disable, orthogonal to seat occupancy).
            return Membership.objects.for_tenant(tenant).count()
        raise ValueError(f"No counter defined for metric {metric!r}")

    @staticmethod
    def record_snapshot(tenant, metric=UsageRecord.Metric.ACTIVE_MEMBERS):
        """
        Snapshot `metric` for `tenant` against its CURRENT `Subscription`
        billing period. Returns `(record, created: bool)`. Raises
        `NoBillingPeriod` when the tenant has no `Subscription` (any status is
        fine — only the absence of the row is a skip).

        Idempotent via the `unique_usage_snapshot` constraint: a second call for
        an already-recorded (tenant, metric, period) returns the existing row
        with `created=False` and does NOT refresh its quantity.
        """
        try:
            subscription = Subscription.objects.for_tenant(tenant).get()
        except Subscription.DoesNotExist:
            logger.info(
                "usage: tenant %s has no subscription — snapshot skipped",
                tenant.id,
            )
            raise UsageMeteringService.NoBillingPeriod()

        start = subscription.current_period_start
        end = subscription.current_period_end
        quantity = UsageMeteringService._count(metric, tenant)

        try:
            with transaction.atomic():
                record = UsageRecord.objects.create(
                    tenant=tenant,
                    metric=metric,
                    quantity=quantity,
                    period_start=start,
                    period_end=end,
                )
            return record, True
        except IntegrityError:
            # The UNIQUE constraint — not the (racy) pre-check — is the
            # guarantee. Caught OUTSIDE the atomic block that raised it
            # (CLAUDE.md); same shape as WebhookService.record_event.
            existing = UsageRecord.objects.for_tenant(tenant).get(
                metric=metric, period_start=start, period_end=end
            )
            return existing, False

    @staticmethod
    def snapshot_all_subscribed(metric=UsageRecord.Metric.ACTIVE_MEMBERS):
        """
        Snapshot `metric` for every tenant that has a `Subscription` row (any
        status — the eligibility rule above), via `record_snapshot`. Idempotent
        by the `unique_usage_snapshot` constraint, so running it more often than
        once per billing period is harmless.

        The orchestration lives HERE, once: the `meter_usage` management command
        and the `billing.meter_usage` Celery task are both thin callers of this
        (docs/stage-d7-spec.md §5).
        """
        tenants = Tenant.objects.filter(subscription__isnull=False).order_by(
            "created_at"
        )
        records = []
        existing = skipped = total = 0
        for tenant in tenants:
            total += 1
            try:
                record, created = UsageMeteringService.record_snapshot(
                    tenant, metric
                )
            except UsageMeteringService.NoBillingPeriod:
                skipped += 1
                continue
            if created:
                records.append(record)
            else:
                existing += 1
        return UsageSnapshotBatchResult(
            records=records, existing=existing, skipped=skipped, total=total
        )

    # --- query methods (spec §4.4) — a plain query, not a reporting layer -----

    @staticmethod
    def usage_for_period(
        tenant,
        period_start,
        period_end,
        metric=UsageRecord.Metric.ACTIVE_MEMBERS,
    ):
        """The recorded `UsageRecord` for this exact tenant/metric/period, or
        `None`. What D6 (proration) consumes."""
        return (
            UsageRecord.objects.for_tenant(tenant)
            .filter(
                metric=metric, period_start=period_start, period_end=period_end
            )
            .first()
        )

    @staticmethod
    def current_usage(tenant, metric=UsageRecord.Metric.ACTIVE_MEMBERS):
        """The recorded `UsageRecord` for the tenant's CURRENT billing period,
        or `None` (also `None` when the tenant has no `Subscription`)."""
        try:
            subscription = Subscription.objects.for_tenant(tenant).get()
        except Subscription.DoesNotExist:
            return None
        return UsageMeteringService.usage_for_period(
            tenant,
            subscription.current_period_start,
            subscription.current_period_end,
            metric,
        )


@dataclass(frozen=True)
class ProrationResult:
    """The output of one proration calculation. `net_amount_cents` is the
    authoritative signed value; the rest is context for the audit record and for
    test transparency."""

    net_amount_cents: int
    currency: str
    calculated_at: datetime
    period_start: datetime
    period_end: datetime
    #: Exact fraction of the billing period still remaining at `calculated_at`.
    fraction_remaining: Fraction


class ProrationService:
    """
    Mid-cycle plan-change proration — standard billing math, recorded as an
    audit entry (docs/stage-d6-spec.md). NOTHING here charges, refunds, or calls
    a payment gateway. `calculate` is a pure function; `record_for_plan_change`
    is a best-effort, never-raising step wired into
    `SubscriptionService.change_plan`.
    """

    class InvalidPeriod(Exception):
        """The billing period is degenerate (end <= start, or sub-second) — no
        meaningful ratio to compute."""

    @staticmethod
    def calculate(
        *,
        from_price_cents,
        to_price_cents,
        currency,
        period_start,
        period_end,
        now,
    ) -> "ProrationResult":
        """
        Pure and deterministic — no DB, no gateway, no `timezone.now()`.

            fraction_remaining = remaining / total          (of the billing period)
            net = (to_price_cents - from_price_cents) * fraction_remaining

        `net` is computed with exact rational arithmetic (`fractions.Fraction`)
        and rounded to the nearest integer cent EXACTLY ONCE, ties away from zero
        (`decimal.ROUND_HALF_UP`):
          - rounding the net once bounds the error to < 0.5c; rounding the unused
            credit and the new charge separately and subtracting can compound to
            +/-1c;
          - `Fraction` keeps every intermediate exact — no float drift, per the
            project's "never floats for money" rule;
          - ties away from zero is symmetric for upgrades (+) and downgrades (-).

        `now` is clamped into the period, so a lapsed period (now > period_end)
        gives `net == 0` rather than a wrong-signed result, and a pre-start `now`
        gives the full-period delta.

        Positive net = extra owed (upgrade); negative = credit owed (downgrade).
        """
        total = period_end - period_start
        if total < timedelta(seconds=1):
            raise ProrationService.InvalidPeriod(
                f"billing period is degenerate: {period_start} .. {period_end}"
            )

        remaining = max(timedelta(0), min(period_end - now, total))
        one_us = timedelta(microseconds=1)
        fraction_remaining = Fraction(remaining // one_us, total // one_us)

        net = Fraction(to_price_cents - from_price_cents) * fraction_remaining
        net_amount_cents = int(
            (Decimal(net.numerator) / Decimal(net.denominator)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        return ProrationResult(
            net_amount_cents=net_amount_cents,
            currency=currency,
            calculated_at=now,
            period_start=period_start,
            period_end=period_end,
            fraction_remaining=fraction_remaining,
        )

    @staticmethod
    def record_for_plan_change(subscription, from_plan, to_plan, *, now=None):
        """
        Compute and store a `ProrationRecord` for a mid-cycle plan change.

        Contract: **NEVER raises**. A calculation or DB failure here must not
        block the plan swap in `SubscriptionService.change_plan`
        (stage-d6-spec.md §11) — the whole body is guarded, and the insert sits
        in a nested `transaction.atomic()` savepoint so a real `IntegrityError`
        rolls back only the savepoint and leaves the caller's transaction usable
        (CLAUDE.md; same pattern as `WebhookService.record_event`).

        Returns the `ProrationRecord`, or `None` when it was skipped (same plan,
        or a currency change) or failed. Does not change whether the plan swap
        itself happens.
        """
        now = now or timezone.now()
        try:
            if from_plan.pk == to_plan.pk:
                # Not a real plan change — the frontend never sends this, and a
                # $0.00 audit row for it would be misleading noise.
                logger.info(
                    "proration: subscription %s — same plan, nothing to prorate",
                    subscription.id,
                )
                return None
            if from_plan.currency != to_plan.currency:
                # A net delta in a single currency field is meaningless across a
                # currency change. Skip (the swap still proceeds).
                logger.warning(
                    "proration: subscription %s — currency change %s->%s, skipped",
                    subscription.id,
                    from_plan.currency,
                    to_plan.currency,
                )
                return None

            result = ProrationService.calculate(
                from_price_cents=from_plan.price_cents,
                to_price_cents=to_plan.price_cents,
                currency=from_plan.currency,
                period_start=subscription.current_period_start,
                period_end=subscription.current_period_end,
                now=now,
            )
            with transaction.atomic():
                record = ProrationRecord.objects.create(
                    tenant_id=subscription.tenant_id,
                    subscription=subscription,
                    from_plan=from_plan,
                    to_plan=to_plan,
                    period_start=result.period_start,
                    period_end=result.period_end,
                    calculated_at=result.calculated_at,
                    amount_cents=result.net_amount_cents,
                    currency=result.currency,
                )
            logger.info(
                "proration: subscription %s %s->%s — recorded %s %+d (audit only, "
                "no charge)",
                subscription.id,
                from_plan.code,
                to_plan.code,
                record.currency,
                record.amount_cents,
            )
            return record
        except Exception:  # noqa: BLE001 — contract is "never raises", see docstring
            logger.exception(
                "proration: subscription %s (%s->%s) — calculation/record failed; "
                "the plan change still proceeds",
                subscription.id,
                getattr(from_plan, "code", "?"),
                getattr(to_plan, "code", "?"),
            )
            return None


# --- D8: reconciliation -------------------------------------------------------


@dataclass(frozen=True)
class ReconciledSubscription:
    """One subscription's outcome from a reconciliation pass."""

    external_subscription_id: str
    #: ReconciliationService.MATCH / DISCREPANCY / SKIPPED / UNAVAILABLE / ERROR
    outcome: str
    #: the `ReconciliationDiscrepancy.Category` value, when outcome == DISCREPANCY
    category: "str | None" = None
    #: `str(exc)` when outcome == ERROR
    error: "str | None" = None


@dataclass(frozen=True)
class ReconciliationSweepResult:
    """The outcome of one sweep — consumed identically by the
    `reconcile_subscriptions` management command and the
    `billing.reconcile_subscriptions` Celery task."""

    checked: list

    @property
    def total(self):
        return len(self.checked)

    @property
    def matched(self):
        return [c for c in self.checked if c.outcome == ReconciliationService.MATCH]

    @property
    def discrepancies(self):
        return [
            c for c in self.checked
            if c.outcome == ReconciliationService.DISCREPANCY
        ]

    @property
    def unavailable(self):
        return [
            c for c in self.checked
            if c.outcome == ReconciliationService.UNAVAILABLE
        ]

    @property
    def skipped(self):
        return [c for c in self.checked if c.outcome == ReconciliationService.SKIPPED]

    @property
    def errors(self):
        return [c for c in self.checked if c.outcome == ReconciliationService.ERROR]


class ReconciliationService:
    """
    Periodic, READ-ONLY cross-check of local `Subscription` status against the
    payment provider's reported status (docs/stage-d8-spec.md).

    Detection only. This service NEVER corrects local state, never transitions a
    subscription, and never writes anything back to the provider — the only
    write it performs is appending an immutable `ReconciliationDiscrepancy`
    audit row. Acting on drift is a separate, human decision (spec §1).

    Only STATUS is compared (spec §6):
      - period dates are a synthesized local placeholder for much of a
        subscription's life (D3/D4) — comparing them would be all false
        positives;
      - the provider plan id diverges by design, because `change_plan` swaps
        `Subscription.plan` locally with no gateway call (D6).

    Provider-response classification (spec §8):
      A. a state came back            -> compare it
      B. `fetch_subscription_state` returns None (provider disowns the id)
                                      -> a genuine discrepancy (PROVIDER_NOT_FOUND)
      C. `ProviderUnavailable` raised -> infra failure, NOT drift: logged,
                                         nothing recorded, sweep continues
    """

    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"
    SKIPPED = "SKIPPED"  # no external_subscription_id — nothing to look up
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"

    # Local Subscription.Status -> the normalized provider vocabulary, so both
    # sides of the comparison speak one language. TRIALING has no provider
    # analogue and a webhook-created subscription is essentially never left
    # TRIALING (the ACTIVATED that creates it immediately moves it to ACTIVE);
    # a trial is a live billing relationship, so it normalizes to ACTIVE.
    _LOCAL_STATUS = {
        Subscription.Status.TRIALING: ProviderSubscriptionStatus.ACTIVE,
        Subscription.Status.ACTIVE: ProviderSubscriptionStatus.ACTIVE,
        Subscription.Status.PAST_DUE: ProviderSubscriptionStatus.PAST_DUE,
        Subscription.Status.CANCELED: ProviderSubscriptionStatus.CANCELED,
    }

    @staticmethod
    def reconcile_subscription(subscription, *, now=None) -> "ReconciledSubscription":
        """
        Reconcile ONE subscription against the provider. Read-only against the
        provider AND against local state — nothing on the `Subscription` is
        touched. Appends a `ReconciliationDiscrepancy` iff drift is found;
        records NOTHING on a match or a provider failure. Never raises for a
        `ProviderUnavailable`.
        """
        now = now or timezone.now()
        eid = subscription.external_subscription_id
        if not eid:
            # Defensive: reconcile_all filters these out. A subscription with no
            # provider id was never provisioned there — nothing to compare.
            return ReconciledSubscription("", ReconciliationService.SKIPPED)

        try:
            state = get_gateway().fetch_subscription_state(eid)
        except ProviderUnavailable as exc:
            # Case C — infrastructure, not drift. Record nothing.
            logger.warning(
                "reconcile: subscription %s (%s) — provider unavailable: %s",
                subscription.id,
                eid,
                exc,
            )
            return ReconciledSubscription(eid, ReconciliationService.UNAVAILABLE)

        local = ReconciliationService._LOCAL_STATUS[subscription.status]

        # Case B — the provider explicitly disowns this id.
        if state is None:
            return ReconciliationService._record(
                subscription,
                ReconciliationDiscrepancy.Category.PROVIDER_NOT_FOUND,
                subscription.status,
                "",
                f"local {subscription.status} but the provider has no record of {eid}",
                now,
            )

        # Case A — compare status (the only compared field).
        if local == state.status:
            return ReconciledSubscription(eid, ReconciliationService.MATCH)

        # Local terminal (CANCELED) but the provider is not — it may still be
        # charging. Its own category, never folded into STATUS_MISMATCH and
        # never skipped; `provider_status` records which non-terminal state it
        # actually is (ACTIVE / PAST_DUE / PENDING / UNKNOWN).
        if local == ProviderSubscriptionStatus.CANCELED:
            category = (
                ReconciliationDiscrepancy.Category.LOCAL_CANCELED_PROVIDER_ACTIVE
            )
        else:
            category = ReconciliationDiscrepancy.Category.STATUS_MISMATCH

        return ReconciliationService._record(
            subscription,
            category,
            subscription.status,
            state.status,
            f"local {local} vs provider {state.status} (raw: {state.raw_status})",
            now,
        )

    @staticmethod
    def _record(
        subscription, category, local_status, provider_status, detail, now
    ) -> "ReconciledSubscription":
        """Append one immutable discrepancy row — the ONLY write this service
        performs — and describe the outcome."""
        ReconciliationDiscrepancy.objects.create(
            tenant_id=subscription.tenant_id,
            subscription=subscription,
            external_subscription_id=subscription.external_subscription_id,
            category=category,
            local_status=str(local_status),
            provider_status=str(provider_status),
            detail=detail,
            detected_at=now,
        )
        logger.info(
            "reconcile: subscription %s — %s (%s)",
            subscription.id,
            category,
            detail,
        )
        return ReconciledSubscription(
            subscription.external_subscription_id,
            ReconciliationService.DISCREPANCY,
            category=category,
        )

    @staticmethod
    def reconcile_all() -> "ReconciliationSweepResult":
        """
        Run `reconcile_subscription` over every `Subscription` that HAS an
        `external_subscription_id` — only those can be looked up at the
        provider. Locally-CANCELED subscriptions ARE included (a
        `local CANCELED / provider live` divergence is exactly what this stage
        exists to surface).

        A per-subscription exception is captured (logged, recorded on the
        result), never propagated — one bad subscription must not abort the
        sweep.

        The orchestration lives HERE, once: the `reconcile_subscriptions`
        management command and the `billing.reconcile_subscriptions` Celery task
        are both thin callers of this (docs/stage-d7-spec.md §5 pattern).
        """
        checked = []
        subs = (
            Subscription.objects.exclude(external_subscription_id__isnull=True)
            .exclude(external_subscription_id="")
            .select_related("tenant")
            .order_by("created_at")
        )
        for sub in subs:
            try:
                checked.append(
                    ReconciliationService.reconcile_subscription(sub)
                )
            except Exception as exc:  # noqa: BLE001 — one bad row can't abort the sweep
                logger.exception(
                    "reconcile sweep: subscription %s (%s) failed",
                    sub.id,
                    sub.external_subscription_id,
                )
                checked.append(
                    ReconciledSubscription(
                        sub.external_subscription_id or "",
                        ReconciliationService.ERROR,
                        error=str(exc),
                    )
                )
        return ReconciliationSweepResult(checked)

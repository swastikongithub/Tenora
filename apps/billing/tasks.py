"""
Celery tasks (docs/stage-d7-spec.md, extended by the Phase 6 worker/scheduler
work — docs/worker-scheduler-operations.md). These are the SCHEDULED entry
points — the beat schedule in `config/celery.py` fires them.

They are NOT wrappers around the management-command layer. Each task calls the
same service-layer method the corresponding `manage.py` command calls:

    Celery task ───────┐
                       ├──> WebhookProcessingService.process_pending()
    management command ┘         / UsageMeteringService.snapshot_all_subscribed()
                                 / ReconciliationService.reconcile_all()

The management commands stay fully usable as manual entry points (on-demand
runs, debugging, recovery); the orchestration they share lives once, in the
service. Phase 6 adds three things AROUND that call and nothing inside it:

  1. An advisory lock, so two workers (or a worker and a manual command) cannot
     sweep the same backlog at the same time. See apps/billing/locks.py.
  2. Bounded retry with backoff for an INFRASTRUCTURE failure — a task that
     raises at all. Per-row failures are already captured on each sweep's
     result and must not trigger a retry of the whole sweep.
  3. Observational audit, written only when a run changed something or failed.
     A silent run writes nothing; see `_record_run`.

Every sweep is idempotent by construction (a unique constraint or a state
check, never a convention), so a retry, an overlapping schedule, or a manual
run racing a scheduled one is safe — the lock is about waste, not correctness.

The AuditService import is the one place `apps.billing` reaches into
`apps.platform`, and it is deliberate: this module is the operational EDGE, not
billing domain logic. The domain services it calls remain entirely unaware of
the platform app, which is the layering rule that matters — the audit trail of
operational activity belongs to the operator domain, and duplicating an audit
model inside billing to avoid one import would be the worse trade.
"""

import logging

from celery import shared_task

from apps.billing.locks import advisory_lock
from apps.billing.services import (
    ReconciliationService,
    UsageMeteringService,
    WebhookProcessingService,
)
from apps.platform.services import AuditService

logger = logging.getLogger(__name__)

#: Retry policy for an INFRASTRUCTURE failure (database unreachable, broker
#: dropped mid-run) — the only way these tasks raise at all, since every sweep
#: catches its own per-row failures and reports them on its result. Bounded and
#: backed off: a sweep that cannot run now will be run again by the schedule
#: anyway, so retrying forever buys nothing and costs a worker slot.
RETRY_POLICY = {
    "autoretry_for": (Exception,),
    "retry_backoff": True,
    "retry_backoff_max": 300,
    "retry_jitter": True,
    "max_retries": 3,
}

#: Every task result carries this flag: True when another run already held the
#: lock and this one did nothing. Named `lock_skipped`, not `skipped`, because
#: the usage result already has a `skipped` key meaning "tenants skipped" — two
#: different facts that must not share a name. The existing count keys are
#: untouched, so a caller reading them sees exactly what it saw before.
def _lock_skipped(**counts):
    return {"lock_skipped": True, **{k: 0 for k in counts}}


def _record_run(*, action, summary, metadata, changed):
    """
    Observational audit for one scheduled run — best-effort by contract
    (AuditService.record_observational never raises), and written ONLY when
    `changed` is true or the run failed.

    A five-minute sweep that found nothing pending runs 288 times a day. Those
    rows would bury the ones that matter in the very log an operator opens to
    find them, so a quiet run records nothing and says so only in the
    application log. This is the spec's "distinguish critical operator-visible
    events from observational operational events", applied one level further:
    not every observational event is worth a row.

    `actor` is None — the model's FK is nullable precisely because an action
    can have no human behind it, and inventing a synthetic "system user" would
    put a fake account in the audit trail.
    """
    if not changed:
        return
    AuditService.record_observational(
        actor=None,
        action=action,
        target_type="ScheduledTask",
        target_id=action,
        summary=summary,
        metadata=metadata,
    )


@shared_task(name="billing.process_webhook_events", **RETRY_POLICY)
def process_webhook_events():
    """Scheduled webhook retry sweep — the mechanism D4's `DEFERRED` events and
    D3's best-effort inline processing rely on. Runs every 5 minutes (beat).

    Idempotent: `WebhookEvent.external_event_id` is unique, and processing sets
    `processed=True` in the same transaction as the state change it applies, so
    a re-run has nothing left to do for an event already handled."""
    with advisory_lock("billing.process_webhook_events") as acquired:
        if not acquired:
            return _lock_skipped(total=0, processed=0, deferred=0, failed=0)

        result = WebhookProcessingService.process_pending()
        body = {
            "total": result.total,
            "processed": len(result.processed),
            "deferred": len(result.deferred),
            "failed": len(result.failed),
        }
        logger.info(
            "webhook sweep task: %d processed, %d deferred, %d failed (of %d)",
            body["processed"],
            body["deferred"],
            body["failed"],
            body["total"],
        )
        _record_run(
            action="scheduled.webhook_sweep",
            summary=(
                f"Scheduled webhook sweep: {body['total']} checked, "
                f"{body['processed']} processed, {body['deferred']} deferred, "
                f"{body['failed']} failed"
            ),
            metadata=body,
            # A run that processed nothing and failed nothing changed nothing,
            # even if rows were deferred again — a deferral is the steady
            # state for an event still waiting on its subscription.
            changed=bool(body["processed"] or body["failed"]),
        )
        return {"lock_skipped": False, **body}


@shared_task(name="billing.meter_usage", **RETRY_POLICY)
def meter_usage():
    """Scheduled per-tenant usage snapshot (D5). Runs daily (beat); idempotent
    via the `unique_usage_snapshot` constraint, so an extra run is a no-op."""
    with advisory_lock("billing.meter_usage") as acquired:
        if not acquired:
            return _lock_skipped(total=0, created=0, existing=0, skipped=0)

        result = UsageMeteringService.snapshot_all_subscribed()
        body = {
            "total": result.total,
            "created": len(result.records),
            "existing": result.existing,
            "skipped": result.skipped,
        }
        logger.info(
            "usage snapshot task: %d new, %d already recorded, %d skipped (of %d)",
            body["created"],
            body["existing"],
            body["skipped"],
            body["total"],
        )
        _record_run(
            action="scheduled.usage_snapshot",
            summary=(
                f"Scheduled usage snapshot: {body['total']} tenants, "
                f"{body['created']} new snapshots"
            ),
            metadata=body,
            changed=bool(body["created"]),
        )
        return {"lock_skipped": False, **body}


@shared_task(name="billing.reconcile_subscriptions", **RETRY_POLICY)
def reconcile_subscriptions():
    """Scheduled reconciliation sweep (D8) — read-only cross-check of local
    subscription status against the provider. Records drift as
    `ReconciliationDiscrepancy` rows; corrects nothing. Runs hourly (beat); a
    `ProviderUnavailable` for one subscription is logged and skipped, never
    mistaken for drift."""
    with advisory_lock("billing.reconcile_subscriptions") as acquired:
        if not acquired:
            return _lock_skipped(
                total=0,
                matched=0,
                discrepancies=0,
                unavailable=0,
                skipped=0,
                errors=0,
            )

        result = ReconciliationService.reconcile_all()
        body = {
            "total": result.total,
            "matched": len(result.matched),
            "discrepancies": len(result.discrepancies),
            "unavailable": len(result.unavailable),
            "skipped": len(result.skipped),
            "errors": len(result.errors),
        }
        logger.info(
            "reconcile sweep task: %d matched, %d discrepancies, %d unavailable, "
            "%d skipped, %d errors (of %d)",
            body["matched"],
            body["discrepancies"],
            body["unavailable"],
            body["skipped"],
            body["errors"],
            body["total"],
        )
        _record_run(
            action="scheduled.reconciliation_sweep",
            summary=(
                f"Scheduled reconciliation sweep: {body['total']} checked, "
                f"{body['discrepancies']} discrepancies found"
            ),
            metadata=body,
            # Drift found, a provider that could not be reached, or a row that
            # errored — all three are worth an operator's attention. A clean
            # sweep where everything matched is not.
            changed=bool(
                body["discrepancies"] or body["unavailable"] or body["errors"]
            ),
        )
        return {"lock_skipped": False, **body}

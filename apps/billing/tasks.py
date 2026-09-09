"""
Celery tasks (docs/stage-d7-spec.md). These are the SCHEDULED entry points — the
beat schedule in `config/celery.py` fires them.

They are NOT wrappers around the management-command layer. Each task calls the
same service-layer method the corresponding `manage.py` command calls:

    Celery task ───────┐
                       ├──> WebhookProcessingService.process_pending()
    management command ┘         / UsageMeteringService.snapshot_all_subscribed()

The management commands stay fully usable as manual entry points (on-demand runs,
debugging, recovery); the orchestration they share lives once, in the service.
"""

import logging

from celery import shared_task

from apps.billing.services import (
    ReconciliationService,
    UsageMeteringService,
    WebhookProcessingService,
)

logger = logging.getLogger(__name__)


@shared_task(name="billing.process_webhook_events")
def process_webhook_events():
    """Scheduled webhook retry sweep — the mechanism D4's `DEFERRED` events and
    D3's best-effort inline processing rely on. Runs every 5 minutes (beat)."""
    result = WebhookProcessingService.process_pending()
    logger.info(
        "webhook sweep task: %d processed, %d deferred, %d failed (of %d)",
        len(result.processed),
        len(result.deferred),
        len(result.failed),
        result.total,
    )
    return {
        "total": result.total,
        "processed": len(result.processed),
        "deferred": len(result.deferred),
        "failed": len(result.failed),
    }


@shared_task(name="billing.meter_usage")
def meter_usage():
    """Scheduled per-tenant usage snapshot (D5). Runs daily (beat); idempotent
    via the `unique_usage_snapshot` constraint, so an extra run is a no-op."""
    result = UsageMeteringService.snapshot_all_subscribed()
    logger.info(
        "usage snapshot task: %d new, %d already recorded, %d skipped (of %d)",
        len(result.records),
        result.existing,
        result.skipped,
        result.total,
    )
    return {
        "total": result.total,
        "created": len(result.records),
        "existing": result.existing,
        "skipped": result.skipped,
    }


@shared_task(name="billing.reconcile_subscriptions")
def reconcile_subscriptions():
    """Scheduled reconciliation sweep (D8) — read-only cross-check of local
    subscription status against the provider. Records drift as
    `ReconciliationDiscrepancy` rows; corrects nothing. Runs hourly (beat); a
    `ProviderUnavailable` for one subscription is logged and skipped, never
    mistaken for drift."""
    result = ReconciliationService.reconcile_all()
    logger.info(
        "reconcile sweep task: %d matched, %d discrepancies, %d unavailable, "
        "%d skipped, %d errors (of %d)",
        len(result.matched),
        len(result.discrepancies),
        len(result.unavailable),
        len(result.skipped),
        len(result.errors),
        result.total,
    )
    return {
        "total": result.total,
        "matched": len(result.matched),
        "discrepancies": len(result.discrepancies),
        "unavailable": len(result.unavailable),
        "skipped": len(result.skipped),
        "errors": len(result.errors),
    }

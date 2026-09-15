"""Scheduled entry point for property billing reminders (beat: daily, see
`config/celery.py`). Calls the same function as `manage.py
send_billing_reminders`; idempotent through notification dedupe keys, so an
overlapping or retried run notifies nobody twice. Billing state is never changed
by this task — manual workflow stays fully usable without a worker.

Wrapped the same way as the subscription sweeps in `apps.billing.tasks`
(docs/worker-scheduler-operations.md): a cross-process advisory lock against
wasted overlapping runs, bounded retry for an infrastructure failure, and an
observational audit row only when the run actually notified someone. Only the
generic lock helper is imported from `apps.billing` — this module stays clear of
the subscription domain.
"""

import logging

from celery import shared_task

from apps.billing.locks import advisory_lock
from apps.platform.services import AuditService
from apps.properties.reminders import send_billing_reminders

logger = logging.getLogger(__name__)

#: Same bounded policy as the subscription sweeps (apps.billing.tasks.RETRY_POLICY);
#: a test pins that the two stay equal.
RETRY_POLICY = {
    "autoretry_for": (Exception,),
    "retry_backoff": True,
    "retry_backoff_max": 300,
    "retry_jitter": True,
    "max_retries": 3,
}

LOCK_NAME = "properties.send_billing_reminders"


@shared_task(name="properties.send_billing_reminders", **RETRY_POLICY)
def send_billing_reminders_task():
    with advisory_lock(LOCK_NAME) as acquired:
        if not acquired:
            return {"lock_skipped": True, "due_soon": 0, "overdue": 0, "owner_summaries": 0, "cycle_incomplete": 0}

        body = send_billing_reminders().as_dict()
        logger.info(
            "billing reminders task: %d due soon, %d overdue, %d owner summaries, %d cycle reminders",
            body["due_soon"],
            body["overdue"],
            body["owner_summaries"],
            body["cycle_incomplete"],
        )
        if any(body.values()):
            AuditService.record_observational(
                actor=None,
                action="scheduled.billing_reminders",
                target_type="ScheduledTask",
                target_id="scheduled.billing_reminders",
                summary=(
                    f"Scheduled billing reminders: {body['due_soon']} due soon, "
                    f"{body['overdue']} overdue, {body['owner_summaries']} owner summaries, "
                    f"{body['cycle_incomplete']} cycle reminders"
                ),
                metadata=body,
            )
        return {"lock_skipped": False, **body}

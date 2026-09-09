"""
Celery application (docs/stage-d7-spec.md).

Background-job infrastructure for the automation D1/D4 and D5 deliberately
deferred to this stage — the webhook deferred-event retry sweep and periodic
usage snapshotting. The scheduled tasks (`apps/billing/tasks.py`) are thin
callers of the same service-layer methods the management commands invoke; this
module only wires Celery up and owns the beat schedule.

The broker URL and test-eager config live in `config/settings.py` (read here via
`config_from_object(..., namespace="CELERY")`). The automated test suite runs
tasks in-process (`CELERY_TASK_ALWAYS_EAGER`) and never needs a real broker.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
# All Celery settings come from Django settings, `CELERY_`-prefixed.
app.config_from_object("django.conf:settings", namespace="CELERY")
# Discovers `tasks.py` in each installed app (apps.billing.tasks).
app.autodiscover_tasks()

app.conf.beat_schedule = {
    # The webhook retry sweep D4's DEFERRED events depend on. Frequent so a
    # CHARGED that arrived before its ACTIVATED resolves within minutes of the
    # ACTIVATED landing — far inside D4's 24h bound. An idle run is a single
    # "nothing pending" query.
    "webhook-retry-sweep": {
        "task": "billing.process_webhook_events",
        "schedule": crontab(minute="*/5"),
    },
    # Periodic usage snapshotting (D5). Billing periods are ~30 days, so one
    # snapshot per period is the intent; daily gives a comfortable margin and
    # D5's unique_usage_snapshot constraint makes an extra run a harmless no-op.
    "daily-usage-snapshot": {
        "task": "billing.meter_usage",
        "schedule": crontab(hour=3, minute=0),  # 03:00 UTC
    },
    # D8 reconciliation sweep — a safety net for drift the webhook pipeline
    # missed entirely (an event that never arrived). The 5-minute webhook sweep
    # already covers "arrived but unprocessed"; a subscription the provider
    # changed an hour ago is a real problem but not a 5-minute-SLA one. One
    # read-only `subscription.fetch` per provider-linked subscription per hour.
    "reconciliation-sweep": {
        "task": "billing.reconcile_subscriptions",
        "schedule": crontab(minute=0),  # top of every hour
    },
}

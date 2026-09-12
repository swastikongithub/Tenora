# Worker & Scheduler Operations

Operational reference for Tenora's background jobs — what runs, how often,
what makes each one safe to run twice, and what has to exist in an environment
before any of it actually executes.

This document records how the deployed system behaves. It is not a design
proposal, and it deliberately does not claim a capability the current hosting
plan does not have (see §5).

---

## 1. The three scheduled operations

All three are defined in `apps/billing/tasks.py` and scheduled by the beat
configuration in `config/celery.py`. Each is a thin caller of the same
service-layer method the matching `manage.py` command invokes — the
orchestration lives once, in the service.

| Task name | Service method | Cadence | What it does |
|---|---|---|---|
| `billing.process_webhook_events` | `WebhookProcessingService.process_pending()` | every 5 minutes | Applies the effect of every webhook event still marked unprocessed — events the inline handler could not apply, and events deferred because they arrived before the subscription they refer to. |
| `billing.reconcile_subscriptions` | `ReconciliationService.reconcile_all()` | hourly, on the hour | Read-only cross-check of local subscription status against the payment gateway. Records drift as discrepancy rows; corrects nothing. |
| `billing.meter_usage` | `UsageMeteringService.snapshot_all_subscribed()` | daily, 03:00 UTC | Snapshots each subscribed tenant's metered quantity for the current billing period. |

The cadences are chosen from what each job is actually protecting against, not
from a uniform default. The webhook sweep is frequent because a deferred event
resolves within minutes of the event it was waiting for. Reconciliation is
hourly because a subscription the provider changed an hour ago is a real
problem but not a five-minute one, and each run costs one provider read per
provider-linked subscription. Usage is daily because billing periods are
roughly thirty days and one snapshot per period is the intent — daily is
margin, and an extra run is a no-op.

---

## 2. Why each one is safe to run twice

Retries, overlapping schedules, and a manual run racing a scheduled one all
reduce to the same question: what happens when the same work executes more than
once? In every case the answer is a database constraint or a state check, not
a convention.

- **Webhook sweep.** `WebhookEvent.external_event_id` is unique, so a
  redelivered gateway event is absorbed by a constraint collision rather than a
  check-then-insert. Processing sets `processed=True` in the same transaction as
  the state change it applies, so a re-run sees nothing left to do. The
  out-of-order guard (`Subscription.last_event_at`) additionally refuses an
  event older than the last one already applied, so a late redelivery cannot
  move state backwards.
- **Usage snapshot.** `UNIQUE(tenant, metric, period_start, period_end)` is the
  idempotency key. A second run for an already-recorded period collides and is
  a no-op; the service never updates an existing row.
- **Reconciliation.** Read-only against the provider and append-only locally. A
  second run that still sees the same drift writes a second discrepancy row
  with a later detection time — by design, since the sequence of rows is the
  record of how long the drift has persisted.

Partial completion is safe for the same reason: each sweep commits per row and
captures per-row failures on its result rather than aborting, so a run that
dies halfway leaves the rows it finished committed and the rest still pending
for the next run.

---

## 3. Overlap protection

Idempotency makes a repeated run harmless, but it does not make two
simultaneous runs useful — two workers sweeping the same backlog will mostly
race each other for rows and waste provider calls.

Each scheduled task therefore takes a **PostgreSQL session-level advisory
lock** for its own name before doing any work, and releases it in a `finally`.
A task that cannot take the lock returns immediately, reporting that it was
skipped. The lock is held in the database, not in process memory, so it works
across workers, across containers, and across a scheduled run overlapping a
manual `manage.py` invocation of the same sweep.

Advisory locks are released automatically if the connection dies, so a worker
killed mid-sweep does not leave the job wedged — the next run acquires the lock
normally.

The lock covers overlap only. It is not a correctness mechanism: every
guarantee in §2 holds with or without it, which is why a skipped run is
reported as ordinary output rather than an error.

---

## 4. Failure handling and visibility

A per-row failure is captured on the sweep's result and logged; it never aborts
the run. That is existing service behaviour and is unchanged.

A failure of the *task itself* — the database unreachable, the broker dropping
mid-run — is infrastructure, not data. Those retry with exponential backoff and
a bounded attempt count, then give up and surface. A task that gives up does not
disappear silently: it records an operational audit entry an operator can see in
the audit log.

Scheduled runs write to the audit log **only when there is something to say** —
a run that changed state, or a run that failed. An idle five-minute sweep that
found nothing pending writes nothing, because 288 rows a day saying "nothing
happened" would bury the rows that matter in the one log an operator reads to
find them. These entries are observational, never critical: they describe
operational activity, not an operator's decision. They carry counts and the
exception class name, never a provider payload, a credential, or a customer
identifier.

---

## 5. What an environment needs before any of this runs

Nothing in §1 executes unless **three** things are deployed and running:

1. **Redis** (or another Celery broker), reachable at `CELERY_BROKER_URL`.
2. **A Celery worker process** — `celery -A config worker`.
3. **A Celery beat process** — `celery -A config beat`.

Django itself does not run scheduled tasks. A deployment with only the web
service has the task code installed and no path by which any of it fires.

**Local / Docker.** `docker-compose.yml` defines all three (`redis`, `worker`,
`beat`), so `docker compose up` gives a complete, working scheduler.

**Current production (Render Free).** The plan runs the web service only. There
is no worker and no beat process, therefore **no scheduled task currently
executes in production.** This is a deployment gap, not a code gap, and it is
stated here rather than implied by silence.

Until a worker and scheduler are deployed, the three sweeps run through the
**Fallback Sweep Controls** in the operator console (`/admin/webhooks`,
`/admin/reconciliation`), which call the same service methods the scheduled
tasks call. Those controls are throttled and audited. They are kept — not
removed — after a scheduler is deployed: they become a manual override rather
than the primary mechanism, and the spec's sequencing is explicit that they
stay available until the scheduled path has been validated in production.

The same endpoints are also the natural integration point for an external
scheduler: any timed caller holding an operator token can drive them on a
schedule without a worker existing at all.

**Automated tests.** `CELERY_TASK_ALWAYS_EAGER` is on under `manage.py test`,
so tasks execute in-process and the suite never needs a broker.

---

## 6. Running them by hand

Every scheduled operation has a management command, usable at any time for an
on-demand run, a recovery, or debugging:

```
python manage.py process_webhook_events
python manage.py reconcile_subscriptions
python manage.py meter_usage
```

These share the service methods with the tasks, so a manual run and a scheduled
run do the same thing — and, because of §3, cannot collide with one.

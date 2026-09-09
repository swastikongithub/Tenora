# Claude Code Implementation Specification — Stage D7: Celery Background Jobs

**Scope:** add real background-job infrastructure (Celery + a broker) and
schedule the automation that D1/D4 and D5 already deliberately deferred
here - the webhook deferred-event retry sweep, and periodic usage
snapshotting. This is mostly wiring scheduling on top of already-correct,
already-tested service logic, not inventing new domain behavior.

**Not in scope:** D8 (reconciliation - will use this same infrastructure,
but isn't built in this stage), any change to D3's synchronous inline
webhook-processing design unless section 2's investigation genuinely
warrants it, any live-provider verification.

---

## 0. New local-dev prerequisite: a message broker

Celery needs a broker. Redis is the standard, low-friction choice -
check whether it's already installed/running locally; if not, this is a
new prerequisite, same category as Postgres was in Stage A. For
automated tests, Celery should run in eager mode (tasks execute
synchronously in the test process) so the test suite never needs a real
broker running - only real local development and the manual
verification step need Redis actually up.

## 1. Objective

Three things in this codebase already have working, tested logic and
are explicitly waiting for real scheduling:

- D1/D4's `process_webhook_events` management command - the deferred-
  retry mechanism `DEFERRED` events (D4) depend on to eventually resolve
  within their bounded retry window.
- D5's `meter_usage` management command - periodic usage snapshotting.

This stage should not reimplement any of this logic. Celery tasks
should be thin wrappers around the exact same service-layer calls the
management commands already make - a scheduled trigger on top of
already-correct code, not a second implementation of the same behavior.

Open question — investigate before deciding: should D3's synchronous
inline webhook processing move to a Celery task now that the
infrastructure exists? My recommendation: no, leave it as-is. D3's
design already satisfies its correctness requirement (the HTTP response
never depends on processing succeeding) without needing Celery at all -
moving it to an async task would improve request latency marginally but
isn't fixing anything broken, and changing already-tested, working code
without a clear necessity risks the same "why touch what isn't broken"
mistake this project has avoided elsewhere. Verify this reasoning holds
against the current code, but don't change D3's design unless
investigation surfaces a real problem with leaving it synchronous.

## 2. Inspect Before Implementing

```
CLAUDE.md
apps/billing/management/commands/process_webhook_events.py,
meter_usage.py                         - the exact logic being wrapped
                                          in scheduled tasks, not
                                          reimplemented
apps/billing/services.py               - WebhookProcessingService,
                                          UsageMeteringService - confirm
                                          the exact methods to call
config/settings.py                     - where broker configuration
                                          should be added, following
                                          existing env-var patterns
docker-compose.yml                     - the existing service pattern
                                          (db/backend/frontend) to
                                          extend with redis/worker/beat
                                          services
```

Current state: D1-D6 complete and committed. Backend 260/260.

## 3. Existing Functionality That Must Not Change

- The management commands themselves stay working as manual-trigger
  tools (useful for on-demand runs, debugging, and recovery) - Celery
  adds scheduling on top, it doesn't replace the manual path.
- D3's webhook-processing behavior - unchanged unless section 1's
  investigation genuinely warrants a change (not expected).
- All existing tests must still pass, and must not require a real broker
  to run.

## 4. Required Changes

### 4.1 Celery setup

Standard Django+Celery wiring: a `celery.py` app configuration, broker
URL from environment (`CELERY_BROKER_URL`, following the existing
`.env.example` pattern), celery beat for scheduling.

### 4.2 Two scheduled tasks — thin wrappers, not reimplementations

- A periodic task calling the same logic `process_webhook_events`
  already runs - a reasonable interval (a few minutes; deferred events
  should resolve well within D4's 24-hour bound if the sweep runs
  frequently).
- A periodic task calling the same logic `meter_usage` already runs - a
  reasonable interval (daily is more than sufficient given billing
  periods are typically a month; idempotent regardless via D5's
  uniqueness constraint, so an overly-frequent run is still safe, just
  unnecessary).

### 4.3 Docker integration

Extend `docker-compose.yml` with a redis service and worker/beat
services, following the exact patterns already established for the
backend service (health checks, environment variables, etc.) - this
keeps the "one command runs everything" property Docker packaging
already delivered, now including the background jobs.

### 4.4 Test configuration

Celery's eager-execution mode enabled in test settings, so the existing
and new test suites never require a real Redis instance.

## 5. Files Likely Affected

```
new:      config/celery.py (or similar - the Celery app config)
          the two scheduled task definitions
          tests for the tasks (calling them directly, not through a
                                real broker)
modified: config/settings.py (broker config, eager mode for tests)
          docker-compose.yml (redis + worker + beat services)
          .env.example (CELERY_BROKER_URL)
          requirements/base.txt (+celery, +redis client library)
```

No frontend file.

## 6. Business Rules

No new business logic - this stage schedules existing, correct logic.

## 7. Security Requirements

No new external-facing surface - Celery/Redis are internal
infrastructure, not exposed endpoints.

## 8. Edge Cases

- A scheduled task running while a manual command invocation of the
  same logic is also in flight - verify this can't cause a problem
  (the underlying service methods are already idempotent per D1/D4/D5's
  own guarantees, so this should be safe by construction - confirm,
  don't just assume).
- No real broker available during a normal `manage.py test` run - must
  not fail or hang; eager mode should make this a non-issue, verify it
  actually is.

## 9. Tests Required

- Both scheduled tasks, called directly (not through a real broker),
  correctly invoke the same underlying service logic the existing
  management commands use - and produce the same observable effects
  (a deferred event getting retried, a usage snapshot getting recorded).
- The test suite runs without requiring a real Redis instance.

## 10. Acceptance Criteria

1. `manage.py test` - full count reported (baseline 260), no real broker
   required.
2. Report: the resolved answer to section 1's open question (with
   reasoning), confirmation the two tasks are thin wrappers around
   existing service logic (not reimplementations), and the exact
   scheduling intervals chosen and why.
3. Manual verification: with a real Redis running locally (or via the
   updated `docker-compose.yml`), start a worker and beat scheduler,
   confirm both scheduled tasks actually fire and produce correct,
   observable effects against real (or synthetic, per prior stages'
   pattern) data.
4. `git status` - no unrelated file changed.

## 11. Must NOT Do

- Do not reimplement the webhook-retry or usage-snapshot logic - call
  the existing service methods.
- Do not change D3's synchronous inline processing unless section 1's
  investigation genuinely warrants it - don't change it by default.
- Do not require a real broker for the automated test suite.
- Do not build D8.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code - expect
the plan to include a resolved answer to section 1's open question.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-d7-spec.md, then inspect the repository.
Produce an implementation plan - including your proposed answer to
section 1's open design question - and wait for my approval before
writing any code.

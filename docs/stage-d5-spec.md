# Claude Code Implementation Specification — Stage D5: Usage Metering

**Scope:** track real, honest usage data per tenant per billing period -
the foundation D6 (proration) and any future usage-based billing would
build on. Pure domain logic, no live provider dependency, fully
buildable and testable now.

**Not in scope:** proration math (D6), Celery/automatic scheduling (D7 -
this stage builds the recording mechanism and a manual trigger, not the
automation), any overage-billing or quota-enforcement logic, any
frontend UI.

## 0. Buildable and testable now

No live provider needed - this is pure domain/database logic.

## 1. Objective

The central constraint, stated up front: **no usage metric may be
invented or fabricated.** This app currently has no real metered
feature - no API rate limiting, no storage tracking, nothing that
naturally generates usage events. Building "usage metering" without a
real thing being metered would mean either fabricating events (violates
the project's oldest rule) or building an elaborate abstraction with
nothing genuine underneath it.

Investigate and confirm, don't assume: what should be metered. My
recommendation, to validate: **active member count**, snapshotted per
billing period. This is a genuinely real, already-tracked domain
resource (Membership rows are real), and per-seat billing is a
completely standard, realistic SaaS pattern - not a contrived metric
invented to have something to demo. If investigation surfaces a better
real candidate already present in the domain, propose it instead - but
don't invent a synthetic one either way.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md            - Stage D's original outline for
                                          what D5 was meant to cover
apps/tenants/models.py                 - Membership - the real resource
                                          being counted, if the
                                          recommendation above holds
apps/billing/models.py                 - Subscription -
                                          current_period_start/
                                          current_period_end, the natural
                                          period boundary usage should be
                                          tied to
apps/billing/services.py               - existing service-layer
                                          conventions to follow
```

Current state: D1-D4 complete and committed. Backend 222/222.

## 3. Existing Functionality That Must Not Change

- No change to Subscription's state machine, the gateway adapter interface, or any existing webhook-processing logic.
- All existing tests must still pass.

## 4. Required Changes

### 4.1 UsageRecord model

Tenant-scoped (TenantScopedManager, consistent with Membership).
Fields: `tenant` (FK), `metric` (a string identifier - e.g.
`"active_members"` - chosen for extensibility, not because multiple
metrics are being built now), `quantity`, `period_start`, `period_end`,
`recorded_at` (auto). A uniqueness constraint on
`(tenant, metric, period_start, period_end)` - the same idempotency
principle already proven for WebhookEvent, applied here via a natural
business key instead of an external event ID, so re-running a snapshot
for a period that's already recorded is a safe no-op, not a duplicate.

### 4.2 Recording mechanism

A service method (e.g.
`UsageMeteringService.record_snapshot(tenant, metric="active_members")`)
that: determines the relevant billing period from the tenant's current
Subscription (if one exists - if not, skip and log, don't invent a
calendar-based fallback period for a tenant with no real subscription),
counts the real current Membership rows for that tenant, and records
a UsageRecord - idempotent via the uniqueness constraint (section 4.1),
not just application-level checking.

### 4.3 Manual trigger — a management command, not automatic scheduling

A command that snapshots usage for all tenants with an active
subscription - the same "manual trigger now, Celery automates it later"
pattern already used for `sync_razorpay_plans` and
`process_webhook_events`. Do not attempt to build real scheduling in
this stage - that's D7's job.

### 4.4 A query/aggregation method

A way to retrieve a tenant's recorded usage for a given period (or its
current period) - this is what D6 (proration) and any future billing
logic would consume. Keep this simple - a straightforward query, not a
speculative reporting/analytics layer.

## 5. Files Likely Affected

```
new:      apps/billing/migrations/... (UsageRecord model)
          the recording service + query method
          the management command
          tests for all of the above
modified: apps/billing/models.py
```

No frontend file - this stage is backend domain logic only.

## 6. Business Rules

- No fabricated usage metric - only real, already-tracked domain data.
- A usage snapshot for a given tenant/metric/period is recorded at most once - the uniqueness constraint is the real guarantee.
- A tenant with no active subscription has no meaningful billing period to snapshot against - skipped, not given an invented one.

## 7. Security Requirements

No new external surface - this is internal domain logic.

## 8. Edge Cases

- Running the snapshot command twice in the same period - no duplicate UsageRecord rows (proven by the DB constraint, tested explicitly).
- A tenant with zero members beyond its OWNER - a real, valid quantity of 1, not an edge case to special-case away.
- A tenant whose subscription changed plans or was cancelled mid-period - verify the snapshot logic behaves sensibly (uses whatever period is currently on the Subscription at snapshot time; don't over-engineer historical period reconstruction in this stage).

## 9. Tests Required

- `record_snapshot` correctly counts real Membership rows and stores the correct period boundaries from the tenant's Subscription.
- Idempotency: recording twice for the same period produces one row, proven against the DB constraint (an IntegrityError-based test, same shape as this project's other uniqueness-guarantee tests).
- A tenant with no subscription is skipped, not given a fabricated period.
- The management command snapshots all eligible tenants correctly.
- The query/aggregation method returns correct data for a given period.

## 10. Acceptance Criteria

1. `manage.py test` - full count reported (baseline 222).
2. `manage.py check`, `makemigrations --check` - clean.
3. Report: confirmation of what metric was chosen and why (section 1), and that it traces to real, already-tracked domain data - not invented.
4. `git status` - no unrelated file changed.

## 11. Must NOT Do

- Do not invent or fabricate a usage metric with no real basis in the existing domain.
- Do not build proration/overage-billing math - that's D6.
- Do not build real scheduling/automation - that's D7; a management command is sufficient for this stage.
- Do not build any frontend UI.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code - expect
the plan to confirm or propose an alternative to section 1's metric
recommendation before proceeding.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-d5-spec.md, then inspect the repository.
Produce an implementation plan - including your proposed answer to
section 1's open question about what should be metered - and wait for
my approval before writing any code.

# Claude Code Implementation Specification — Stage D6: Proration

**Scope:** correctly calculate and record the prorated amount for a
mid-cycle plan change - real, standard billing math, applied honestly.
No real charge or refund happens as a result of this stage - there
is no gateway mechanism in this project to collect or issue a mid-cycle
delta payment (Stage D's checkout flow only ever handles a new
subscription's initial payment). This is domain calculation and an
audit record, not a payment action.

**Not in scope:** any real charge/refund/gateway call, D7 (Celery), D8
(reconciliation), any frontend UI showing the proration amount (unless
investigation finds it's trivial to surface - not required).

## 0. Buildable and testable now

Pure domain math and a real, already-existing trigger point
(`change_plan`) - no live provider needed.

## 1. Objective

Honesty constraint, stated up front, same discipline as the
Cancellation UI's copy: this stage computes what a customer would owe
or be credited for a mid-cycle plan change - a real, standard SaaS
billing calculation - and records it as an audit entry. It does NOT
charge anything, refund anything, or call Razorpay. If this is ever
wired into a real collection mechanism, that's later, separate work,
requiring real gateway capability this project doesn't have yet.

Investigate before assuming: does Razorpay's Subscriptions API even
support changing an existing subscription's plan, or does a real plan
change typically require creating a new subscription? This shapes how
honestly `change_plan`'s current behavior (locally swapping
`Subscription.plan` with no gateway involvement at all) should be
described - verify against current docs, don't assume either way, and
note the finding in the report even if it doesn't change this stage's
scope.

## 2. Inspect Before Implementing — open design question

```
CLAUDE.md
apps/billing/services.py               - SubscriptionService.change_plan
                                          (or wherever plan-change logic
                                          currently lives, post-D2's
                                          refactors) - confirm its exact
                                          current behavior before
                                          assuming anything
apps/billing/views.py                  - CurrentSubscriptionView.patch -
                                          confirm plan-change is still
                                          reachable via this path and
                                          untouched by D2's removal of
                                          the POST/create path
apps/billing/models.py                 - Subscription (period fields),
                                          Plan (price_cents, currency)
frontend/src/routes/SubscriptionPage.tsx,
ChangePlanConfirmModal.tsx (or equivalent) - the real, live client flow
                                          this stage's calculation would
                                          attach to, if wired in
```

Open question: should this wire into the live `change_plan` flow now,
or stay a standalone, tested calculation service for now?
Recommendation to validate: wire it in, because unlike D5 (which had
no existing trigger and needed a synthetic manual-command path),
`change_plan` is a real, already-tested, currently-working client
action - there's no need to invent a separate trigger when a real one
exists. The calculation should run as a non-blocking, best-effort step:
if it succeeds, record it; if something about the calculation
unexpectedly fails, log it and let the actual plan change (already
real, already tested, already working) proceed unaffected - a proration
audit-record failure must never break the underlying feature that
already works.

## 3. Existing Functionality That Must Not Change

- `change_plan`'s actual plan-swapping behavior, its existing tests, and `SubscriptionPage`'s existing plan-change UI/flow - must keep working exactly as they do today. This stage adds a calculation alongside it, not a redesign of it.
- All existing tests must still pass.

## 4. Required Changes

### 4.1 The proration calculation — standard, well-defined math

Given the subscription's current billing period (`current_period_start` /
`current_period_end`), the old plan's `price_cents`, the new plan's
`price_cents`, and the moment of change:

```
days_total     = (period_end - period_start) in days
days_remaining = (period_end - now) in days
unused_credit  = old_plan.price_cents * (days_remaining / days_total)
new_charge     = new_plan.price_cents * (days_remaining / days_total)
net_amount     = new_charge - unused_credit
```

`net_amount` positive = additional amount owed (an upgrade);
negative = credit owed (a downgrade). All money in cents, integer math,
never floats, per this project's established convention. Handle rounding
deliberately and document the chosen approach (e.g. round to the nearest
cent, note which direction) rather than leaving it ambiguous.

### 4.2 ProrationRecord — an audit record, not a transaction

Fields: `tenant`, `subscription`, `from_plan`, `to_plan`, `period_start`,
`period_end`, `calculated_at`, `amount_cents` (signed), `currency`. This
is a record of a calculation performed at a real moment for a real plan
change - legitimate real domain data, same category as `UsageRecord` -
not a record of money actually moving, and the model / its docstring
should say so explicitly.

### 4.3 Wiring (per section 2's resolved answer)

If wiring into `change_plan`: compute and record the `ProrationRecord`
as a non-blocking step before or alongside the actual plan swap. A
calculation failure must never prevent the real, already-working plan
change from succeeding.

## 5. Files Likely Affected

```
new:      apps/billing/migrations/... (ProrationRecord model)
          the calculation service
          tests for all of the above
modified: apps/billing/services.py (if wired into change_plan)
```

No frontend file required (unless section 2's investigation finds
trivially surfacing the amount is low-cost - not required either way).

## 6. Business Rules

- No real charge, refund, or gateway call results from this stage, under any circumstance.
- The calculation is deterministic and testable independent of any live provider.

## 7. Security Requirements

No new external surface.

## 8. Edge Cases

- A plan change on the exact day the period starts (`days_remaining` equals `days_total`) - full-period math, no rounding surprises.
- A plan change on the last day of the period (`days_remaining` approaches zero) - a near-zero but correctly-signed amount, not a divide-by-zero or nonsensical result.
- Changing to the same plan (a no-op price-wise) - `net_amount` should correctly compute to zero, not error.
- A subscription with no real period data yet (shouldn't happen given `change_plan` only applies to existing subscriptions, but verify this can't crash if it somehow occurs).

## 9. Tests Required

- Upgrade mid-cycle - positive `net_amount`, verified against a hand-calculated expected value for at least one concrete example.
- Downgrade mid-cycle - negative `net_amount`, same rigor.
- Edge cases from section 8, each with an explicit expected value.
- If wired into `change_plan`: a real plan change produces a correct `ProrationRecord`, and a forced calculation failure doesn't prevent the plan change itself from succeeding (proving the non-blocking requirement, not just asserting it).

## 10. Acceptance Criteria

1. `manage.py test` - full count reported (baseline 239).
2. `manage.py check`, `makemigrations --check` - clean.
3. Report: the resolved answer to section 2, the Razorpay plan-change-support finding from section 1, and the exact rounding approach chosen for section 4.1.
4. `git status` - no unrelated file changed.

## 11. Must NOT Do

- Do not call any Razorpay API to attempt a real charge or refund.
- Do not claim, anywhere in code comments, docstrings, or (if built) UI text, that a real financial transaction occurred.
- Do not let a proration calculation failure block the real, working plan-change flow.
- Do not build D7 or D8.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-d6-spec.md, then inspect the repository.
Produce an implementation plan - including your proposed answer to
section 2's open design question and your finding on section 1's
Razorpay research question - and wait for my approval before writing
any code.

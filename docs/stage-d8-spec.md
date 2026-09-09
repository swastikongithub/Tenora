# Claude Code Implementation Specification — Stage D8: Reconciliation

**Scope:** the last stage in the original Stage D sequence - periodically
cross-check local Subscription state against the payment provider's
actual records, to catch drift (a webhook that never arrived, a status
mismatch, anything the event-driven pipeline might have missed). Build
the comparison logic and drift-detection mechanism now, against
MockGatewayAdapter; the live cross-check against real Razorpay records
is explicitly deferred, same pattern as every prior D-stage's live
verification step.

**Not in scope:** any automatic corrective action beyond detecting and
recording drift (correcting it is a deliberate, separate decision - see
section 1), any live-provider verification, any further D-stage (this
closes the original D1-D8 sequence).

---

## 0. This stage is structurally different from D1–D7 — say so plainly

Every prior D-stage could be fully verified with mocks, deferring only
the final live confirmation. D8's entire purpose is comparing local
state against the provider's real state - so its live verification
isn't just "nice to confirm for real," it's the actual point of the
feature. Build and test the mechanism thoroughly against
MockGatewayAdapter (proving the comparison/drift-detection logic is
correct), but be honest in the report that this stage's real value only
materializes once it runs against a live account.

## 1. Objective

Detection, not automatic correction, in this stage. When
reconciliation finds a mismatch between local state and the provider's
reported state, it should record the drift clearly (what was
expected, what was found, when) - not silently auto-correct it. Silently
overwriting local state based on an external comparison is a bigger,
riskier decision than this stage should make unilaterally; a human
(or a well-considered future stage) should decide how to act on detected
drift. This is the same caution already shown throughout Stage D - e.g.
D4's bounded retry rather than infinite automatic reprocessing, D6's
non-blocking calculation that never silently alters billing state.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/payment-gateway-adapter-spec.md   - the PaymentGatewayAdapter
                                          interface - this stage will
                                          likely need a new interface
                                          method to fetch a
                                          subscription's current state
                                          from the provider (something
                                          D1/D2's interface doesn't have,
                                          since nothing needed it before
                                          now) - verify what exists,
                                          propose the addition following
                                          the same justified-extension
                                          precedent as period dates/
                                          correlation IDs
apps/billing/models.py                 - Subscription, WebhookEvent -
                                          what local state exists to
                                          compare against
apps/billing/services.py               - existing service-layer
                                          conventions, D5's
                                          UsageMeteringService and D7's
                                          batch-orchestration pattern as
                                          the closest precedent for a
                                          "check every eligible tenant"
                                          sweep
apps/billing/tasks.py                  - D7's task pattern - this
                                          stage's sweep likely becomes a
                                          third scheduled task, following
                                          the exact same thin-wrapper
                                          convention
```

Current state: D1-D7 complete and committed. Backend 268/268.

## 3. Existing Functionality That Must Not Change

- No existing D1-D7 logic changes - this stage adds a new, additive
  comparison capability.
- All existing tests must still pass.

## 4. Required Changes

### 4.1 Adapter interface addition — fetch current provider state

Investigate what the adapter interface needs to support this stage:
likely a get_subscription_status(external_subscription_id) -> <some
normalized shape> method, implemented in both RazorpayGatewayAdapter (a
real API call) and MockGatewayAdapter (a configurable fake response for
testing). Follow the same justified-extension precedent already used
twice in this project (period dates, correlation IDs) - a small,
necessary addition, not a redesign.

### 4.2 Drift detection

A service method that, for a given Subscription, fetches the
provider's current reported state and compares it against local state
(status, at minimum - consider whether period dates are also worth
comparing). A mismatch gets recorded - a new small model (e.g.
ReconciliationDiscrepancy - tenant, subscription, field, expected
value, found value, detected_at) is the honest way to do this, same
audit-record philosophy as UsageRecord/ProrationRecord: a record of
something real that was found, not an automatic action.

### 4.3 A sweep — following D5/D7's established pattern

A method that runs this check across every tenant with a subscription
(mirroring D5's snapshot_all_subscribed/D7's process_pending naming and
shape), a management command for manual triggering, and a third
scheduled Celery task calling the same service method - exactly the
shared-service-layer pattern D7 already established and proved correct.
Do not reimplement D7's orchestration pattern differently; follow it.

## 5. Files Likely Affected

```
new:      apps/billing/migrations/... (ReconciliationDiscrepancy model)
          the drift-detection service method + sweep
          the management command
          the Celery task
          tests for all of the above
modified: apps/billing/gateway/base.py, razorpay.py, mock.py (the new
                                          interface method)
          apps/billing/tasks.py (the third task)
          config/celery.py (the third scheduled entry)
```

No frontend file required for this stage.

## 6. Business Rules

- Detected drift is recorded, never silently auto-corrected.
- The comparison must be read-only against the provider - this stage
  never writes anything back to Razorpay.

## 7. Security Requirements

No new external-facing surface - this is an internal, scheduled,
read-only comparison.

## 8. Edge Cases

- A Subscription whose provider record no longer exists at all
  (e.g. deleted on the provider's side, however unlikely) - handled
  cleanly, recorded as a discrepancy, not a crash.
- No drift found - a clean, unremarkable sweep result, not treated as
  noteworthy or logged loudly.
- The provider API call itself failing (network, auth) - logged clearly,
  doesn't crash the sweep for other tenants, doesn't get mistaken for a
  genuine state discrepancy.

## 9. Tests Required

- Drift correctly detected and recorded when MockGatewayAdapter is
  configured to report a different status than local state.
- No drift recorded when they match.
- A provider-call failure (mocked) is handled cleanly, distinct from a
  genuine mismatch.
- The sweep, task, and command all follow D7's proven pattern - tests
  mirroring D7's test_tasks.py shape.

## 10. Acceptance Criteria

1. manage.py test - full count reported (baseline 268).
2. manage.py check, makemigrations --check - clean.
3. Report: the adapter interface addition and why it was necessary, and
   an explicit, honest statement that this stage's live value is
   unproven until it runs against real Razorpay data.
4. git status - no unrelated file changed.

## 11. Must NOT Do

- Do not automatically correct detected drift - record it only.
- Do not write anything back to the provider.
- Do not claim this stage is "fully verified" in the same sense D1-D7
  were - its core purpose genuinely requires live data to prove.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-d8-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing
any code.

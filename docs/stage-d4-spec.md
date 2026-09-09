# Claude Code Implementation Specification — Stage D4: Out-of-Order Event Handling

**Scope:** protect Subscription state against webhook events arriving in
the wrong relative order - a real, documented Razorpay behavior (their own
docs note events like payment.authorized can arrive after
payment.captured), not a hypothetical. D3 already made processing a
single event idempotent (the same event twice is safe); D4 addresses a
different problem - different events for the same subscription arriving
out of their logical sequence.

**Not in scope:** D5-D8, any change to the adapter interface's already-
justified fields (period dates, correlation ID), any live-provider
verification.

---

## 0. Buildable and testable now, no live provider needed

Same as every prior D-stage: fully buildable and testable against
MockGatewayAdapter and deliberately-constructed out-of-order event
sequences. No live Razorpay account required.

## 1. Objective

D3 already built some accidental ordering protection as a side effect of
its state-machine guards - CANCELED is terminal (a late ACTIVATED or
CHARGED can't undo it), and several handlers already no-op when the
target is in an unexpected state. This stage makes that protection
deliberate and complete, not incidental.

Two concrete gaps worth naming up front:

1. A CHARGED event's period dates could move backward in time if two CHARGED events for the same subscription are processed out of their real order (e.g. a redelivered older event processed after a newer one already advanced the period). Right now, nothing checks this - whichever CHARGED event happens to process last simply wins, regardless of which period it actually represents.
2. A CHARGED event arriving before the ACTIVATED event that would have created the Subscription currently gets silently, permanently discarded (D3's "no match found -> log, mark processed=True, no crash" behavior) - meaning real period data from that first charge is lost forever once ACTIVATED eventually does arrive and create the row. This is a genuine, if narrow, data-loss risk.

## 2. Inspect Before Implementing — two open design questions

```
CLAUDE.md
docs/stage-d3-v2-spec.md, the period-date fix spec — the exact current
                                          shape of NormalizedEvent,
                                          WebhookEvent, and
                                          WebhookProcessingService's
                                          handlers - confirm before
                                          assuming, don't work from the
                                          spec's memory of them
apps/billing/gateway/base.py           - confirm exactly what ordering-
                                          relevant data is already
                                          available (period_start/
                                          period_end) versus what would
                                          need to be added
apps/billing/services.py               - WebhookProcessingService's
                                          current handlers - the guards
                                          they already have (CANCELED
                                          terminal, etc.) vs. what's
                                          still missing

```

Open question 1 — how to detect and safely ignore a stale/out-of-order
event, in general, not just for CHARGED. My starting recommendation,
to validate or challenge:

- For CHARGED specifically: a period-monotonicity guard - only apply a CHARGED event's period update if its period\_start is at or after the Subscription's currently-stored current\_period\_end. Otherwise, it's chronologically stale relative to what's already been applied - log it clearly and treat it as a safe no-op (still mark processed=True, since it's not a case that will resolve itself by retrying). This reuses fields that already exist (from the period-date fix) - no new interface field needed for this specific protection.
- For ordering across different event types (e.g. a PAYMENT\_TROUBLE event for an old period arriving after a newer CHARGED already resolved it) - PAYMENT\_TROUBLE doesn't currently carry period data, so there's no data-driven way to order it against a CHARGED event using only what exists today. Investigate whether Razorpay's webhook envelope carries a general event-level timestamp (distinct from received\_at, which only reflects when your server got it, not when Razorpay generated it) that could serve as a general ordering signal. If one exists and is reasonably added to NormalizedEvent (same justified-extension precedent as the period-date fix), propose adding it. If it would require speculative complexity beyond what's actually needed right now, propose a narrower fix and name the remaining gap explicitly rather than over-building.

Open question 2 — should an unmatched CHARGED event (no Subscription
or SubscriptionCheckout found yet) stay retryable, or stay a permanent
no-op? D3's current behavior permanently discards it. My starting
recommendation: for CHARGED specifically, leave it processed=False
(retryable via the existing backfill command) rather than permanently
discarding it, since ACTIVATED arriving shortly after and creating the
Subscription would let a retry succeed and recover the real period
data. This needs a bound, though - an event that's genuinely
unmatchable (garbage ID, a subscription that will never exist) shouldn't
retry forever. Propose a simple, bounded approach (e.g. an age-based
cutoff - after some reasonable window, give up and mark it processed
with a logged warning) rather than an open-ended retry loop. Keep this
simple; don't build a general-purpose retry/backoff framework for a
narrow case.

## 3. Existing Functionality That Must Not Change

- D3's per-event idempotency (the same event processed twice is already safe) - untouched, this stage adds a different, complementary protection.
- Every existing EventType handler's already-correct guards (CANCELED terminal, etc.) - kept, not redesigned.
- All existing tests must still pass.

## 4. Required Changes

Driven by section 2's resolved answers:

- The CHARGED period-monotonicity guard.
- Whatever cross-event-type ordering mechanism (if any) section 2's investigation concludes is actually warranted right now - don't over-build if the investigation finds the narrower fix is sufficient for what this project actually needs.
- The bounded-retry adjustment for unmatched CHARGED events.

## 5. Files Likely Affected

```
modified: apps/billing/services.py (WebhookProcessingService's handlers)
          apps/billing/gateway/base.py, razorpay.py, mock.py (only if
                                          section 2 concludes a new field
                                          is genuinely warranted)
new:      tests constructing deliberately out-of-order event sequences

```

## 6. Business Rules

- A Subscription's state must never move backward in time due to event arrival order - only due to a genuinely later, more current event.
- Real data from a legitimately out-of-order-but-eventually-resolvable event (the CHARGED-before-ACTIVATED case) should be recovered when possible, not silently and permanently lost, within a reasonable bound.

## 7. Security Requirements

No new external surface - this stage strengthens correctness of already-
verified, already-stored events.

## 8. Edge Cases

- Two CHARGED events for the same subscription, processed out of their real order - the later-period one wins regardless of processing order, the earlier one is a clean logged no-op.
- CHARGED arriving before ACTIVATED - recovered via retry once ACTIVATED creates the Subscription, within whatever bound section 2 settles on.
- A genuinely permanently-unmatchable event - eventually gives up cleanly, logged, not retried forever.
- Verify the existing D3 idempotency tests (same event twice) still pass unmodified - this stage must not regress that guarantee while adding the new one.

## 9. Tests Required

- A deliberately-constructed out-of-order CHARGED sequence (older period processed after a newer one) - confirm the newer period's data wins, the older event is a clean no-op.
- CHARGED arriving with no matching Subscription/SubscriptionCheckout - stays retryable (per section 2's resolved bound), and a subsequent ACTIVATED + retry correctly recovers the period data.
- The bounded-retry cutoff - an event old enough to exceed the bound is cleanly given up on, not retried forever.
- Whatever cross-event-type ordering mechanism section 2 lands on, if any - tested with a constructed out-of-order sequence proving it works.

## 10. Acceptance Criteria

1. manage.py test - full count reported (baseline 209 backend / 287 frontend, though this stage is backend-only).
2. Report: resolved answers to both section 2 open questions, with reasoning.
3. Manual, synthetic verification against the dev server: a hand- constructed out-of-order CHARGED sequence processed correctly.
4. git status - no unrelated file changed.

## 11. Must NOT Do

- Do not weaken D3's existing per-event idempotency.
- Do not build a general-purpose retry/backoff framework - keep the bounded-retry mechanism simple and scoped to what section 2 actually needs.
- Do not touch the adapter interface's already-justified fields beyond what section 2's investigation concludes is genuinely necessary.
- Do not build D5-D8.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code - expect
the plan to include resolved, investigated answers to both section 2
questions.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-d4-spec.md, then inspect the repository.
Produce an implementation plan - including your proposed answers to
section 2's two open design questions - and wait for my approval before
writing any code.

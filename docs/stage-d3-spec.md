# Claude Code Implementation Specification — Stage D3: Webhook-Driven State Changes

**Scope:** turn the WebhookEvent rows D1 already receives, verifies, and
stores into real Subscription state changes - the first ACTIVE
subscription this product will ever have that was actually paid for.
This is the stage where the whole payment flow becomes real rather than
inert.

**Not in scope:** out-of-order event handling as its own hardened concern
(D4 - this stage handles the common case correctly, D4 hardens it),
usage metering, proration, Celery, reconciliation.

---

## 0. Still blocked, still not blocking

The Razorpay account issue (Subscriptions product erroring) is still
unresolved as of this stage. Same split as D1/D2: all of this stage's
logic can be built and fully tested with mocked/synthetic webhook
payloads right now. The live, end-to-end proof (a real Checkout -> real
webhook -> real ACTIVE subscription) stays pending until the account
clears, to be done in one combined pass with D1/D2's still-open live
verification items.

## 1. Objective

Right now, WebhookEvent rows accumulate with processed=False forever -
D1 deliberately stopped short of doing anything with them. D2 removed
the only way a local Subscription could be created from client input,
which means the very first time a tenant's Subscription row comes into
existence should be right here, in this stage, driven by a real
subscription.activated event - not by anything a browser said.

Processing must be idempotent by design, not just non-duplicated. D1
already guarantees a given event is stored exactly once (the unique
constraint on razorpay_event_id). This stage adds a second, different
guarantee: applying a given event's effect to a Subscription must be
safe to run more than once without corrupting state - e.g., processing
subscription.activated against a Subscription that's already ACTIVE
must be a clean no-op, not an error and not a duplicate side effect. This
matters because processing (unlike storage) can plausibly be retried -
see section 2's open question.

A webhook's HTTP response must never depend on processing succeeding.
D1 already returns 200 the moment an event is safely stored - that
must remain true. If this stage's state-change logic fails for any
reason, the webhook response is still 200 (the event was received and
stored correctly); the failure is logged and the event stays available
for retry via whatever mechanism section 2 settles on. Making Razorpay's
delivery success depend on your business logic succeeding would turn
every application bug into a webhook retry storm.

## 2. Inspect Before Implementing — open design question

```
CLAUDE.md
docs/stage-d1-spec.md, docs/stage-d2-spec.md - the WebhookEvent and
                                          SubscriptionCheckout models this
                                          stage consumes; read in full
apps/billing/models.py                 - Subscription, WebhookEvent,
                                          SubscriptionCheckout - exact
                                          current fields, confirm before
                                          assuming
apps/billing/services.py               - SubscriptionService (kept from
                                          D2 specifically for this stage
                                          to use), transition_status,
                                          LEGAL_TRANSITIONS,
                                          WebhookService.record_event
apps/billing/views.py                  - RazorpayWebhookView - where
                                          processing gets triggered from,
                                          per whichever answer section 2's
                                          investigation lands on
```

Open design question — investigate and propose, don't assume: with
no background job runner yet (Celery is D7), how does event processing
actually get triggered? My starting recommendation, to validate or
challenge against the real code:

- Process synchronously, inline, right after WebhookService.record_event
  successfully stores the event - within the same request, but as a
  distinct step whose failure is caught and logged, never allowed to
  turn the HTTP response into anything other than 200 once storage
  succeeded (per section 1).
- Also build a management command that finds processed=False rows
  and retries them - this covers any event whose inline processing
  failed, and gives a manual recovery/backfill path before Celery exists
  to automate it.

If you find a better approach during investigation, propose it - but
whatever's chosen must satisfy section 1's two hard requirements
(idempotent effect, response never blocked on processing).

## 3. Existing Functionality That Must Not Change

- D1's webhook storage/signature verification, D2's checkout flow -
  untouched. This stage adds processing after D1's storage step; it
  doesn't change how events arrive or get verified.
- Subscription.Status/LEGAL_TRANSITIONS - the transition rules
  themselves are untouched; this stage is a new caller of
  transition_status/create_subscription, not a redesign of the state
  machine.
- All existing tests must still pass.

## 4. Required Changes

### 4.1 Subscription.razorpay_subscription_id

A new nullable, unique-when-set field on Subscription - this is what
lets a future event (e.g. subscription.charged, arriving after the
SubscriptionCheckout row has done its job) be correlated back to the
right local row. Populated when the Subscription is first created by
this stage's subscription.activated handling.

### 4.2 Event processing logic

For each event type this stage handles, look up the relevant
SubscriptionCheckout (by razorpay_subscription_id from the payload)
or Subscription (once one exists, by its own razorpay_subscription_id)
and apply the corresponding change, atomically (the state change and
marking WebhookEvent.processed=True happen in the same transaction):

- subscription.activated - if no local Subscription exists yet for this
  tenant, create one via the existing, kept
  SubscriptionService.create_subscription (verify its exact behavior/
  default status before assuming - don't guess), using the tenant/plan
  from the matched SubscriptionCheckout, and set the new
  razorpay_subscription_id. If a Subscription already exists and is
  already active, this is a safe no-op (section 1's idempotency
  requirement).
- subscription.charged - a renewal; update the current billing period
  fields. If the subscription was PAST_DUE, this legitimately moves it
  back toward ACTIVE (verify this transition is legal per
  LEGAL_TRANSITIONS, don't assume).
- subscription.cancelled - transition to CANCELED via the existing
  transition_status (which already correctly rejects CANCELED ->
  CANCELED, so a duplicate cancellation event is automatically safe).
- subscription.pending/subscription.halted/payment.failed - map toward
  PAST_DUE (verify these specific event names against Razorpay's current
  docs, don't assume from memory).
- Any other/unrecognized event type - mark processed=True with no state
  change (a safe, logged no-op) - don't error, don't retry forever on an
  event this stage doesn't yet have a defined meaning for. This is the
  same defensive default as every other "don't guess at unknown data"
  decision in this project.

### 4.3 Management command

A command that finds WebhookEvent rows with processed=False and retries
processing them - for recovery/backfill, per section 2.

## 5. Files Likely Affected

```
new:      apps/billing/migrations/... (Subscription.razorpay_subscription_id)
          the event-processing logic (in services.py, following the
                                       existing service-layer pattern)
          the management command
          tests for all of the above
modified: apps/billing/models.py
          apps/billing/views.py (wiring processing into the webhook flow,
                                  per section 2's resolved approach)
```

No frontend change in this stage (the "processing" UI feedback from D2
stays as-is - this stage is what eventually makes a page reload show
ACTIVE instead of the empty state, but no new frontend code is needed
for that to work, since the existing subscription-fetching pages already
render whatever Subscription state actually exists).

## 6. Business Rules

- A Subscription is never created except by this stage's
  subscription.activated handling (or the deferred seed_demo_data path,
  which uses the same underlying service).
- Every state change this stage makes is idempotent - reprocessing any
  event must never corrupt state or double-apply an effect.

## 7. Security Requirements

- No new external-facing surface - this stage processes already-verified
  events; it doesn't add a new way for unverified data to reach the
  system.

## 8. Edge Cases

- The same event processed twice (via the management command retrying
  something that actually already succeeded, or any other double-trigger)
  - must be a clean no-op, tested explicitly.
- A subscription.charged event arriving for a razorpay_subscription_id
  that doesn't match any known Subscription or SubscriptionCheckout (a
  genuinely unexpected case) - handled cleanly (logged, marked
  processed, no crash), not silently ignored without a trace.
- Processing raising an unexpected exception - caught, logged, event
  stays processed=False for the recovery command, and the webhook's
  HTTP response is still 200 (per section 1).

## 9. Tests Required

- Each handled event type: correct state change applied, using
  synthetic/mocked payloads (no real Razorpay calls).
- Idempotency: processing the same event twice produces the same end
  state as processing it once, for every handled event type.
- Unknown event type: marked processed, no state change, no error.
- The management command: correctly finds and retries processed=False
  rows; correctly leaves already-processed rows alone.
- The webhook endpoint's response is 200 even when processing fails
  internally (a test that forces a processing exception and asserts the
  HTTP response is unaffected).

## 10. Acceptance Criteria

1. manage.py test - full count reported.
2. Report: the resolution to section 2's open question, and confirmation
   every event-type mapping (section 4.2) was checked against Razorpay's
   current documentation, not assumed from memory.
3. Manual verification using synthetic (not live) webhook payloads
   against the running dev server: a fabricated subscription.activated
   event correctly creates a real Subscription row; a second identical
   event is a no-op.
4. The live, real-Checkout-to-real-webhook walkthrough is expected to
   remain blocked - report this plainly, to be done together with
   D1/D2's pending live items once the Razorpay account issue clears.
5. git status - no unrelated file changed.

## 11. Must NOT Do

- Do not let a processing failure change the webhook endpoint's HTTP
  response - it must stay 200 once the event is stored, per section 1.
- Do not build out-of-order-specific hardening - that's D4's job; this
  stage handles the straightforward case correctly.
- Do not build usage metering, proration, Celery, or reconciliation.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code - expect
the plan to include a proposed, investigated answer to section 2 before
proceeding.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-d3-spec.md, then inspect the repository.
Produce an implementation plan - including your proposed answer to
section 2's open design question - and wait for my approval before
writing any code.

# Claude Code Implementation Specification — Stage D2: Subscription Creation + Checkout

**Scope:** create a real Razorpay Subscription (tied to a Plan's
razorpay_plan_id from D1) when an OWNER subscribes, and integrate
Razorpay's Checkout on the frontend so a real customer authorization
happens. This stage does not activate anything locally - the existing
Subscription.Status state machine is not touched, and no local status
flips to ACTIVE as a result of anything built here. That's D3's job,
driven by the webhook events D1 already knows how to receive and store.

**Not in scope:** any local status transition, out-of-order event
handling, usage metering, proration, Celery, reconciliation.

---

## 0. Current blocker — build and test now, verify live later

The Razorpay Subscriptions product is currently returning "Something went
wrong" in the dashboard itself (confirmed account-side, not a code issue)
- this is pending resolution via Razorpay support, outside anyone's
control here. This does not block this stage's real work:

- All backend logic, using mocked Razorpay SDK responses, can be built
  and fully tested now - same approach D1 used successfully.
- The one thing that stays blocked until the account issue clears:
  actually opening a real Razorpay Checkout popup and completing a real
  test-mode payment. Build everything up to that point; flag the final
  live walkthrough as pending, the same way D1's dashboard round-trip was
  left pending.

## 1. Objective

Today, POST /api/subscriptions/current/ creates a local Subscription
row directly - no payment gateway involved at all (this was correct and
honest for Phase 1, where no real billing existed). That can no longer be
true once real money is involved: creating a local subscription record
before a customer has actually authorized payment would be fabricating a
paid state that doesn't exist yet - the same category of dishonesty this
project has refused everywhere else, just applied to billing state instead
of UI content.

The new flow: OWNER selects a plan -> backend creates a real Razorpay
Subscription (no local Subscription row activation yet) -> frontend
opens Razorpay Checkout with that subscription's ID -> customer authorizes
(enters a test card in test mode) -> Razorpay's Checkout returns a
success payload to the frontend, which is used only for immediate UI
feedback ("processing, waiting for confirmation") - never to create or
activate a local Subscription row. The real, trustworthy activation
happens later, server-to-server, via the subscription.activated webhook
- which D1 already knows how to receive, verify, and store; wiring it into
an actual state change is D3, not this stage.

Two different Razorpay signatures exist - do not confuse them (this was
already true for D1's webhook signature; a second, different one appears
here):
- The webhook signature (D1, already built) - HMAC-SHA256 over the raw
  webhook body, keyed with the webhook secret.
- The checkout success signature - computed by the frontend receiving
  razorpay_payment_id, razorpay_subscription_id, and
  razorpay_signature from Checkout's success callback; verified
  server-side via HMAC-SHA256 of subscription_id|payment_id keyed with
  the API secret (not the webhook secret). Verify this exact
  construction against Razorpay's current documentation before
  implementing - don't assume from memory.

## 2. Inspect Before Implementing — real open questions, investigate first

```
CLAUDE.md
apps/billing/models.py                 - Subscription's current fields,
                                          Status choices, LEGAL_TRANSITIONS
                                          - confirm exactly what exists
                                          before proposing any change
apps/billing/services.py               - SubscriptionService.create_subscription
                                          - the existing (Phase-1-only,
                                          no-payment) creation logic this
                                          stage's new flow replaces or
                                          sits in front of
apps/billing/views.py                  - CurrentSubscriptionView.post -
                                          today's entry point; this stage
                                          changes what happens when an
                                          OWNER "subscribes"
apps/billing/razorpay_client.py        - D1's single SDK construction
                                          point, reused here
docs/stage-d1-spec.md                  - D1's WebhookEvent/signature work,
                                          the foundation this stage builds on
```

Real, unresolved design question — investigate and propose, don't
assume an answer from this spec alone: with local Subscription
creation no longer happening immediately, how does the system track "a
Razorpay subscription creation is in flight for this tenant" between the
moment checkout starts and the moment D3's webhook eventually confirms
it? Options worth considering (propose the one that best fits the
existing schema, or another you find better - report your reasoning):
- A new nullable field (e.g. on Tenant, or a small new model) tracking
  a pending razorpay_subscription_id before any local Subscription
  row exists.
- Creating a local Subscription row immediately but in a genuinely new,
  honestly-named status (e.g. PENDING) - which would mean extending
  Subscription.Status and LEGAL_TRANSITIONS, a real, deliberate change
  to a state machine that's been locked and tested extensively since B2.
  If you propose this path, treat the state-machine change with the same
  weight as any other change to already-tested, foundational logic - it
  is not a small edit.

Whichever approach: it must prevent a double-click from creating two
Razorpay-side subscriptions for the same tenant, and it must not require
trusting anything the client says about payment success - only the
webhook (later, in D3) is authoritative.

## 3. Existing Functionality That Must Not Change

- Subscription.Status, LEGAL_TRANSITIONS, and every existing status
  transition test - untouched, unless section 2's investigation genuinely
  requires an extension, reported and justified explicitly before
  implementing, not assumed.
- D1's webhook endpoint, signature verification, and WebhookEvent
  model - untouched; this stage adds a second, different signature check
  (the checkout one), it doesn't modify the first.
- All existing tests must still pass.

## 4. Required Changes

### 4.1 Backend — create the real Razorpay Subscription

When an OWNER initiates subscribing to a plan: create a Razorpay
Subscription via the SDK, using the plan's razorpay_plan_id (from D1 -
if a plan lacks one, this must fail cleanly with a clear error, not crash
- report how this is surfaced). total_count (the number of billing
cycles Razorpay requires - they don't support truly infinite
subscriptions) needs a concrete, reasonable value; pick one that
functionally represents "ongoing" (e.g. enough cycles for several years)
and report the exact number chosen and why.

Return to the frontend whatever it needs to open Checkout: the Razorpay
subscription ID, the public key ID, and any other required Checkout
parameters.

### 4.2 Backend — checkout confirmation endpoint

A new endpoint (e.g. POST /api/subscriptions/current/confirm-checkout/)
that receives the Checkout success payload
(razorpay_payment_id/razorpay_subscription_id/razorpay_signature),
verifies the checkout signature (section 1's second signature type -
verified against current docs, not assumed), and does not create or
mutate any local Subscription row on success. Its only job is confirming
the checkout handshake was authentic, for UI feedback and audit purposes
- the real state change waits for D3's webhook processing. A failed
signature check here -> clean error, not a crash.

### 4.3 Frontend — Razorpay Checkout integration

On plan selection, call the backend to create the Razorpay subscription
(section 4.1), then open Razorpay's Checkout widget (their JS SDK -
verify the current integration approach against their docs, same
discipline as D1's API verification) configured for subscription mode
with the returned subscription ID. On Checkout's success callback, POST
to the confirm endpoint (section 4.2) and show an honest "processing"
state - not an "active" or "success" state, since local status hasn't
changed and won't until D3 processes the real webhook. On Checkout's
failure/cancellation, show a clean error, no partial state left behind.

## 5. Files Likely Affected

```
Backend:
  modified: apps/billing/models.py (only if section 2's investigation
                                      concludes a schema change is
                                      needed - report and justify)
            apps/billing/services.py, views.py
            apps/billing/razorpay_client.py (if additional SDK calls
                                              need a new helper)
  new:      tests for the above (all mocked - no real Razorpay calls
                                  in the automated suite)

Frontend:
  modified: frontend/src/routes/SubscriptionPage.tsx (or wherever plan
                                                        selection lives)
  new:      Checkout integration component/hook
            tests (mocking Razorpay's Checkout callback, not a real
                   payment flow)
```

## 6. Business Rules

- No local Subscription row is ever created or activated based on
  anything the client reports - only a verified server-to-server webhook
  (D3) is authoritative.
- total_count's chosen value and reasoning must be reported, not
  silently picked.

## 7. Security Requirements

- The checkout signature is verified using the exact construction
  Razorpay's current docs specify - confirmed, not assumed.
- The Razorpay API secret is never exposed to the frontend - only the
  public key ID crosses that boundary.

## 8. Edge Cases

- A customer abandons Checkout without completing payment - no local
  state change, no orphaned "half-subscribed" appearance in the UI.
- A double-click on "subscribe" - must not create two Razorpay-side
  subscriptions for the same tenant (section 2's investigation must
  address this explicitly).
- The confirm-checkout endpoint receiving a tampered/invalid signature -
  clean rejection, not a crash, and definitely no local state change.

## 9. Tests Required

- Backend: subscription creation calls the SDK with correct plan/
  total_count values (mocked); a plan lacking razorpay_plan_id fails
  cleanly; the confirm-checkout endpoint correctly verifies a valid
  signature and correctly rejects an invalid one - and in neither case
  does any local Subscription row get created or mutated (an explicit
  assertion on absence, same discipline as prior stages' "prove the
  thing doesn't happen" tests).
- Frontend: Checkout opens with correct parameters; success callback
  posts to confirm-checkout and shows a "processing," not "active,"
  state; failure/cancellation shows a clean error.

## 10. Acceptance Criteria

1. manage.py test, npm test - full counts reported, all mocked, no
   real Razorpay calls in the automated suite.
2. npm run build, npm run lint - clean.
3. Report: the resolution to section 2's open design question (with
   reasoning), the exact total_count chosen and why, and confirmation
   the checkout signature construction was verified against current docs.
4. The live Checkout walkthrough is expected to remain blocked by the
   Razorpay account issue - report this plainly rather than skipping the
   acceptance section silently. Once the account issue clears, this
   walkthrough (plus D1's still-pending dashboard round-trip) should be
   done together in one real-account verification pass.
5. git status - no unrelated file changed.

## 11. Must NOT Do

- Do not create or activate a local Subscription row from anything the
  client reports - only D3's webhook processing may eventually do that.
- Do not extend Subscription.Status/LEGAL_TRANSITIONS without
  explicitly reporting and justifying the change per section 2 - this is
  not a casual edit.
- Do not build webhook-to-state-change wiring, usage metering,
  proration, Celery, or reconciliation.
- Do not attempt the live Checkout walkthrough as a blocking requirement
  - build and mock-test everything, report the live step as pending.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code - given
section 2's genuinely open design question, expect the plan to propose a
concrete answer for review before implementation, not just proceed on an
assumption.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-d2-spec.md, then inspect the repository.
Produce an implementation plan - including your proposed answer to
section 2's open design question - and wait for my approval before
writing any code.

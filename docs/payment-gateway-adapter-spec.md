# Claude Code Implementation Specification — Payment Gateway Adapter Interface

**Scope:** introduce a provider-neutral boundary between the billing
domain and Razorpay. Relocate D1/D2's already-built, already-tested
Razorpay logic behind a RazorpayGatewayAdapter implementing a new
interface; build a MockGatewayAdapter for development and automated
tests; rename the provider-specific fields to generic ones while it's
still cheap (no production data exists yet). This is purely a refactor
- no behavior change, no new external surface, and no live Razorpay
account needed to build or fully test any of it.

**Why now, before D3:** D3's original plan was written directly against
Razorpay's specific event names and payload shapes. Building D3 that way
now, then retrofitting this interface afterward, means writing the
event-handling logic twice. This stage exists to make D3 (and D4 later)
buildable once, correctly, against a boundary that already exists.

**Not in scope:** D3's actual event-processing logic (a separate spec,
written after this one lands), D4, D5-D8, any live-provider verification,
any frontend change (this is a backend-internal refactor; the
StartCheckoutView/ConfirmCheckoutView external contract - URLs,
request/response shapes - must not change).

---

## 1. Objective

Today, apps/billing/services.py calls Razorpay's SDK directly (via
D1's razorpay_client.get_client()), and D1's webhook signature
verification is hand-rolled specifically for Razorpay's exact HMAC
construction. This stage inserts a real seam: the domain layer depends
on an interface, not a vendor SDK - matching the same architectural
discipline this project has already applied elsewhere (e.g.
TenantScopedManager requiring an explicit tenant argument rather than
implicit thread-local state).

New locked rule, same weight as existing ones: after this stage,
nothing in apps/billing's domain logic (Subscription/Plan models,
SubscriptionService's state-machine methods) may import a payment
provider's SDK directly. All external calls go through the adapter
interface.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/stage-d1-spec.md, docs/stage-d2-spec.md - the exact existing
                                          Razorpay logic being relocated,
                                          not rewritten
docs/provider-independence-roadmap.md  - the full reasoning behind this
                                          stage; read in full
apps/billing/razorpay_client.py        - D1's single SDK construction
                                          point - the natural seam to
                                          build the interface around
apps/billing/services.py               - RazorpayPlanService,
                                          RazorpaySubscriptionService,
                                          verify_webhook_signature,
                                          verify_checkout_signature - all
                                          being relocated behind the
                                          interface
apps/billing/views.py                  - RazorpayWebhookView,
                                          StartCheckoutView,
                                          ConfirmCheckoutView - confirm
                                          their external contract before
                                          touching anything, so it can be
                                          verified unchanged after
apps/billing/tests/test_razorpay_webhook.py,
test_razorpay_checkout.py              - current tests, largely mocking
                                          the SDK directly; these need to
                                          migrate to mocking/injecting at
                                          the new interface seam
                                          (preserving every existing
                                          assertion's intent, not
                                          weakening coverage)
```

Current state: D1 + D2 complete, mock-tested, uncommitted (stacked
together). D3 has not been built. Backend 143/143.

## 3. Existing Functionality That Must Not Change

- StartCheckoutView/ConfirmCheckoutView's external API contract
  (URLs, request/response shapes) - completely unchanged. This is an
  internal refactor; nothing about how the frontend talks to these
  endpoints may differ.
- RazorpayWebhookView's external behavior - signature verification,
  event storage, dedup, the 200-response guarantee - all unchanged in
  observable behavior, even though the internal call path changes.
- Subscription/Plan's state machine, LEGAL_TRANSITIONS - untouched.
- All 143 existing tests must still pass, migrated to the new seam where
  they currently mock the SDK directly - not weakened, not skipped.

## 4. Required Changes

### 4.1 The interface

A PaymentGatewayAdapter interface (a Protocol or ABC - whichever
fits this codebase's existing style better; report which and why) with
methods covering exactly what D1/D2 already do, no more:

- create_plan(plan) -> str (the external plan ID) - D1's
  RazorpayPlanService.sync_plan logic.
- create_subscription(tenant, plan) -> <whatever D2's checkout flow
  needs returned> - D2's RazorpaySubscriptionService.create_checkout
  logic.
- verify_webhook_signature(headers, raw_body) -> bool - D1's logic,
  relocated, not rewritten.
- parse_webhook_event(headers, raw_body) -> NormalizedEvent - new
  work: define a small, common NormalizedEvent shape (event type
  from a project-defined vocabulary - e.g. ACTIVATED/CHARGED/
  CANCELLED/PAYMENT_TROUBLE/UNKNOWN - plus the external event ID,
  the external subscription ID, and the raw payload for audit purposes).
  This is where Razorpay's specific event names (subscription.activated,
  etc.) get mapped into the common vocabulary - this mapping logic
  moves here, out of what would have been D3 - so a future D3 only ever
  consumes NormalizedEvent, never raw Razorpay JSON.
- verify_checkout_signature(payment_id, subscription_id, signature) -> bool
  - D2's logic, relocated.

Keep this interface minimal - exactly what's needed for D1/D2's already-
built functionality plus the event-normalization D3 will need. Do not
speculatively add methods for capabilities nothing has asked for yet
(section 11).

### 4.2 RazorpayGatewayAdapter

Implements the interface, wrapping the SDK calls and logic already built
in D1/D2 - relocated, not rewritten. The underlying HMAC constructions,
API calls, and error handling stay exactly as they are; only their
container changes.

### 4.3 MockGatewayAdapter

Implements the same interface without any real network calls -
deterministic fake IDs, configurable to simulate success or specific
failure modes for testing. This is what all automated tests should use
going forward, and what local development can use without any Razorpay
credentials at all.

### 4.4 Adapter selection

Investigate the existing pattern (razorpay_client.get_client()'s
single-construction-point precedent) and propose how the active adapter
gets chosen/injected - e.g. a factory function reading a setting, with
tests overriding it or injecting MockGatewayAdapter directly. Report
the approach chosen.

### 4.5 Field renames — do this now, while it's free

Plan.razorpay_plan_id -> a generic name (e.g. external_plan_id). No
production data exists yet, so this is a cheap, safe rename now - doing
it later, after a real deployment has real data, would be materially
riskier. (Note: Subscription.razorpay_subscription_id doesn't exist
yet, since D3 was paused before it was built - when D3 is eventually
written against this new interface, it should use the generic name from
the start, avoiding a second rename entirely.)

### 4.6 SubscriptionService and views updated to call the interface

Every place that currently calls razorpay_client.get_client() or the
Razorpay-specific service methods directly now calls through the
adapter interface instead.

## 5. Files Likely Affected

```
new:      apps/billing/gateway.py (or similar - the interface +
                                    NormalizedEvent + both adapter
                                    implementations; use judgment on
                                    exact module layout, report choice)
          tests for the adapters themselves
modified: apps/billing/services.py (calls go through the interface)
          apps/billing/views.py (same)
          apps/billing/models.py (the field rename + its migration)
          apps/billing/tests/test_razorpay_webhook.py,
            test_razorpay_checkout.py (migrated to the new seam,
            every existing assertion's intent preserved)
```

No frontend file. No new external route or contract change.

## 6. Business Rules

- No behavior change from this stage - this is purely structural.
- The domain layer never imports a payment SDK directly, from this
  point forward (section 1's new locked rule).

## 7. Security Requirements

- Signature verification logic (webhook and checkout) is relocated
  exactly as-is - no change to the actual cryptographic checks, only to
  where they live.

## 8. Edge Cases

- Existing tests that currently mock razorpay_client.get_client
  directly - each needs to be re-pointed at the new seam
  (MockGatewayAdapter or the injection mechanism from section 4.4), with
  the same assertions, not weaker ones.

## 9. Tests Required

- The RazorpayGatewayAdapter and MockGatewayAdapter each satisfy the
  interface correctly (a shared test suite run against both, if
  practical, is a good way to prove they're truly interchangeable).
- Every existing D1/D2 test migrated to the new seam, passing, with its
  original intent preserved.
- parse_webhook_event's mapping from Razorpay's real event names to
  the common vocabulary - tested against the same verified event names
  D3's original (paused) plan already confirmed against live docs.

## 10. Acceptance Criteria

1. manage.py test - full count reported; no regression from 143.
2. npm run build, npm test, npm run lint - unaffected, confirm
   anyway (no frontend file touched).
3. Report: which interface style was used (Protocol/ABC) and why,
   the adapter-selection mechanism chosen, and confirmation
   StartCheckoutView/ConfirmCheckoutView's external contract is
   byte-identical before and after (a real diff/comparison, not an
   assumption).
4. git status - no unrelated file changed; this stage's changes should
   be cleanly additive to the still-uncommitted D1+D2 work.

## 11. Must NOT Do

- Do not build D3's actual event-processing/state-application logic -
  that's the next spec, written after this one lands.
- Do not speculatively add interface methods for capabilities nothing
  has asked for yet - keep it exactly as large as D1/D2 (+ the event
  normalization D3 will need) require.
- Do not change StartCheckoutView/ConfirmCheckoutView's external
  contract.
- Do not change Subscription/Plan's state machine.
- Do not require any live Razorpay credentials to build or test this
  stage - everything here should be fully verifiable with
  MockGatewayAdapter alone.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

Read docs/payment-gateway-adapter-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.

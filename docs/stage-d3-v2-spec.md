# Claude Code Implementation Specification — Stage D3 (v2): Webhook-Driven State Changes

**Scope:** turn stored WebhookEvent rows - now holding a normalized
EventType value (ACTIVATED/CHARGED/CANCELLED/PAYMENT_TROUBLE/UNKNOWN),
thanks to the adapter stage's parse_webhook_event - into real
Subscription state changes. This supersedes the original D3 plan, which
was written against raw Razorpay event names before the adapter
interface existed. The domain logic here should be near-identical to
that original plan's well-reasoned design; only the input shape changed
- cleaner, because it's already normalized.

**Not in scope:** D4 (out-of-order hardening), D5-D8, any live-provider
verification, any change to the adapter interface itself.

---

## 0. Still blocked, still not blocking

Same as D1/D2/the adapter stage: fully buildable and testable with the
MockGatewayAdapter and synthetic WebhookEvent rows, no live Razorpay
account needed. The live end-to-end proof stays pending until the
account clears.

## 1. Objective — carried over from the original D3 plan, still true

A WebhookEvent row existing must not, by itself, mean anything changed
in Subscription. This stage is what makes it mean something -
correctly, safely, and idempotently.

Two hard requirements, unchanged from the original plan:
- Idempotent by design: processing a given event's effect must be safe
  to run more than once without corrupting state or duplicating side
  effects.
- The webhook's HTTP response never depends on processing succeeding -
  this was already true after D1/the adapter stage (storage -> 200);
  this stage's processing logic must never be allowed to change that.

## 2. What changed since the original D3 plan (read this first)

- WebhookEvent.event_type now stores the normalized EventType value,
  not a raw provider string (the adapter stage's decision B). This
  stage's handlers switch on EventType, not on any provider's
  event-name strings.
- WebhookEvent.external_event_id (renamed from razorpay_event_id).
- The correlating field this stage needs on Subscription should be
  named external_subscription_id from the start - no rename needed
  later, since the adapter stage already established that naming
  convention for the sibling fields.
- The original D3 plan's proposed answer to "how does processing get
  triggered" (synchronous inline processing right after
  WebhookService.record_event, wrapped in a broad try/except Exception
  that logs and never lets the response become non-200, plus a
  process_webhook_events management command for retry/backfill) was
  sound reasoning and should carry forward unchanged - re-verify it
  against the current code, but there's no reason to reconsider the
  approach itself.

## 3. Inspect Before Implementing

```
CLAUDE.md
docs/payment-gateway-adapter-spec.md   - read in full; this is what this
                                          stage builds on
apps/billing/gateway/base.py           - NormalizedEvent, EventType -
                                          the exact shape this stage
                                          consumes
apps/billing/models.py                 - Subscription, WebhookEvent,
                                          SubscriptionCheckout - current
                                          fields (post-adapter-refactor
                                          naming), confirm before assuming
apps/billing/services.py               - SubscriptionService,
                                          WebhookService.record_event,
                                          LEGAL_TRANSITIONS
apps/billing/views.py                  - RazorpayWebhookView's current
                                          shape (post-refactor) - where
                                          processing gets wired in
```

## 4. Required Changes

### 4.1 Subscription.external_subscription_id

Nullable, unique-when-set. Named generically from the start (section 2).

### 4.2 Event processing — switch on EventType, not provider strings

For each WebhookEvent, atomically (state change + processed=True in
one transaction, idempotent per section 1):

- ACTIVATED - match SubscriptionCheckout (or an existing Subscription)
  by external_subscription_id. No local Subscription yet -> create one
  via the existing SubscriptionService.create_subscription, set
  external_subscription_id. Already ACTIVE -> no-op. TRIALING/PAST_DUE
  -> transition to ACTIVE. CANCELED -> log, no-op (a canceled
  subscription doesn't reactivate from a stray event).
- CHARGED - match Subscription. Update billing period fields (verify
  the exact NormalizedEvent/raw_payload shape for period dates - don't
  assume). PAST_DUE/TRIALING -> ACTIVE. No match -> log, mark
  processed, no crash.
- CANCELLED - match Subscription. Already CANCELED -> no-op. Else
  transition to CANCELED.
- PAYMENT_TROUBLE - match Subscription. ACTIVE -> PAST_DUE. Already
  PAST_DUE/CANCELED -> no-op.
- UNKNOWN - safe logged no-op, processed=True, no state change. This is
  the normalized equivalent of the original plan's "any other event
  type" handling - now a single case instead of an open-ended list,
  since the adapter already funneled everything unrecognized into
  UNKNOWN.

### 4.3 Processing trigger + retry — carried over from section 2

Synchronous inline processing after WebhookService.record_event,
failure caught and logged (never affecting the HTTP response), plus a
management command for retry/backfill of processed=False rows.

## 5. Files Likely Affected

```
new:      apps/billing/migrations/... (Subscription.external_subscription_id)
          the event-processing logic (services.py, following the
                                       existing pattern)
          the management command
          tests for all of the above
modified: apps/billing/models.py
          apps/billing/views.py (wiring processing into the webhook flow)
```

No frontend change - the ephemeral "processing" UI from D2 stays as-is;
a page reload after this stage activates a subscription will correctly
show it, since existing pages already render whatever Subscription
state actually exists.

## 6-9. Business rules, security, edge cases, tests

Carry forward the original D3 plan's content for these sections
essentially unchanged - the domain reasoning (idempotency guarantees,
the unmatched-event-id edge case, the "reprocessing twice must be a
no-op" test requirement, the webhook-response-stays-200-under-failure
test) was sound and doesn't change just because the input is now
normalized. Re-verify field names against the current (post-refactor)
code rather than assuming the original plan's exact code excerpts still
apply verbatim.

## 10. Acceptance Criteria

1. manage.py test - full count reported (baseline 176).
2. Report: confirmation the processing-trigger approach (section 2) was
   re-verified against the current code, and that every EventType case
   in section 4.2 is handled.
3. Manual, synthetic verification against the running dev server: a
   fabricated WebhookEvent with event_type=EventType.ACTIVATED (created
   directly, or via a hand-signed webhook POST through the real
   adapter) correctly creates a real Subscription; reprocessing is a
   no-op.
4. Live walkthrough: still pending, per section 0.
5. git status - no unrelated file changed.

## 11. Must NOT Do

- Do not reintroduce any provider-specific event-name knowledge into
  this stage's handlers - switch on EventType only.
- Do not modify the adapter interface, RazorpayGatewayAdapter, or
  MockGatewayAdapter.
- Do not build D4, D5-D8.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-d3-v2-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.

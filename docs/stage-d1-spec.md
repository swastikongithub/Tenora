# Claude Code Implementation Specification — Stage D1: Razorpay Foundation

**Scope:** the foundation Stage D builds on — Razorpay SDK + credentials
wired in, each local `Plan` mapped to a real Razorpay Plan, and a webhook
endpoint that correctly **receives and verifies** real Razorpay events
(signature-checked, stored, deduplicated by event ID) — but does not yet
turn those events into subscription state changes.

**This is D1 of an N-stage sequence. Do not attempt subscription creation,
checkout, event-driven state changes, usage metering, proration, Celery, or
reconciliation in this stage** — each of those gets its own spec, scoped
once D1's real shape is known. Building ahead of that would repeat the
mistake this project has consistently avoided (see: C1 deferring Table's
mobile transform until C4 had a real page to build it against).

---

## 0. Prerequisites (your action, not Claude Code's)

Two things must exist before this stage can be tested end-to-end:

1. **A Razorpay account with test-mode API keys.** Sign up at
   [razorpay.com](https://razorpay.com), switch to **Test Mode** (toggle in
   the dashboard — critical, never use live keys for development), then
   **Settings → API Keys** to generate a `Key ID` and `Key Secret`.
2. **A webhook secret.** **Settings → Webhooks → Add New Webhook** — you'll
   need a public URL to register here (see below), and Razorpay will show
   you a secret to enter that's used to verify signatures. Save both.
3. **A tunnel tool for local webhook delivery** (e.g. `ngrok`) — Razorpay,
   unlike Stripe, has no first-party CLI forwarder equivalent to
   `stripe listen`, so testing a real webhook against your local dev server
   requires exposing it via a public tunnel URL, which is what you register
   in step 2.

Add to `.env`:
```
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
```

Check whether these are set before starting; if not, stop and report it as
a blocker, same as the Docker and Google OAuth prerequisite checks.

## 1. Objective

Every subsequent D-stage depends on three things existing correctly: the
SDK being wired in, each `Plan` having a corresponding Razorpay-side Plan
ID to reference when creating subscriptions later, and a webhook endpoint
that's already proven to correctly verify signatures and deduplicate
events — the exact mechanism `WebhookEvent`'s unique-constraint pattern
(already proven once in this codebase, for JWT refresh-token blacklisting
in C3 §0.2) needs to work correctly before anything is built on top of it.

**Two distinct signatures exist in Razorpay's model — do not confuse
them.** The **webhook** signature (`X-Razorpay-Signature` header,
HMAC-SHA256 over the **raw** request body, keyed with the webhook secret)
is completely different from the **checkout success** signature (computed
over `order_id|payment_id`, keyed with the API secret) that a future stage
will handle on the frontend. This stage only deals with the webhook
signature — verify against Razorpay's current documentation before
implementing, don't assume the exact header/algorithm from memory.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md            — Stage D's original outline (written
                                          around Stripe, now Razorpay) —
                                          read for the overall shape, but
                                          this spec is authoritative for D1
                                          specifically
apps/billing/models.py                 — Plan — where the new
                                          razorpay_plan_id field goes
apps/billing/services.py               — existing service-layer pattern
                                          (SubscriptionService,
                                          transaction.atomic usage) — new
                                          Razorpay-related logic should
                                          follow this same shape
apps/users/services.py, auth.py        — the token-blacklist / email-
                                          verification-token patterns —
                                          both are precedent for
                                          "DB-backed, unique-constrained,
                                          real state" over anything
                                          stateless — WebhookEvent follows
                                          the same philosophy
requirements/base.txt                  — confirm no Razorpay SDK is
                                          installed yet
```

Current state: full core product + all deferred stages (Docker, email
verification, Google Sign-In, Platform Admin, cancellation) complete and
committed. Backend 120/120, frontend 279/279.

## 3. Existing Functionality That Must Not Change

- No existing endpoint, model, or service changes behavior. This stage is
  purely additive — new fields, a new model, one new endpoint.
- All existing tests must still pass.
- `Subscription`'s existing state machine (`LEGAL_TRANSITIONS`,
  `transition_status`) is untouched — this stage doesn't yet wire any
  webhook event into it (that's a later stage).

## 4. Required Changes

### 4.1 Razorpay SDK + configuration

Add the official `razorpay` Python SDK to `requirements/base.txt`. Read
`RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/`RAZORPAY_WEBHOOK_SECRET` from
environment variables in `config/settings.py`, following the exact pattern
already established for `GOOGLE_OAUTH_CLIENT_ID` (empty-string default, so
a misconfigured deployment fails closed rather than crashing).

### 4.2 `Plan.razorpay_plan_id`

Add a nullable, unique-when-set field to `Plan` for the corresponding
Razorpay-side Plan ID. A management command (or a small idempotent
service function, check-then-create) that ensures every local `Plan`
without a `razorpay_plan_id` gets a real Razorpay Plan created via the SDK
and the returned ID stored — safe to run repeatedly, never creating a
duplicate Razorpay-side Plan for a local Plan that already has one.

### 4.3 `WebhookEvent` model

```
- razorpay_event_id (unique — this is the entire idempotency guarantee,
  same pattern as OutstandingToken/EmailVerificationToken's
  DB-backed-uniqueness philosophy, not a stateless dedup trick)
- event_type (the Razorpay event name, e.g. "subscription.activated")
- raw_payload (the full body, stored for later processing/debugging)
- received_at
- processed (boolean, default False — this stage stores and verifies;
  turning `processed` events into real state changes is a later stage's
  job, not this one's)
```

### 4.4 Webhook endpoint

```
POST /api/webhooks/razorpay/
```

- Verify `X-Razorpay-Signature` against the **raw** request body (not
  re-serialized JSON — signature verification must happen on the exact
  bytes received, before any parsing) using `RAZORPAY_WEBHOOK_SECRET`,
  timing-safe comparison (`hmac.compare_digest`, not `==`).
- A failed signature check → 400, don't process, don't store.
- A valid signature: attempt to create a `WebhookEvent` row keyed by the
  event's ID. If a row with that ID already exists (Razorpay may deliver
  the same event more than once, which their own docs describe as
  expected behavior, not a bug), return 200 without creating a duplicate —
  this is the idempotency guarantee, proven by a unique-constraint
  collision, not by checking-then-inserting non-atomically.
- This endpoint does **not** call any part of `SubscriptionService` yet —
  it stores the verified, deduplicated event and returns. Wiring events
  into actual state changes is explicitly a later stage.
- No authentication required (Razorpay calls this directly, there's no
  user session) — but the signature check **is** the authentication
  mechanism; make sure it's not accidentally skippable.

## 5. Files Likely Affected

```
new:      apps/billing/migrations/... (Plan.razorpay_plan_id,
                                        WebhookEvent model)
          the webhook view + its tests
          a management command (or service function) for Plan sync
          tests for all of the above
modified: apps/billing/models.py
          requirements/base.txt
          config/settings.py
          config/urls.py
```

No frontend change in this stage.

## 6. Business Rules

- No `WebhookEvent` is ever processed twice — the unique constraint on
  `razorpay_event_id` is the real guarantee, not application-level
  checking alone.
- Signature verification happens on the raw body, always, before any
  parsing or processing.

## 7. Security Requirements

- Timing-safe signature comparison, not a plain string `==`.
- Real webhook secret from environment, never hardcoded, never logged.
- The raw payload is stored for debugging, but verify it doesn't contain
  anything that shouldn't be persisted (report if Razorpay's payloads
  include anything sensitive worth redacting before storage).

## 8. Edge Cases

- The same event delivered twice (a documented, expected Razorpay
  behavior, not a bug on either side) — second delivery returns 200,
  no duplicate row, verified by an actual test asserting a second POST
  with the same event ID doesn't create a second `WebhookEvent`.
- A malformed or missing signature header — clean 400, not a crash.
- Running the Plan-sync command twice — no duplicate Razorpay-side Plans
  created for Plans that already have a `razorpay_plan_id`.

## 9. Tests Required

- Signature verification: valid signature accepted, invalid rejected,
  missing header rejected.
- Duplicate event ID: second delivery is a no-op, first delivery's row
  is unaffected.
- Plan sync: creates Razorpay Plans for local Plans lacking one; running
  twice doesn't duplicate.
- Mock the Razorpay SDK calls in tests — no real network calls to
  Razorpay's API in the automated suite.

## 10. Acceptance Criteria

1. `manage.py check`, `manage.py test` — full count reported.
2. Manual verification: using the tunnel tool from §0, trigger a real
   test-mode webhook from Razorpay's dashboard (they typically offer a
   "send test webhook" feature) and confirm it's received, verified, and
   stored correctly — this is the one thing automated tests can't fully
   substitute for, same category as the Google Sign-In real-account
   walkthrough.
3. Confirm the Plan-sync command works against real Razorpay test-mode
   API keys, not just mocked tests.
4. `git status` — no unrelated file changed.
5. Report: which Razorpay SDK version was used, confirmation the
   signature check was verified against Razorpay's current documentation
   (not assumed from memory), and the real webhook event type(s) observed
   during manual testing.

## 11. Must NOT Do

- Do not build subscription creation, checkout, or any frontend change —
  later stages.
- Do not wire any webhook event into `SubscriptionService` or any state
  change — later stages.
- Do not build usage metering, proration, Celery, or reconciliation.
- Do not use live Razorpay API keys anywhere in this stage.
- Do not weaken any existing test.

---

## Workflow

Confirm the prerequisites (§0) before anything else. Then produce a plan
and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

```
Read docs/stage-d1-spec.md, then check whether RAZORPAY_KEY_ID,
RAZORPAY_KEY_SECRET, and RAZORPAY_WEBHOOK_SECRET are available (§0).
Report the result. If available, inspect the repository and produce an
implementation plan, then wait for my approval before writing any code.
```

# Multi-Tenant SaaS Billing Engine

Django + DRF multi-tenant SaaS billing platform. Portfolio project — the engineering
problems (tenant isolation, idempotency, concurrency correctness, reconciliation) are
the point, not feature count or UI polish.

Full specification: `docs/project-master-spec.md`
UI specification: `docs/ui-design-specification.md`

## Architecture rules — do not violate

These were each deliberated and corrected during design. Do not "fix" them back.

- **Tenant resolution lives in `TenantJWTAuthentication` (a DRF authentication class),
  NEVER Django middleware.** SimpleJWT authenticates at the DRF layer, which runs after
  Django's middleware stack — middleware cannot rely on `request.user` being populated.
- **`GLOBAL_PATHS` is an exact-match frozenset, never prefix matching.** A prefix would
  silently exempt every future sub-route from tenant resolution. This is a security control.
- **All tenant-owned querysets go through `TenantScopedManager.for_tenant(tenant)`.**
  No ad hoc `.filter(tenant=...)` at call sites. The manager takes tenant explicitly —
  never infer it from thread-local or global state.
- **`tenant_id` is NEVER accepted from a request body, on any endpoint.** Tenant comes
  only from the `X-Tenant-ID` header + Membership resolution.
- **Cross-tenant object access returns 404, never 403.** A 403 confirms the object exists.
- **Status codes:** missing/malformed `X-Tenant-ID` → 400 (custom `TenantHeaderRequired`,
  not `AuthenticationFailed`, which maps to 401). Valid header but no Membership → 403.
- **All mutations go through services.** No business logic in serializers or views.
  Views and serializers stay thin.
- **The billing domain never imports a payment provider's SDK directly.** Every
  external call (create plan/subscription, verify webhook/checkout signatures,
  parse+normalize a webhook) goes through `apps.billing.gateway.get_gateway()`,
  which returns the adapter named by `settings.PAYMENT_GATEWAY` (`razorpay` |
  `mock`). All Razorpay-specific SDK calls, HMAC constructions, header names and
  event-name→`EventType` mapping live in `apps.billing.gateway.razorpay` — the
  one and only module that imports `razorpay`. Tests use `MockGatewayAdapter`
  (via `@override_settings(PAYMENT_GATEWAY="mock")` or patching `get_gateway`).
- **Subscription status changes only via `SubscriptionService`.** Never assign
  `.status = ...` directly. Legal transitions are an explicit table. `CANCELED` is
  terminal — no reactivation exists.
- **A local `Subscription` row is NEVER created from anything a client reports.**
  Since D2, subscribing goes: `POST /api/subscriptions/current/checkout/` creates a
  real Razorpay Subscription + a `SubscriptionCheckout` row (an in-flight checkout,
  NOT a subscription state — `Subscription.Status` was deliberately not extended);
  `POST /api/subscriptions/current/confirm-checkout/` only verifies the checkout
  handshake for UI feedback. The local row is created later by D3 processing the
  verified `ACTIVATED` webhook. `POST /api/subscriptions/current/` (the Phase-1
  direct create) was removed. Double-click safety in
  `CheckoutService.create_checkout` is a `select_for_update()` on the tenant's
  `SubscriptionCheckout` row (gateway create has no idempotency key).
- **The checkout success signature is a DIFFERENT signature from the webhook one:**
  for Razorpay, HMAC-SHA256 of `f"{payment_id}|{subscription_id}"` (payment_id
  first — verified against Razorpay's SDK, the D2 spec text had it reversed) keyed
  with `RAZORPAY_KEY_SECRET` (the API secret, not the webhook secret), in
  `RazorpayGatewayAdapter.verify_checkout_signature`, timing-safe. The
  `subscription_id` hashed is the one from our `SubscriptionCheckout` record, not
  the client's request body (and the body's value must match it).
- **`IntegrityError` from a unique constraint must be caught OUTSIDE the
  `transaction.atomic()` block that raised it** (or via a nested savepoint). Postgres
  marks the transaction broken once the error escapes; continuing to use it raises
  `TransactionManagementError`. The DB constraint — not a pre-check — is the real
  concurrency guarantee.
- **Never store card numbers, CVV, or expiry.** Razorpay owns payment collection
  (the payment processor for this project — the master spec's older "Stripe"
  references predate that decision; see `docs/stage-d1-spec.md`).
- **The webhook signature is verified on the RAW request body** (bytes, read
  before any parsing), via `get_gateway().verify_webhook_signature(headers,
  raw_body)`. For Razorpay: HMAC-SHA256 of the raw body, timing-safe compare,
  keyed with `RAZORPAY_WEBHOOK_SECRET`, hand-rolled (not the SDK helper, which
  raises instead of returning). A failed check → 400, nothing stored.
  `WebhookEvent.external_event_id` (the gateway's per-delivery id — for Razorpay,
  the `X-Razorpay-Event-Id` header) is `unique`, and that constraint — not an
  app-level check — is the entire webhook-idempotency guarantee.
  `WebhookEvent.event_type` stores the project's `EventType` vocabulary (the
  adapter's `parse_webhook_event` does the mapping); the raw provider event name
  stays in `raw_payload`.
- **Money is `price_cents` (integer) + `currency`.** Never floats. Never a hardcoded `$`.
  Razorpay's `amount` is the smallest currency unit (cents for USD), so `price_cents`
  maps to it directly.
- **`User.email_verified` is never reused as/for `is_active`.** They are distinct concepts —
  `is_active` means administratively disabled; `email_verified` means the mailbox was never
  confirmed. Only `EmailVerificationService.verify()` (or the one-time grandfathering
  migration for pre-existing rows) may set it `True`.
- **Login (`apps.users.auth.EmailVerifiedTokenObtainPairSerializer`) never returns a
  distinguishable error for "wrong password" vs. "correct password, unverified account."**
  Byte-identical `AuthenticationFailed` body both times — verified by an explicit test, not
  an assumption. Verification-token failures (invalid/expired/already-used) collapse to one
  generic 400 the same way.
- **Verification/transactional email uses Django's console `EMAIL_BACKEND`** (prints to
  the terminal/log) **— deliberately, not an oversight.** No real provider (SES/Postmark/
  SendGrid) is configured; that is a separate, later decision if this project ever needs
  actual delivered email. See `docs/email-verification-spec.md` §4.6.

## Commands

```
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py test
```

## Working agreement

- Inspect the actual repository before implementing. If the repo contradicts the spec,
  report the discrepancy — do not silently pick one.
- One feature per session. Produce a plan and wait for approval before writing code.
- Run the tests and report real output. "Should pass" is not "passed".
- Never weaken or modify existing tests to make new code pass.
- Phase 1's test matrix is green, and Phase 2 is in progress. Shipped so far, each
  against its own spec: **D1** (Razorpay foundation — SDK, `Plan.external_plan_id` +
  sync command, receive/verify/dedup webhook endpoint), the **payment-gateway adapter
  refactor** (`apps.billing.gateway`), **D2** (checkout — `SubscriptionCheckout`, no
  `POST /api/subscriptions/current/`), and **D3** (`docs/stage-d3-v2-spec.md` — the
  webhook endpoint now drives `SubscriptionService` state changes inline via
  `WebhookProcessingService.process_event`, switching on `EventType` only;
  `Subscription.external_subscription_id` correlates later events; `manage.py
  process_webhook_events` is the retry/backfill path). Everything past D3 — usage
  metering, Celery, proration, reconciliation, out-of-order hardening (D4) — still
  waits for its own spec; do not build ahead of that.

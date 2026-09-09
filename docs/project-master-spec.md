# Multi-Tenant SaaS Billing Engine — Project Master Specification

**Status:** Canonical reference. Supersedes the earlier `billing-engine-master-spec.md` in structure (reorganized into the taxonomy below) — no architectural content has been changed, only reorganized and extended with risk analysis that wasn't previously written down.

**Roles:** Claude (this document) = Product Architect / Technical Architect. Claude Code = implementation engineer, works against this spec, inspects the actual repository before implementing, flags discrepancies rather than silently resolving them.

---

# A. LOCKED DECISIONS

These were each deliberated (and in several cases corrected once) during design. Treat as settled — do not re-litigate without a stated reason and an explicit "previous decision / new decision / why / impact" note.

## A.1 Tenant Resolution & Authentication
1. Tenant resolution lives in a custom DRF `JWTAuthentication` subclass (`TenantJWTAuthentication`), **not** Django middleware. Reason: SimpleJWT authenticates at the DRF layer (`perform_authentication`), which runs after Django's middleware stack — middleware cannot reliably assume `request.user` is populated.
2. `X-Tenant-ID` is a per-request header, not baked into the JWT. Reason: supports a user belonging to multiple tenants without re-issuing tokens to switch context.
3. `GLOBAL_PATHS` (endpoints exempt from tenant resolution) is an **exact-match frozenset of literal paths**, not a prefix list. Reason: a prefix like `/api/tenants/` would silently exempt every future sub-route created under it.
4. Status code contract: missing/malformed `X-Tenant-ID` → **400**; valid header but no `Membership` → **403**; foreign-tenant object access → **404** (never 403 — a 403 would confirm the object exists).
5. `request.tenant` / `request.membership` are attached to `request._request` during authentication and read via DRF's standard `Request.__getattr__` proxying to the wrapped `HttpRequest` — confirmed correct DRF behavior, not a workaround.

## A.2 Tenant Isolation
6. `TenantScopedManager.for_tenant(tenant)` is the only mechanism for filtering tenant-owned querysets. No ad hoc `.filter(tenant=...)` at call sites.
7. The manager takes `tenant` as an **explicit argument** — never inferred from thread-local/global state. Reason: explicit passing makes a missing-context bug loud (an error) instead of silent (wrong or unscoped data).
8. `tenant_id` is **never** accepted as a request body field, on any endpoint, anywhere in the system.
9. `Membership` uses `TenantScopedManager` (added specifically to support `GET /api/memberships/` — it is unambiguously tenant-owned data).

## A.3 Data Model
10. `Subscription.tenant` is a `OneToOneField`, not a `ForeignKey` + separate unique constraint — the domain rule (one tenant : one subscription, Phase 1) is modeled directly.
11. `Plan.currency` is explicit from Phase 1 (not assumed USD).
12. UUIDs are used as primary keys throughout, explicitly treated as **identifiers, not an authorization mechanism**.

## A.4 Business Logic
13. All subscription mutations go through `SubscriptionService`; no direct `.status = ...` assignment anywhere else.
14. Legal subscription state transitions are an explicit table (see §B.5), not implicit/arbitrary.
15. Membership creation (`POST /api/memberships/`) is OWNER-only, can only assign `MEMBER` (never `OWNER`, even if the request body contains `"role": "OWNER"`), and adds an **existing** user by email — this is not an invitation system (no token/expiry/acceptance flow) and should not become one in Phase 1.
16. Duplicate-membership handling must be concurrency-safe via the DB's `UNIQUE(user, tenant)` constraint, with `IntegrityError` caught **outside** the `transaction.atomic()` block that raised it (or via a nested savepoint) — never caught inside the same block that raised it, since Postgres marks that transaction broken once the error escapes.

## A.5 Phase 2 Principles (decided, not yet implemented)
17. Webhook idempotency will rely on a unique constraint on `stripe_event_id` — same "the DB constraint is the real guarantee, the pre-check is a nicety" principle as membership duplicates.
18. Usage-ingestion idempotency (Phase 2) is a **distinct problem** from webhook idempotency, requiring its own idempotency key — not the same mechanism reused.
19. Stripe is never the source of truth for local state; the system maintains its own billing state and stores Stripe IDs as external references.
20. Sequencing: domain model and Stripe-independent logic (Phase 1) must be solid before Stripe integration begins — not the reverse.

---

# B. CURRENT REQUIREMENTS

## B.1 Product Requirements
- Portfolio project demonstrating serious backend engineering, alongside an existing Node.js project (Email Job Scheduler / ReachInbox — BullMQ, Redis, rate limiting, deterministic job IDs).
- Django chosen specifically to re-demonstrate the same systems concepts (idempotency, rate limiting, concurrency) in a second stack.
- Priority order for engineering focus (explicit): correctness → security → multi-tenant isolation → data integrity → idempotency → concurrency correctness → reliability → maintainability → testability → performance → UI quality.
- Explicitly out of scope regardless of how good it would look: fancy landing page, elaborate animations, 15-chart dashboard, profile customization, social login, chat, generic admin panel, incidental CRUD sprawl.
- "CV-ready" tiers:
  - **Must have:** Django+DRF, PostgreSQL, multi-tenancy + isolation, OWNER/MEMBER RBAC, subscription plans, Stripe integration, webhook signature verification + idempotency, tests proving duplicate-webhook safety.
  - **Strong additions:** usage metering, usage-ingestion idempotency, proration, Celery, reconciliation.
  - **Nice-to-have:** metrics/observability, tracing, elaborate frontend, sophisticated admin UI.
- Five "killer demo" scenarios that define done better than a feature checklist:
  1. Cross-tenant access → 404, never 403.
  2. Duplicate Stripe webhook sent twice → processed exactly once.
  3. 100 concurrent usage-ingestion requests → exactly 100 records.
  4. Failed payment → `PAST_DUE` → Celery retry → back to `ACTIVE`.
  5. Deliberately corrupted local state → caught by reconciliation.

## B.2 Technical Architecture

```
Client
  │  Authorization: Bearer <JWT>
  │  X-Tenant-ID: <uuid>          (tenant-scoped endpoints only)
  ▼
TenantJWTAuthentication  (DRF authentication layer)
  ▼
DRF Permissions (IsTenantMember / IsTenantOwner)
  ▼
ViewSet / View  (thin — no business logic)
  ▼
Service layer  (all mutations)
  ▼
TenantScopedManager  (.for_tenant(tenant))
  ▼
PostgreSQL
```

Layer responsibilities are a hard rule: Authentication = identity + tenant context only. Permissions = what a role can *do*. Managers = what rows a query can *see*. Services = all mutation/business logic. This separation exists so that Phase 2's multi-system operations (DB + Stripe + webhook state + Celery) have a natural home instead of being trapped in a serializer.

## B.3 Django Architecture

```
billing-engine/
├── config/                  # settings, urls, wsgi, asgi
├── apps/
│   ├── users/                # custom User model
│   ├── tenants/               # Tenant, Membership, tenant-scoping infra, auth, permissions
│   ├── billing/                # Plan, Subscription (+ later: UsageRecord, Invoice, Payment, WebhookEvent)
│   └── api/                   # mentioned once early, purpose undefined — see §E
├── requirements/
├── manage.py
```

`apps/tenants` owns cross-cutting tenant infrastructure so `apps/billing` (and any future tenant-owned app) can reuse it without duplication.

## B.4 Database Design

**Built (Phase 1 core):**

`User` (`apps/users`) — `AUTH_USER_MODEL = "users.User"`
- `id` UUID pk, `email` unique (`USERNAME_FIELD`), `username = None`.

`Tenant` (`apps/tenants`)
- `id` UUID pk, `name`, `slug` unique, `created_at`, `is_active`.

`Membership` (`apps/tenants`) — join of `User` ↔ `Tenant`
- `id` UUID pk, `user` FK, `tenant` FK, `role` (`OWNER`/`MEMBER`), `created_at`.
- `UNIQUE(user_id, tenant_id)`; index on `tenant_id`; uses `TenantScopedManager`.

`Plan` (`apps/billing`) — **global**, not tenant-owned
- `id` UUID pk, `name`, `code` unique, `price_cents` (int, never float), `currency` (3-char, e.g. "USD"), `is_active`.

`Subscription` (`apps/billing`) — tenant-owned
- `id` UUID pk, `tenant` **OneToOneField** → Tenant, `plan` FK (PROTECT), `status` (TRIALING/ACTIVE/PAST_DUE/CANCELED), `current_period_start`, `current_period_end`, `created_at`, `updated_at`.
- Uses `TenantScopedManager`; index on `tenant_id`.

**Planned, named but not fully specified (Phase 2+):**
- `UsageRecord` — tenant-owned; known required field: `idempotency_key`.
- `Invoice`, `InvoiceItem` — tenant-owned; fields not yet specified.
- `Payment` — tenant-owned; fields not yet specified.
- `WebhookEvent` — known required fields: `stripe_event_id` (unique), `event_type`, `payload`, `status`, `received_at`, `processed_at`, `attempt_count`.

**Relationships:**
```
User ──< Membership >── Tenant ── OneToOne ── Subscription ──FK── Plan
```

## B.5 Billing / Subscription State Machine

```
TRIALING → ACTIVE
TRIALING → CANCELED
ACTIVE   → PAST_DUE
ACTIVE   → CANCELED
PAST_DUE → ACTIVE
PAST_DUE → CANCELED
CANCELED → [terminal]
```
`CANCELED → ACTIVE` (reactivation) is explicitly not a Phase 1 transition. Enforced only through `SubscriptionService` (`create_subscription`, `transition_status`, `change_plan`, `cancel_subscription`).

## B.6 Authentication & Authorization

See A.1 for the locked mechanism. Roles: `OWNER`, `MEMBER`.
- OWNER: manage subscription (create/change plan/cancel), manage members (add/list), view billing.
- MEMBER: view subscription, view tenant resources, list members. Cannot mutate subscription or add members.
- `IsTenantMember` / `IsTenantOwner` read from `request.membership` as resolved by authentication — never re-query.

**UI coverage of the OWNER subscription capabilities.** All three are now
exposed. Stage C5 shipped **create** and **change plan**; **cancel** shipped
2026-09-07 (`docs/cancellation-spec.md`) as an OWNER-only **type-to-confirm**
flow on the Subscription & Plans page — a danger-zone control that opens a modal
requiring the workspace name to be typed before the destructive button enables
(the GitHub repo-deletion pattern), since this is the only irreversible
transition in §B.5. It calls `PATCH /api/subscriptions/current/
{status: "CANCELED"}` through the view's existing status branch; no backend
production change was needed (permission, validation, and the `LEGAL_TRANSITIONS`
guard were already in place — three new API tests lock the contract by name).
`SubscriptionService.cancel_subscription` remains defined but unused — the view
path goes through `transition_status` directly, like every other transition.

**Known gap (not a Phase 1 blocker):** cancellation is *fully* terminal via the
API. A `CANCELED` row keeps the tenant's `Subscription` OneToOne slot, `POST
/api/subscriptions/current/` then returns `400` (`SubscriptionAlreadyExists`),
and there is no `DELETE` route — so there is currently **no way for an OWNER to
start a fresh subscription after cancelling**. The cancellation UI copy states
this honestly rather than implying a path that doesn't exist. A reset/replace
endpoint is a deliberate later decision (Stage D territory), not an oversight.

## B.7 API Contracts (Phase 1)

**Global (no `X-Tenant-ID`):**
```
POST   /api/auth/login/                  (email-verification stage — EmailVerifiedTokenObtainPairView, wired, tested)
POST   /api/auth/refresh/                (SimpleJWT built-in — wired)
POST   /api/auth/register/               (B1, extended by email-verification stage — wired, tested)
POST   /api/auth/logout/                 (C3 §0.2 — wired, tested)
POST   /api/auth/verify-email/           (email-verification stage — wired, tested)
POST   /api/auth/resend-verification/    (email-verification stage — wired, tested)
GET    /api/users/me/                    (C3 §0.1 — wired, tested)
POST   /api/tenants/                     (B1 — wired, tested)
GET    /api/tenants/me/                  (B1 — wired, tested)
GET    /api/plans/                       (B2 — wired, tested)
GET    /api/platform/tenants/            (platform-admin stage — wired, tested; IsPlatformStaff, deliberately cross-tenant)
GET    /api/platform/stats/              (platform-admin stage — wired, tested; IsPlatformStaff, deliberately cross-tenant)
```

**Email verification (`docs/email-verification-spec.md`, shipped).** Registering
leaves `User.email_verified=False`; `EmailVerifiedTokenObtainPairSerializer`
(`apps/users/auth.py`) refuses password login until a real, DB-backed, single-use
`EmailVerificationToken` (SHA-256-hashed at rest, 24h TTL) is redeemed at
`/api/auth/verify-email/`. Login's failure body is byte-identical for
wrong-password and unverified-account (verified by an explicit test comparing
both response bodies, not just status codes) — the non-disclosure principle from
§B.6/§7 login errors is extended, not weakened. `resend-verification` returns an
identical 200 regardless of whether the account exists, is already verified, or a
token was genuinely sent. Pre-existing users (including every seeded demo
account) were grandfathered as verified by a data migration shipped in the same
deployable unit as the field — tested against actually-migrated data via
`MigrationExecutor`, not assumed. `register` and `resend-verification` are
rate-limited (`ScopedRateThrottle`); nothing else on the platform is throttled.
Email delivery is Django's console backend (prints, doesn't send) — a deliberate
scope boundary, see CLAUDE.md and the spec's §4.6; a real provider is a separate,
later decision. `is_active` is untouched — `email_verified` is a new, distinct
field, never conflated with it.

**Tenant-scoped (`X-Tenant-ID` required):**
```
GET    /api/memberships/                 (B1 — wired, tested)
POST   /api/memberships/                 (B1 — wired, tested)
GET    /api/subscriptions/current/                (B2 — wired, tested)
PATCH  /api/subscriptions/current/                (B2 — wired, tested; plan change + cancel)
POST   /api/subscriptions/current/checkout/        (D2 — wired, tested; OWNER starts a
                                                    Razorpay Subscription; creates NO local row)
POST   /api/subscriptions/current/confirm-checkout/(D2 — wired, tested; verifies Checkout's
                                                    success signature; creates NO local row)
```
`POST /api/subscriptions/current/` (the Phase-1 direct create) was **removed in D2** —
creating a local `Subscription` from a client action would fabricate a paid state.

**Unauthenticated (signature-verified):**
```
POST   /api/webhooks/razorpay/           (D1 — wired, tested; no session, the
                                          X-Razorpay-Signature HMAC check IS the auth)
```

**Stage D is Razorpay, not Stripe.** §B.9/§B.10 and the "killer demo" list below
were written around Stripe; the payment processor is now Razorpay
(`docs/stage-d1-spec.md`). **Stage D1 (shipped)** is the foundation only: the
`razorpay` SDK wired in, `Plan.razorpay_plan_id` + a `sync_razorpay_plans`
management command mapping each local `Plan` to a real Razorpay Plan, and a
`WebhookEvent` model + `POST /api/webhooks/razorpay/` that verifies the
`X-Razorpay-Signature` HMAC against the **raw** body and deduplicates by the
`X-Razorpay-Event-Id` header (unique constraint = the whole idempotency
guarantee, same pattern as `OutstandingToken`). D1 does **not** turn any webhook
event into a subscription state change — that, plus usage metering, Celery,
proration and reconciliation, each get their own later spec.

**Stage D2 (shipped)** adds real checkout. `POST .../checkout/` creates a Razorpay
Subscription (`total_count` 120 for monthly / 10 for annual ≈ 10 years) tied to the
plan's `razorpay_plan_id`, tracked by a new `SubscriptionCheckout` model — a
separate model, **not** a `Subscription.Status` extension, so the B2 state machine
is untouched. OneToOne on tenant + `select_for_update()` in
`create_checkout` = at most one Razorpay Subscription per tenant even on a
double-click. `POST .../confirm-checkout/` verifies Razorpay Checkout's success
signature (HMAC of `payment_id|subscription_id` keyed with the **API** secret — a
different signature and key from D1's webhook one) and marks the checkout
`CONFIRMED` for UI feedback only. **No local `Subscription` row is created or
mutated anywhere in D2** — that waits for D3 wiring the normalized `ACTIVATED`
webhook event into `SubscriptionService.create_subscription`.

**Payment gateway adapter (shipped, `docs/payment-gateway-adapter-spec.md`).** A
pure refactor between D2 and D3: all of D1/D2's Razorpay logic (SDK calls, both
HMAC constructions, and the new event-name→vocabulary mapping) now lives behind
`apps.billing.gateway.PaymentGatewayAdapter` (an ABC) with two implementations —
`RazorpayGatewayAdapter` (the only module importing the `razorpay` SDK) and
`MockGatewayAdapter` (no network, used by the whole test suite and by local dev
with no credentials). `get_gateway()` picks one via `settings.PAYMENT_GATEWAY`.
The three provider-named fields were renamed generic while there's no production
data: `Plan.external_plan_id`, `SubscriptionCheckout.external_subscription_id`,
`WebhookEvent.external_event_id` (the `SubscriptionCheckoutSerializer` keeps the
JSON key `razorpay_subscription_id` so the frontend contract is unchanged).
`WebhookEvent.event_type` now stores the project's `EventType` vocabulary
(`ACTIVATED`/`CHARGED`/`CANCELLED`/`PAYMENT_TROUBLE`/`UNKNOWN`); the raw provider
event name is kept in `raw_payload`. No behaviour change to any endpoint.

**C3 §0.1 — `GET /api/users/me/`.** `IsAuthenticated`, global path. Returns `{id, email,
is_staff}` for the requesting user and nothing more — no tenant list (that is
`/api/tenants/me/`), no role, no PII. Closes the C2-reported gap where the JWT carries only
`user_id`, so nothing told the frontend who was logged in after a silent-refresh reload.
`is_staff` (added by the platform-admin stage via a `MeSerializer` subclass — the shared
`UserSerializer` and `POST /api/auth/register/`'s `{id, email}` body are unchanged) is what
lets the frontend decide whether to show the platform-admin dashboard at all.

**Platform-admin stage (`docs/platform-admin-spec.md`, shipped).** `GET
/api/platform/tenants/` and `GET /api/platform/stats/` — the one deliberate, documented
exception to tenant isolation. Both are global paths (no `X-Tenant-ID`: there is no single
tenant context for a platform-wide view) gated by a new `IsPlatformStaff` permission
(`apps/platform/permissions.py`, checks `request.user.is_staff` — the same flag Django admin
already uses, not a new field). A logged-in non-staff user gets 403, not 404. `tenants/`
lists every tenant regardless of membership, each with a `Count()` member annotation and a
`{plan_name, status}` subscription summary (or null). `stats/` returns ORM-computed
aggregates only — total tenants, subscription-status breakdown (every `Status` plus a
`NONE` bucket), plan distribution, and tenant signups per month (`TruncMonth`) — no
Python-side tallying, no fabricated numbers. Read-only; no endpoint here mutates anything.
The signature test (`apps/platform/tests/test_platform_views.py::
PlatformTenantListTests::test_platform_staff_sees_every_tenant_in_one_response`) is the
deliberate inverse of every `test_isolation.py` case: it asserts three tenants owned by
three different users come back in one response. Nothing about how existing tenant-scoped
endpoints resolve, authenticate, or authorize changed.

**C3 §0.2 — `POST /api/auth/logout/`.** `IsAuthenticated`, global path. Body `{refresh}`;
blacklists that refresh token via `RefreshToken(token).blacklist()` (the `token_blacklist`
app, installed since Stage A for rotation, gets its first logout use here). A malformed,
expired, wrong-type, or already-blacklisted token → 400, never 500 — logging out with a bad
token is a graceful no-op from the client's side. **Resolved (Stage C3):** closes the C2
gap where a refresh token stayed valid after logout; `test_logout.py` verifies the
blacklisted token genuinely fails at `/api/auth/refresh/` afterward, not merely that
`/logout/` returns 200.

## B.8 Multi-Tenant Isolation Rules

See A.2. Additionally: cross-tenant access must return 404 on **every verb** (GET/PATCH/DELETE), and any attempt to influence tenant scope via request body (e.g. a forged `tenant_id`) must have zero effect — proven by dedicated tests, not just documented as a rule.

## B.9 Stripe Integration (Phase 2 — planned)

```
Django → Create Customer → Create Checkout Session → Create Subscription → Stripe
```
Local state is authoritative; Stripe IDs (`stripe_customer_id`, `stripe_subscription_id`) are stored as references. Test matrix once built: new subscription, upgrade, cancellation, reactivation, failed payment.

## B.10 Webhook Architecture (Phase 2 — planned)

- `WebhookEvent.stripe_event_id` unique constraint → duplicate delivery returns 200 without reprocessing.
- Signature verification required before any processing.
- Event ordering: must not assume chronological arrival. Planned approach — compare against a "newer state" indicator (Stripe's event `created` timestamp, or the subscription object's own state) rather than trusting delivery order. **Exact mechanism undecided — see §E.**

## B.11 Idempotency Requirements

Two **separate** idempotency problems, each needing its own key:
1. Webhook idempotency — `stripe_event_id` unique constraint.
2. Usage-ingestion idempotency — a per-`UsageRecord` idempotency key (e.g. tenant + external request id).

## B.12 Concurrency Requirements

- 100 concurrent usage-ingestion requests → exactly 100 `UsageRecord`s. Tests must use genuine concurrent execution, not a sequential loop.
- Membership creation: DB `UNIQUE(user, tenant)` constraint is the real guarantee; `IntegrityError` must be caught outside the atomic block that raised it (see A.4.16).
- Webhook duplicates: same "constraint is the real guarantee" pattern as membership.

## B.13 Usage Metering (Phase 2 — **shipped, Stage D5**)

`UsageRecord`, immutable, tenant-owned. Illustrative (not locked) billing shape discussed: base price + included quota + overage rate.

**What shipped (D5, `docs/stage-d5-spec.md`):** the earlier "ingestion + per-record `idempotency_key`" design was superseded — the app has no real metered feature, so an ingestion API would require fabricated usage events (violates the no-fabrication rule). D5 instead **snapshots a real already-tracked resource**: `active_members`, a count of the tenant's `Membership` rows, recorded once per `Subscription` billing period by `UsageMeteringService.record_snapshot` and the `meter_usage` management command (manual trigger; D7 automates). Idempotency is the natural business key `UNIQUE(tenant, metric, period_start, period_end)`, not an external id — so B.11's "usage-ingestion idempotency key" and B.12's "100 concurrent ingestion requests → 100 records" do not apply; the guarantee tested is "snapshot the same period twice → one row". A tenant with no `Subscription` row is skipped (no invented period); status is not a gate (a `CANCELED` subscription's period is still metered).

## B.14 Background Jobs / Celery (Phase 2 — **shipped, Stage D7**)

Handles (eventual scope): invoice generation, usage aggregation, email notifications, retryable billing operations, periodic reconciliation.

**What shipped (D7, `docs/stage-d7-spec.md`):** Celery + a Redis broker (`config/celery.py`, `CELERY_BROKER_URL`), with **celery-beat** as the scheduling mechanism. Two periodic tasks in `apps/billing/tasks.py`, each a thin caller of a shared service method (not a reimplementation, not a wrapper around the CLI): `billing.process_webhook_events` **every 5 minutes** → `WebhookProcessingService.process_pending()` (the D4 `DEFERRED`-event retry sweep); `billing.meter_usage` **daily at 03:00 UTC** → `UsageMeteringService.snapshot_all_subscribed()` (D5 usage snapshot). The `process_webhook_events` / `meter_usage` management commands remain the manual entry points and now call the same service methods. Concurrent task-vs-command runs are safe by construction (the event-row `select_for_update` + `processed` guard; the `unique_usage_snapshot` constraint). **D3's inline webhook processing stays synchronous** — it already meets its correctness bar and making it async fixes nothing. Redis is a new manual-workflow prerequisite; the automated test suite runs tasks in-process (`CELERY_TASK_ALWAYS_EAGER` under `manage.py test`) and never needs a broker. No result backend yet (D8 adds one if it needs task results).

## B.15 Reconciliation (Phase 2 — **shipped, Stage D8**)

Periodic comparison of local subscription state vs. the provider's state; mismatches flagged. Demo: deliberately corrupt local state, show detection.

**What shipped (D8, `docs/stage-d8-spec.md`):** an hourly, **read-only** sweep — `billing.reconcile_subscriptions` (beat) and the `reconcile_subscriptions` management command, both thin callers of `ReconciliationService.reconcile_all()` (the D7 pattern). The adapter gained one method, `fetch_subscription_state(external_subscription_id) -> ProviderSubscriptionState | None`, raising `ProviderUnavailable`; `None` = the provider explicitly disowns the id (a genuine finding), the exception = an infra failure that is logged and **never recorded as drift**. The **frequency question** is resolved to hourly (a safety net for an event that never arrived; the 5-minute webhook sweep already covers "arrived but unprocessed"); the **auto-repair-vs-flag-only question** is resolved to **flag-only** — a mismatch appends an immutable `ReconciliationDiscrepancy` audit row (`STATUS_MISMATCH`, `LOCAL_CANCELED_PROVIDER_ACTIVE`, or `PROVIDER_NOT_FOUND`) with explicit `local_status`/`provider_status` columns, and nothing is corrected locally or written back to the provider. Only subscription **status** is compared: period dates are a synthesized local placeholder for much of a subscription's life (D3/D4) and the provider plan id diverges by design (D6's `change_plan` is local-only). Eligibility is every `Subscription` with an `external_subscription_id`; a locally-`CANCELED` one is still reconciled, because `local CANCELED / provider live` is the drift most worth catching. **The comparison mechanism is proven against `MockGatewayAdapter`; its actual value — catching real drift — is unproven and currently un-runnable, because the Razorpay Subscriptions account is still blocked and no dev subscription has a provider id yet.**

## B.16 Observability

Named as a "nice-to-have" tier item and as a v1.0 roadmap component ("Reconciliation + observability"), but **no specific observability requirements (logging format, metrics, tracing tool) have been discussed** — see §E.

## B.17 Testing Requirements

- **Unit:** proration calc, usage aggregation, billing calc, state transitions.
- **API:** authentication, permissions, tenant isolation, subscription endpoints, usage endpoints.
- **Integration:** Stripe webhook → DB, retry, duplicate webhook, failed payment, subscription update.
- **Concurrency:** genuine concurrent usage-ingestion requests, exact-count assertions.
- Built and must stay green, unweakened, as the codebase grows: `apps/tenants/tests/test_isolation.py` — GET/PATCH/DELETE foreign-tenant subscription → 404; forged body `tenant_id` never honored; missing header → 400; header for non-member tenant → 403. **Resolved (Stage B3):** `_auth_as()` now mints a real `AccessToken` and sends `Authorization: Bearer` + `X-Tenant-ID`, so `TenantJWTAuthentication` genuinely runs. The missing-header (→ 400 from `TenantHeaderRequired`), non-member (→ 403 from `PermissionDenied`), and forged-body tests now exercise the real auth→tenant-resolution pipeline. **Residual limitation:** the three foreign-*subscription* tests target `/api/subscriptions/<id>/`, which is not a wired route (only `/current/` exists), so their 404s come from Django's URL resolver, not from `TenantJWTAuthentication` + `TenantScopedManager`. Genuine object-level cross-tenant coverage needs a detail endpoint that Phase 1 does not define — see §F.1.
- Additional focus areas required per your workflow instructions: invalid input, duplicate operations, race conditions, transaction boundaries, webhook retries/ordering, subscription state transitions, usage limits, billing edge cases, failure recovery.

---

# C. UI/DESIGN SYSTEM

**Status: active.** The design system and page-by-page specs live in
`docs/ui-design-specification.md`, whose header records that it activates this section.
That document is the design authority: §C.1 fixes the palette, type scale, spacing,
radius and shadow tokens; the remaining sections cover the tenant switcher, page
inventory, security constraints, responsive rules and accessibility requirements. Do
not restate or fork those values here — this section keeps only the standing
constraints below and the tracked item that follows.

What was already true before the design work started, and still constrains it:
- Every UI element must map to a real model/service/endpoint already defined in §B, or to an explicitly approved future feature — no decorative or fabricated data.
- The UI should expose the engineering concepts (multi-tenancy, RBAC, idempotency, state transitions, reconciliation) rather than hide them behind a generic dashboard.
- No page should be designed "because it looks good" if it doesn't demonstrate real backend functionality — this cuts against building elaborate marketing/landing pages, matching the explicit scope exclusion in B.1.

**Tracked item — dev-only component showcase (Stage C1). Resolved (Stage C3).** C1
stood up the `frontend/` foundation (Vite + React + TS + Tailwind v4, the §C.1 tokens,
and eight component primitives) and, to give those primitives a surface before any real
page existed, a DEV-only component showcase at `frontend/src/dev/Showcase.tsx`. It was
development scaffolding, never product. **Stage C3 deleted it** (`src/dev/` and the
`/dev/showcase` route) once the first real pages — Login, Register, Workspace —
exercised the primitives for real. A route-table test (`showcase-removed.test.tsx`)
asserts the path no longer resolves. Recorded here the same way §B.17 records B3's known
limitation, so the lifecycle is visible to a reader of this spec alone.

---

# D. DEVELOPMENT ROADMAP

**Overall roadmap (agreed, stop at v1.0):**
```
v0.1  Django + PostgreSQL
v0.2  Multi-tenancy + RBAC
v0.3  Plans + subscriptions
v0.4  Stripe integration
v0.5  Idempotent webhooks
v0.6  Out-of-order event handling
v0.7  Usage metering
v0.8  Proration
v0.9  Celery + retries
v1.0  Reconciliation + observability
```

**Phase 1 internal sequencing and current status:**
1. ✅ Domain model + multi-tenancy core (models, `TenantScopedManager`, `TenantJWTAuthentication`, permissions, `SubscriptionService`, signature isolation test suite).
2. ✅ `config/settings.py` and `config/urls.py` — only `/api/auth/login/` and `/api/auth/refresh/` actually wired; nothing stubbed ahead of its view.
3. 🔄 **Current step:** Tenant API layer (`POST /api/tenants/`, `GET /api/tenants/me/`, `GET/POST /api/memberships/`). Implementation prompt finalized; **execution and review pending** — this is the next concrete action.
4. ⏳ Plan/Subscription API layer.
5. ⏳ Close the real-JWT integration test gap.
6. ⏳ Phase 2 (Stripe) begins only once Phase 1's full test matrix is green.

**Recommended cycle for every feature going forward (per your workflow instructions):**
```
Specification → Claude Code inspects repo → implementation plan → approval
→ implementation → tests → security/architecture review → fixes → commit
```
Applied incrementally, one independently testable feature at a time — never the whole application from one prompt.

---

# E. EXPLICITLY UNDECIDED ITEMS

- **Stripe event-ordering mechanism** — agreed conceptually ("compare against a newer-state indicator"), exact field/logic not decided.
- **`apps/api/`** — mentioned once in an early structure sketch, no defined purpose; unclear if still part of the plan.
- **View style for Tenant API layer** — `APIView` vs. DRF generic views/ViewSets, left as an implementation choice.
- **Membership-add logic location** — extend `TenantService` or add a separate `MembershipService`, left as an implementation choice.
- **Behavior when `POST /api/memberships/` targets a nonexistent email** — 404 vs. 400, explicitly left as "your call, but be consistent."
- **`python-dotenv`** is in `requirements/base.txt` but `settings.py` doesn't currently load a `.env` — noted, explicitly deferred.
- **Settings package split** (base/dev/prod) — deferred until there's an actual need to diverge environments.
- **Docker/docker-compose, Nginx/Gunicorn, OpenAPI/Swagger, pytest** — appeared in an early tech-stack proposal, not confirmed as committed requirements. Current `requirements/base.txt` contains only Django, DRF, SimpleJWT, psycopg2-binary, python-dotenv.
- **`UsageRecord`/`Invoice`/`InvoiceItem`/`Payment` exact field lists** beyond what's named in B.4.
- **Reconciliation job frequency and scheduling mechanism.**
- ~~**Exact proration formula** — only a conceptual sketch exists ("unused old-plan value + remaining new-plan value = adjustment").~~ **Resolved (Stage D6, `docs/stage-d6-spec.md`):** `net_amount_cents = round_half_away_from_zero( (to_plan.price_cents − from_plan.price_cents) × remaining / total )` where `remaining`/`total` are the current billing period's timedeltas (exact `Fraction`, `now` clamped into the period), rounded to the nearest cent **once**, ties away from zero. Recorded as a signed `ProrationRecord` audit row by `ProrationService.record_for_plan_change`, wired non-blocking into `SubscriptionService.change_plan`. **No charge, refund, or gateway call** — Tenora has no mid-cycle collection mechanism (a real Razorpay integration would use the Update Subscription API and Razorpay would prorate; see stage-d6-spec.md §1).
- **Multi-currency conversion logic** — `Plan.currency` exists as a field; no conversion/display logic discussed. D6 handles a plan change *across* currencies by **skipping** the proration record (a single-currency net delta is meaningless) — it does not convert.
- **Observability specifics** — logging format, metrics tooling, tracing — named as a goal, not specified.
- **The actual output of the Tenant API layer implementation** — prompt finalized, not yet executed or reviewed. Its real code is not part of this spec and should be audited against §A/§B once available, not assumed to match.
- **UI/UX — entire section C**, as stated above.
- **Deployment/hosting target** — not discussed at all; relevant once Stripe webhooks need a publicly reachable endpoint for testing (see F.5).

---

# F. ARCHITECTURAL RISKS / OPEN QUESTIONS

These are risk observations, not new requirements — flagging them is architect judgment on what's already decided, not an attempt to expand scope.

**F.1 — Test suite currently proves less than it appears to.** *(Partially resolved — Stage B3.)*
The isolation suite previously ran via `force_authenticate()`, which bypassed `TenantJWTAuthentication` entirely. Stage B3 switched `_auth_as()` to a real minted `AccessToken` + `X-Tenant-ID` header, so the auth→tenant-resolution pipeline is now genuinely exercised for the header-contract assertions (missing header → 400, non-member tenant → 403) and the forged-body assertion.
**Still outstanding:** the three foreign-subscription tests (`test_{get,patch,delete}_foreign_subscription_returns_404`) hit `/api/subscriptions/<id>/`, which no URLconf entry serves, so their 404s are URL-resolver misses — the request never reaches `TenantJWTAuthentication` or `TenantScopedManager`. "Cross-tenant object access returns 404" is asserted but only at the routing layer. Closing this needs a subscription detail endpoint (GET/PATCH/DELETE by id through the scoped manager), which is not in Phase 1's endpoint set — a deliberate scope call to make before Phase 2, not an accident to paper over.

**F.2 — Scope risk given solo, deadline-free development.**
The full roadmap (v0.1–v1.0) is substantial — multi-tenancy, Stripe, webhooks with ordering guarantees, usage metering, proration, Celery, and reconciliation, built solo with no fixed deadline. No-deadline projects commonly stall mid-scope. The tiered requirement structure (§B.1: must-have / strong-addition / nice-to-have) already exists as a mitigation — worth treating the "must have" tier as a real, protectable minimum viable finish line rather than letting it slide because later tiers look more interesting to build.

**F.3 — Spec/implementation drift risk on the Tenant API layer.**
This document currently describes those four endpoints (§B.7) as designed but unexecuted. If Claude Code or another agent implements them with any deviation (different status code choice on the undecided email-not-found case, different service boundary, etc.), this spec will be stale on those specifics until it's updated from the actual diff. Do not let Claude Code treat this document as ground truth for that feature without a review pass first — this is exactly the "repository vs. specification" conflict your own workflow rules (§9–§10 of your instructions) anticipate.

**F.4 — Multi-tenant membership as a product requirement was never fully confirmed, only implemented.**
Early in design, per-user multi-tenant membership (vs. one user = one tenant) was flagged as "worth deciding based on whether multi-tenant membership is actually a feature you want to demo" — the JWT-header-based tenant resolution was then built on the assumption that it is. This was never explicitly reconfirmed as a product requirement after that point, only carried forward implicitly through continued building. Low risk to revisit now (the mechanism is sound either way), but worth a conscious "yes, this is a real requirement" confirmation before it's cited to an interviewer as an intentional design choice rather than a default that was never challenged.

**F.5 — Local Stripe webhook testing needs a decision before Phase 2 starts.**
Testing webhook idempotency/ordering realistically requires either the Stripe CLI's webhook-forwarding (`stripe listen`) or a public tunnel (ngrok or similar) to a local dev server. Nothing has been decided about local dev/testing infrastructure for this. Not urgent now, but it blocks concrete progress the moment Phase 2 starts, so worth deciding before v0.4 begins rather than discovering the gap mid-implementation.

**F.6 — Currency field exists without any consuming logic.**
`Plan.currency` was added specifically to avoid a USD assumption, but proration (B.13) and usage billing math are currently only sketched in USD-shaped examples ("$29/month", "$0.01 per 1,000"). If multi-currency is ever a real goal, the proration/usage formulas will need currency-aware logic before those examples are implemented as tests, not treated as detail to retrofit afterward. If multi-currency is *not* actually a goal for this project (plausible — it may just be good data hygiene, not a real requirement), that's worth stating explicitly so `currency` is understood as "correct modeling," not "half-built feature."

---

*This document reflects only what has been explicitly discussed and decided. Where the conversation left something open, it's listed in §E rather than resolved. Where a genuine risk exists in what's already decided, it's named in §F rather than silently carried forward.*

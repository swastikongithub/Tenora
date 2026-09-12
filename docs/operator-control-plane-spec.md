# Operator Control Plane — Architecture & Design Specification

**Status:** APPROVED DESIGN — IMPLEMENTATION NOT STARTED

---

## 0. Scope & Purpose

Tenora currently has no first-party way for its operator to run the platform without
Django Admin, Render Shell, or direct database access — none of which are available on
the current Render Free deployment. This specification defines a complete **Operator
Control Plane**: a frontend dashboard plus a matching backend API surface giving the
platform operator full, auditable control over plans, tenants, subscriptions, billing
events, and platform-staff roles, without ever needing shell or direct-DB access for
normal operations.

**Governing constraints, carried over from `CLAUDE.md` and enforced throughout this
design:**

- All authorization is enforced server-side. A client-side gate is UX only, never the
  boundary.
- Every mutation reuses an existing domain service where one already exists
  (`SubscriptionService`, `PlanSyncService`, `WebhookProcessingService`,
  `ReconciliationService`, `UsageMeteringService`). No business logic is duplicated
  into a parallel "admin" code path.
- No subscription state transition may bypass `SubscriptionService`'s existing
  `LEGAL_TRANSITIONS` table. The operator surface cannot express an illegal state
  change — it calls the same service the tenant-facing endpoint already calls.
- No business logic lives in React.
- No field is invented without first being grounded in the existing repository —
  every model/field referenced below was verified against the actual codebase before
  this design was written.

This document is the complete, approved design. **No code has been written against
it.** Implementation proceeds phase by phase per Section F, each phase reviewed before
the next begins.

---

## Implementation Note — the only place a specific provider is named

> Tenora currently has exactly one configured payment gateway adapter, selected by
> `settings.PAYMENT_GATEWAY`. The concrete SDK-specific implementation behind that
> setting's non-mock value lives entirely inside one module under
> `apps/billing/gateway/` — the single place in the codebase permitted to import a
> payment provider's SDK, construct provider-specific signatures, or know a provider's
> specific field/event names. Every other reference in this document — "gateway,"
> "adapter," "external plan ID," "gateway sync," "gateway event" — refers to the
> provider-neutral interface (`PaymentGatewayAdapter`) that module implements, never to
> the specific provider itself.
>
> This design is written so that adding or swapping the configured adapter requires
> **zero changes** to anything described in Sections B–I: the Operator Control Plane
> speaks only Tenora's own normalized vocabulary (`external_plan_id`,
> `external_subscription_id`, `external_event_id`, the `EventType` enum), never a
> provider's own field or event names.

No other section of this document names a specific payment provider.

---

## A. Current architecture findings

**Authentication / JWT.** `TenantJWTAuthentication` (a DRF authentication class, never
Django middleware — SimpleJWT authenticates after the middleware stack has already
run) authenticates the user, then — unless `request.path` is in the exact-match
`GLOBAL_PATHS` set — resolves `Membership` from the `X-Tenant-ID` header and attaches
`request.tenant`/`request.membership`. SimpleJWT's own user resolution re-checks
`user.is_active` on every request, not only at login, so disabling a `User` takes
effect immediately.

**User model.** Email-keyed, UUID primary key, `is_staff`/`is_superuser` inherited from
`AbstractUser`. `is_staff` already gates the existing read-only platform-admin surface.
`is_superuser` is currently unused by any application code — only Django's own admin
site reads it today. `email_verified` is a distinct concept from `is_active`, never
conflated. No admin-facing user list/search endpoint exists yet — the only self-lookup
endpoint returns just the caller's own identity.

**Tenant / Membership.** `Tenant.is_active` exists in the schema (default `True`) but
**is read nowhere in the request pipeline today** — it is dead schema, not an enforced
suspension flag. `Membership` is the single join (`OWNER`/`MEMBER`), resolved once per
request and reused by the existing tenant-scoped permission classes without a second
query.

**Plan / Subscription.** `Plan` is global data (no tenant scoping), `code` unique,
money stored as `price_cents` (integer) + `currency` (never floats), `external_plan_id`
nullable-unique. `Subscription` is one-per-tenant, its state machine
(`TRIALING → ACTIVE → PAST_DUE`, `CANCELED` terminal) enforced exclusively through an
explicit legal-transition table inside `SubscriptionService` — no code path anywhere
assigns subscription status directly. A separate in-flight-checkout model exists,
deliberately not folded into the subscription state machine.

**Billing services.** Every domain operation is already a static-method service class
with idempotent, transactionally-correct patterns (a unique-constraint violation is
always caught **outside** the atomic block that raised it, so a broken transaction is
never reused). Critically, **every "sweep all" operation this design needs already
exists as a service entry point**: a webhook-retry sweep, a reconciliation sweep, and a
usage-snapshot sweep, each already the shared orchestration behind both a management
command and a scheduled background task.

**Gateway adapter boundary.** A clean, already-enforced boundary: one abstract
interface defines `create_plan`, `create_subscription`, `verify_webhook_signature`,
`parse_webhook_event`, `verify_checkout_signature`, and a read-only
`fetch_subscription_state` for reconciliation. Exactly one module implements it against
a real provider (see the Implementation Note above); a second, no-network mock
implementation exists for tests and local development. Plan creation at the gateway has
no idempotency key — a crash between the gateway call and the local write is an
already-accepted, already-documented narrow risk window, not something this design
introduces.

**Webhook processing.** Applied inline, best-effort, at receipt time — a processing
failure leaves the stored event unprocessed and recoverable only by re-running the
retry sweep (management command or scheduled task).

**Reconciliation, usage, proration.** All three are **append-only, immutable audit
tables** already. Reconciliation is detection-only — it never corrects local state or
writes back to the gateway. This shape is exactly what an operator audit surface wants
to read, with no new backend logic required to expose it.

**No Payment or Invoice model exists.** Every model in the billing domain was
inspected; none stores a structured amount/currency/line-item ledger. The closest thing
to payment history is the normalized webhook event stream, which does not carry an
amount field today.

**Background jobs — the finding that shapes this whole design.** A scheduled-task
configuration exists for a 5-minute webhook retry sweep, a daily usage snapshot, and an
hourly reconciliation sweep. There is no evidence anywhere in the repository of a
second deployed process to run them — no separate worker service, no scheduled-job
configuration file. **On the current single-web-service Render Free deployment, these
scheduled sweeps are almost certainly not executing in production at all.** This is not
a hypothetical risk; it is the reason the fallback sweep controls in Section B exist.

**Existing platform-admin surface.** A read-only permission class already reuses
`is_staff` as "can reach privileged, platform-level tooling" — the correct precedent
this design extends rather than replaces. Two existing read-only endpoints deliberately
query across every tenant (the one sanctioned exception to this codebase's tenant
isolation). A matching frontend page exists, gated client-side for UX only, with the
real boundary already server-side.

**API / serializer patterns.** Every existing mutation follows the same shape: a thin
view, an input-only serializer, a domain-service call, explicit exception-to-status-code
mapping. **No endpoint anywhere in this codebase is paginated or filtered today** —
this design is the first place pagination is introduced, done deliberately rather than
assumed.

**Frontend.** A flat route table behind a single protected-route gate. Query cache keys
are explicitly namespaced tenant-scoped vs. global, maintained by hand in lockstep with
the backend's own tenant-exemption list — the same exact-match discipline this design's
new endpoints must also follow. An existing shared component library already covers
every list/detail/form/confirm-modal shape this design needs — no new base components
are required.

**Tests.** Established, reused conventions throughout this design: real issued tokens
rather than bypassing authentication in tests, permission-matrix subtests per endpoint,
and service-level idempotency tests.

**Bootstrap — already solved.** An environment-driven, idempotent management command,
invoked on every container start, creates the first superuser account with no shell
access required — it never overwrites an existing password and never logs one. **The
first-operator-account problem is already closed.** This design's job is to make sure a
second operator is never created the same way.

---

## B. Proposed operator architecture

### Principle

Every mutation reuses an existing domain service unmodified, with exactly one
exception (plan creation, which has no existing service because nothing before this
design could create a `Plan` programmatically at all). No business logic in React;
every server-side gate is a DRF permission class.

### Authorization model — Staff vs. Root

Two tiers, both built from fields that already exist on `User` — no new field, no new
model:

| Tier | Server-side check | Meaning |
|---|---|---|
| **Staff** (`IsPlatformStaff`, existing, unchanged) | `is_staff` | **Trusted platform-operations authority.** Sufficient, alone, for every read and every routine mutation across the whole platform. |
| **Root** (`IsPlatformRoot`, new) | `is_staff AND is_superuser` | **Emergency/root authority.** Reserved for actions that change *who has power* or lock out an entire tenant. |

**`is_staff` here means trusted, cross-tenant platform-operations authority — it is not
ordinary tenant support.** It is unrelated to, and must never be confused with, a
tenant's own internal `Membership.Role` (`OWNER`/`MEMBER`), which is scoped to a single
tenant and grants no cross-tenant capability whatsoever. Holding `is_staff` means being
trusted to act across *every* tenant in the system through this control plane; it says
nothing about membership in any one of them.

`is_superuser` is deliberately **not** required for routine platform work. An operator
can run this entire control plane — manage plans, override a stuck subscription, retry
the fallback sweeps, read every diagnostic surface except the raw gateway payload —
under an `is_staff`-only account, indefinitely. `is_superuser` is only ever exercised by
whoever administers the operator roster itself, or in the rare tenant-suspension case.
This is the concrete mechanism that prevents an ordinary operator from ever needing, or
being tempted to acquire, unrestricted Django superuser status.

Root-gated actions, and only these:
- User role management (granting or revoking `is_staff`/`is_superuser`/`is_active` on
  any account)
- Tenant suspend / reactivate
- Viewing a webhook event's raw gateway payload

Everything else — plan create/edit/archive/sync, subscription overrides, all fallback
sweep triggers, every read surface — is Staff-tier.

### Reuse table

| Capability | Backend logic | New or reused |
|---|---|---|
| Subscription force-transition / plan override | `SubscriptionService.transition_status` / `.change_plan` | Reused, unmodified |
| Gateway sync for a plan | `PlanSyncService.sync_plan` | Reused, unmodified |
| Webhook retry sweep | the existing webhook-processing sweep entry point | Reused, unmodified |
| Reconciliation sweep | the existing reconciliation sweep entry point | Reused, unmodified |
| Usage snapshot sweep | the existing usage-metering sweep entry point | Reused, unmodified |
| Plan creation | — | **New**: the one genuinely new domain service in this design |
| Plan edit / archive | — | New, thin |
| User role management | — | New, thin, with the invariant guard (see Section E) |
| Tenant suspend | — | New, thin + one new check inside `TenantJWTAuthentication` |
| Audit trail | — | New: an audit model + a small write service |

### Plan management — `external_plan_id` as a platform-level lock marker

`external_plan_id` is treated purely as **the platform's own marker that a `Plan` is
externally provisioned and therefore locked** — not as a statement about what any
specific gateway's API happens to allow.

Rule: before `external_plan_id` is set, every field on a `Plan` may be edited freely.
The instant it is set, only `name` and `is_active` may change — `price_cents`,
`currency`, `interval`, and `code` are rejected with a clear error.

This is enforced **as platform policy, independent of the configured adapter's own
capabilities.** Even if a future gateway adapter's provider technically supported
editing a live plan, this platform would still refuse to mutate a locked `Plan` through
this API — because the risk being guarded against is a local plan row drifting out from
under subscriptions, checkouts, and audit records that already reference it, which is a
property of this system's own data integrity, not of any one provider's plan API. A
price change is always a *new* `Plan` (new code, freshly synced), with the old one
archived — never an in-place mutation.

No `DELETE` exists anywhere in this API for `Plan`, `Tenant`, `User`, or `Subscription`.
Archive/deactivate only — `Plan` is already referentially protected from deletion by
every subscription, checkout, and proration record that references it, so the API never
offers a capability the database would refuse anyway.

### Webhook management — normalized surface, isolated raw diagnostic

The operator dashboard's list and detail views expose **only Tenora's own normalized
fields**, never a provider's raw payload:

```
id, external_event_id, event_type, external_subscription_id,
tenant: {id, name, slug} | null,
period_start, period_end, event_created_at, received_at, processed
```

`event_type` is always one of Tenora's own normalized values — never a provider's own
event-name string:

| `EventType` value | Meaning |
|---|---|
| `ACTIVATED` | A subscription began billing |
| `CHARGED` | A billing-period charge succeeded |
| `CANCELLED` | A subscription was cancelled at the gateway |
| `PAYMENT_TROUBLE` | A charge failed or a subscription was halted for non-payment |
| `UNKNOWN` | An event the configured adapter received but has no mapping for |

Mapping a provider's own event names into this vocabulary is entirely the adapter's
responsibility (`parse_webhook_event`) — the core API contract never sees or names a
provider's event strings, only the mapped, normalized result. The equivalent
normalization exists on the reconciliation side: a provider's own subscription-status
string is mapped into Tenora's own `ProviderSubscriptionStatus` vocabulary
(`ACTIVE`/`PAST_DUE`/`CANCELED`/`PENDING`/`UNKNOWN`) before it is ever stored or
displayed.

`tenant` is resolved by matching `external_subscription_id` against the subscription
domain, falling back to the in-flight-checkout domain when no subscription row exists
yet — reusing the exact matching order the webhook-processing service itself already
uses, not a new lookup.

The full raw event payload is **never** included in the list or detail response. It is
reachable only through a separate, explicitly named action, Root-tier only, because a
gateway's raw payload can embed customer contact information and payment-instrument
metadata that no routine Staff-tier reader should see by default. Viewing it is logged
(see the observational-audit category below).

### Billing Events — not a fake ledger

No `Payment` or `Invoice` model exists, and the normalized webhook-event record carries
no amount field. A page presenting rows with no amount as "Payments" would misrepresent
what the system actually tracks. Instead:

- **Billing Events** — the same normalized, sanitized webhook-event read, filtered to
  `event_type IN (CHARGED, PAYMENT_TROUBLE)` — the two lifecycle events that are
  actually payment-shaped.
- Columns: tenant, event type (a plain badge — "Charged" / "Payment trouble"), billing
  period, event time, and `external_subscription_id` as an operator-pastable reference
  for looking the transaction up directly with the payment gateway.
- No currency/amount column exists, and the page says so explicitly rather than
  omitting the gap silently: *"Amounts aren't captured locally — look up the external
  subscription id above in your payment gateway's dashboard."*

### Future Payment/Invoice capability — explicitly out of scope, specified for later

If a real financial ledger is ever needed, the provider-neutral shape it should take is
specified here so it is not silently assumed away or designed twice:

```python
class PaymentEvent(models.Model):
    """
    A provider-neutral record of one financial movement the gateway reported —
    the domain-model counterpart to the normalized webhook event, but
    structured (amount, currency, kind) instead of raw. Tenant-owned;
    append-only, like every other financial audit table in this codebase.
    """
    class Kind(models.TextChoices):
        CHARGE_SUCCEEDED = "CHARGE_SUCCEEDED", "Charge succeeded"
        CHARGE_FAILED = "CHARGE_FAILED", "Charge failed"
        REFUND_ISSUED = "REFUND_ISSUED", "Refund issued"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payment_events")
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="payment_events")
    webhook_event = models.ForeignKey(WebhookEvent, on_delete=models.PROTECT, related_name="+")  # provenance
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount_cents = models.IntegerField()   # never floats; unsigned magnitude, kind carries direction
    currency = models.CharField(max_length=3)
    occurred_at = models.DateTimeField()   # provider-generated time
    recorded_at = models.DateTimeField(auto_now_add=True)
```

**The provider-specific work stays entirely inside the adapter**, exactly like today's
`EventType` mapping: the adapter's event-parsing method would be extended so that, for
event types carrying a financial amount, it also returns `amount_cents`/`currency` in
its normalized result — the adapter is the only place that knows where a given
provider's payload puts the amount. A new, thin ledger-recording service (mirroring the
existing webhook-event storage service's exact idempotent-insert shape) would persist
`PaymentEvent` rows from that normalized data — no provider knowledge in the service,
none in the view, none in the frontend.

**This is why the mechanism satisfies "a future gateway integration should populate the
same domain model rather than forcing frontend changes":** a second configured adapter
independently fills in the same `amount_cents`/`currency`/`kind` fields from its own
payload shape, and the ledger service, the platform API, and the Billing Events page
need **zero changes** — they only ever read `PaymentEvent`, never a provider's payload.

Not built now. Also explicitly not built now: refund/dispute tracking beyond the
`REFUND_ISSUED` stub, invoice numbers or PDFs, tax/fee breakdowns, revenue reporting,
and settlement reconciliation against the gateway. This is its own future stage with
its own spec, named here so it is never silently assumed.

### Audit semantics — critical vs. observational

A new append-only audit model, deliberately using plain snapshot fields rather than a
generic foreign key — the same instinct this codebase already applies to its other
audit tables:

```python
class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=64)          # "plan.created", "subscription.transitioned", …
    target_type = models.CharField(max_length=32)      # "Plan", "Tenant", "Subscription", "User"
    target_id = models.CharField(max_length=64)         # str(pk) — works for any target, no FK coupling
    summary = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)   # small before/after values only — never a secret, never a raw payload
    is_critical = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

Two write paths, so the critical/non-critical choice is visible at every call site:

- **Critical mutations** write their `AuditEvent` **atomically with the mutation
  itself** — inside the same database transaction, with no exception swallowed. If the
  audit write fails, the mutation is rolled back too. A financial or control-state
  change can never silently succeed with no audit record.
- **Observational actions** use a best-effort write — logged and swallowed on failure,
  the same "never raises" contract this codebase's existing proration-audit recording
  already uses. Their own effects are already durably recorded elsewhere regardless of
  whether the observational audit row lands.

**Critical** (atomic, `is_critical=True`):
1. Subscription status transition (operator override)
2. Subscription plan change (operator override)
3. Plan creation
4. Plan edit (`name` / `is_active`)
5. Plan → gateway sync — *with one honest exception, below*
6. Tenant suspend / reactivate
7. User role / `is_active` change

**Observational** (best-effort, `is_critical=False`):
- Webhook retry sweep triggered
- Reconciliation sweep triggered
- Usage snapshot sweep triggered
- Webhook raw payload viewed

**Honest exception — plan sync.** The gateway plan-creation call is not, and cannot be,
wrapped in the same database transaction as the local write that follows it — the
gateway call has no idempotency key, and the existing sync service is deliberately not
transaction-wrapped around it (a documented, already-accepted risk window predates this
design). True atomicity between that local write and its audit row is equally
unreachable without modifying that existing service, which this design will not do. What
ships instead: the audit write is attempted immediately after a successful sync: if it
fails, the request surfaces as a server error so the operator knows to check, but the
already-committed external plan id cannot be unwound at that point. Stated here plainly
rather than overclaiming atomicity the reused service does not support.

**Where the atomic wrapping lives, concretely:**
- New platform-only services (plan creation, user role management, tenant suspend) own
  their own transaction and their own critical audit write internally — one service
  call is one atomic unit, matching how this codebase's existing services already work.
- Mutations that call a **reused, unmodified** existing service (the subscription
  overrides) are wrapped by the *view*: the existing service's own transaction nests
  correctly as a savepoint inside an outer transaction the view opens around both the
  service call and the audit write, so a failed audit write rolls back the subscription
  change too — without touching the reused service's code at all.

### Fallback sweep controls — explicitly temporary

The three sweep-trigger endpoints (webhook retry, reconciliation, usage snapshot) call
the exact existing sweep-all service entry points — nothing new is written for what
they *do*. They are explicitly labeled, in both the information architecture and the UI
copy itself, as **Fallback Sweep Controls**: *"These run manually because no background
worker is deployed for this service. Once a worker and scheduler run in production,
this panel becomes a manual override, not the primary mechanism."*

- Throttled (a new, modest scoped rate limit applied to all three) — generous enough for
  legitimate manual retries, bounded against a compromised token driving repeated,
  costly runs.
- **Bridge pattern, worth stating explicitly:** until a real worker exists, these same
  authenticated endpoints are exactly what an external scheduler — a scheduled job
  product, or any timed caller — would target. They are not only a button for a human;
  they are the natural stopgap integration point too.

---

## C. Exact backend endpoint table

All paths under `/api/platform/`, all exact-match entries in `GLOBAL_PATHS` (no
`X-Tenant-ID`), all requiring authentication plus the tier shown. Pagination is
introduced here for the first time in this codebase (page-number based, page size 25).

| Method & path | Tier | Request | Response | Audit |
|---|---|---|---|---|
| `GET /api/platform/health/` | Staff | – | total tenants, webhook backlog size, discrepancies in the last 24h, last reconciliation/usage-snapshot timestamps, configured gateway adapter identifier | – |
| `GET /api/platform/stats/` *(existing, unchanged)* | Staff | – | unchanged | – |
| `GET /api/platform/plans/` | Staff | `?is_active=&search=&page=` | plan list, including inactive | – |
| `POST /api/platform/plans/` | Staff | `{name, code, price_cents, currency, interval}` | `201` plan row | **critical** |
| `GET /api/platform/plans/{id}/` | Staff | – | plan + subscriber count | – |
| `PATCH /api/platform/plans/{id}/` | Staff | `{name?, is_active?}` (money fields rejected once locked) | `200` plan row | **critical** |
| `POST /api/platform/plans/{id}/sync/` | Staff | – | `{external_plan_id}` | **critical**, with the honest exception above |
| `GET /api/platform/tenants/` *(existing, extended)* | Staff | `?status=&plan=&search=&page=` | tenant list, now paginated/filterable | – |
| `GET /api/platform/tenants/{id}/` | Staff | – | tenant + memberships + subscription + recent normalized events | – |
| `PATCH /api/platform/tenants/{id}/` | **Root**, Phase 5 only | `{is_active}` | `200` tenant row | **critical** |
| `PATCH /api/platform/subscriptions/{id}/` | Staff | `{plan_id}` XOR `{status}` | `200` subscription row | **critical** |
| `GET /api/platform/webhook-events/` | Staff | `?tenant=&event_type=&processed=&page=` | sanitized normalized fields only | – |
| `GET /api/platform/webhook-events/{id}/` | Staff | – | sanitized normalized fields only — never the raw payload | – |
| `GET /api/platform/webhook-events/{id}/raw/` | **Root** | – | normalized fields plus the raw gateway payload | observational |
| `POST /api/platform/webhook-events/process-pending/` | Staff, throttled | – | sweep summary | observational |
| `GET /api/platform/reconciliation-discrepancies/` | Staff | `?tenant=&category=&page=` | discrepancy list | – |
| `POST /api/platform/reconciliation/run/` | Staff, throttled | – | sweep summary | observational |
| `POST /api/platform/usage/run/` | Staff, throttled | – | sweep summary | observational |
| `GET /api/platform/users/` | Staff | `?is_staff=&search=&page=` | user list | – |
| `GET /api/platform/users/{id}/` | Staff | – | user + their memberships (tenant, role) | – |
| `PATCH /api/platform/users/{id}/` | **Root** | `{is_staff?, is_superuser?, is_active?}` | `200` user row | **critical** |
| `GET /api/platform/audit-log/` | Staff | `?actor=&action=&target_type=&is_critical=&page=` | audit event list | – |

---

## D. Exact frontend route/component structure

### Canonical mount and compatibility redirect

`/admin` is the canonical operator surface. `/platform-admin` becomes a single
compatibility redirect — nothing else lives at that path, and the two surfaces are
never duplicated:

```
/admin                       → AdminOverviewPage   (the existing platform-admin page's content, evolved in place — moved, not copied)
/admin/plans                 → PlansPage
/admin/plans/:id             → PlanDetailPage
/admin/tenants                → TenantsPage
/admin/tenants/:id            → TenantDetailPage
/admin/billing-events         → BillingEventsPage
/admin/webhooks               → WebhooksPage        (includes the labeled Fallback sweep control)
/admin/reconciliation         → ReconciliationPage   (includes the labeled Fallback sweep controls)
/admin/users                  → UsersPage            (role controls rendered only for a Root-tier viewer — UX only, server enforces the real boundary)
/admin/audit-log              → AuditLogPage

/platform-admin                → redirects to /admin
```

The existing platform-admin page component is retired into the new overview page — it
is not kept as a second, parallel implementation. The existing top-navigation link is
repointed at `/admin`.

### Component reuse

The existing shared component library already covers every shape this surface needs —
tables, key-value detail lists, cards, status badges, alerts, buttons, confirm modals,
form inputs, loading skeletons. **No new base component is required.**

### Query-key and tenant-exemption additions

New cache keys for every new read, all namespaced as global (not tenant-scoped) data,
matching the two that already exist for the current platform-admin reads.

Every new `/api/platform/...` path — including the new raw-payload action — must be
added to the frontend's own exact-match tenant-exemption list, kept byte-identical to
the backend's `GLOBAL_PATHS`, following the discipline this codebase already applies.
Missing this on either side produces a real, confusing failure: a staff caller with a
tenant currently selected would have a stray tenant header attached to what the backend
correctly treats as a global path, or vice versa.

---

## E. Authorization / bootstrap strategy

- **Staff = trusted platform-operations authority**, sufficient alone for every read
  and every routine mutation. This is not, and must never be presented as, an extension
  of ordinary tenant membership — it is a separate, cross-tenant trust grant.
- **Root = emergency/root authority**, checked as `is_staff AND is_superuser` (both
  flags, deliberately, as defense in depth — a superuser somehow missing `is_staff`
  should not silently retain platform access). Reserved for exactly two mutating
  actions (user role management, tenant suspend) and one privileged read (the raw
  webhook payload).
- **Bootstrap is already solved** by the existing environment-driven, idempotent
  superuser-creation command, which sets both flags together on the very first account.
  Because routine work never needs `is_superuser`, that first account can immediately
  create Staff-only colleagues for day-to-day operation through `/admin/users`, keeping
  `is_superuser` rare by design rather than by discipline alone.

### Self-lockout / last-root invariant

A single guard, checked before any role-management write is applied: **no mutation may
result in zero users simultaneously satisfying `is_staff = True AND is_superuser = True
AND is_active = True`** — precisely the predicate the Root tier itself checks.

This one invariant covers both named failure modes:
- **Self-lockout** — an actor cannot strip themselves of Root status if no other
  qualifying Root account would remain.
- **Last-root protection** — no actor can demote a *different* account to zero if doing
  so would leave no qualifying Root account at all.

A Root account may still demote *itself* as long as another qualifying Root remains —
the invariant protects the system from ever reaching zero, not from any individual
change. Because the guard is phrased over the full three-flag predicate rather than
`is_superuser` alone, it also transitively guarantees at least one `is_staff` account
always remains (a qualifying Root is, by construction, always also Staff) — no separate
"last staff" rule is needed.

---

## F. Implementation phases, ordered by risk

**Phase 0 — done.** The environment-driven superuser bootstrap command already ships.

**Phase 1 — low risk, additive, read-only.** New sanitized read endpoints (plans,
tenant detail, sanitized webhook events, reconciliation discrepancies, users, health);
pagination introduced; the full `/admin` route tree stood up for reads; the
`/platform-admin` redirect added; the existing platform-admin page retired into the new
overview page. No raw payload exposure anywhere in this phase.

**Phase 2 — medium risk, Staff-tier mutations reusing existing services unmodified.**
Subscription override endpoint; all three throttled, labeled fallback sweep triggers.
The audit model and both write paths ship here, wired in from the start — atomicity for
critical mutations is a Phase 2 property, not deferred to later.

**Phase 3 — medium-high risk, one genuinely new domain capability.** Plan creation,
plan edit/archive, plan sync (with the locked-field guard); the Billing Events page.
Still Staff-tier — the risk here is business-logic correctness, not access control.

**Phase 4 — Root-tier, concentrated blast radius.** User role management (with the
self-lockout/last-root invariant) and the raw webhook payload view. Both gated at the
narrow Root tier; both get disproportionate test coverage given how much leverage each
carries.

**Phase 5 — highest risk, deliberately last, its own review cycle.** Enforcing tenant
suspension inside `TenantJWTAuthentication` and wiring the tenant suspend endpoint. The
only phase touching the file this codebase treats as its most architecturally sensitive
— its own dedicated spec and sign-off precede implementation, exactly as every prior
stage of this project has required.

**Phase 6 — future, out of current scope, named so it is never silently assumed.**
Replace the fallback sweep buttons' role as the operational backbone with a real
deployed worker and scheduler, or an external scheduler calling the same throttled
endpoints on a timer.

---

## G. Migration strategy

Every change in this design is additive to the existing system, with two narrow,
explicit exceptions:

- New exact-match entries added to the backend's tenant-exemption list, and to its
  frontend mirror — additive only, no existing entry is touched.
- One new check inside `TenantJWTAuthentication` (Phase 5 only) — the single point this
  design touches shared, already-load-bearing authentication code, sequenced last and
  reviewed on its own.

No existing endpoint, serializer, service signature, or test file needs to change or
weaken. Every new behavior ships with new test files, following this codebase's
existing conventions rather than modifying what already passes. The existing
tenant-facing application — subscriptions, members, workspace, billing checkout — is
untouched by every phase of this design; the operator control plane is purely additive
alongside it.

Rollout order (Section F) keeps risk in front of capability at every step: read
surfaces before mutation surfaces, mutations that reuse proven services before the one
genuinely new service, and the one shared-authentication-code change absolute last.

---

## H. Security concerns

**CSRF / CORS.** No new exposure. This API is bearer-token authenticated, not
session-cookie authenticated, so Django's CSRF protection never engages for these
calls. CORS is already configured at the host level and already covers every path
under `/api/platform/...` automatically — no new CORS configuration is required.

**Privilege escalation.** Bounded by the Staff/Root split and the self-lockout/last-root
invariant (Section E). The existing bootstrap credentials remaining set in the hosting
environment indefinitely is a standing risk this design does not worsen — but the new
role-management endpoint is precisely what removes the need to touch them again after
the very first deploy.

**Tenant isolation.** Untouched, except for the one Phase 5 exception, sequenced and
reviewed on its own.

**IDOR — deliberately inverted from the tenant-facing rule.** This codebase's rule that
cross-tenant access returns 404, never 403, exists to protect an ordinary tenant-scoped
endpoint from confirming another tenant's object exists. Platform endpoints are the
opposite case by design — the operator is supposed to see that any object exists. The
correct rule here: a non-staff caller gets 403 at the permission-class gate, before any
object lookup runs; a genuine operator gets a real 404 only for an object that truly
does not exist. This distinction is called out explicitly so it is never "corrected" to
match the tenant-facing rule by mistake.

**Destructive-operation protections.** No delete capability anywhere in this API;
archive/deactivate only. Money fields on a locked plan are immutable, enforced
server-side. Every subscription mutation routes through the existing legal-transition
table — the platform API cannot express an illegal state change. Confirm-before-mutate
modals exist client-side as UX only, never as the actual boundary.

**Sensitive data never exposed.** Gateway API/webhook secrets are never serialized by
any endpoint (unchanged from the existing convention). The raw gateway payload — the
one surface that can carry customer contact and payment-instrument metadata — is
excluded from every response except the single Root-gated action, and its access is
logged. Password hashes are never serialized, matching the existing convention. Audit
metadata is restricted by explicit discipline, checked in tests, to never contain a
secret or a raw payload.

**Production worker/beat gap — a named architecture risk, not an implicit assumption.**
The scheduled sweep configuration in this codebase almost certainly does not execute on
the current deployment (Section A). The fallback sweep endpoints are a stopgap; Section
F names the future replacement (Phase 6) explicitly rather than leaving the gap
unaddressed in the design.

**Audit-write failure is a real, surfaced failure mode for critical mutations.** Because
a failed critical audit write now rolls back its paired mutation, these endpoints can
fail in a way read endpoints and observational actions cannot (an audit-table outage).
This is the deliberate trade this design makes to guarantee no silent
financial/control-state change — and it is testable directly (Section I).

**Role management is the single highest-leverage endpoint in this design.** Moving
routine work off `is_superuser` concentrates every "who has power" change into one
endpoint, which is easier to review and test thoroughly than a wide operator tier would
have been — but also means a bug in its guard logic is disproportionately consequential.
It is named here as warranting disproportionate test coverage relative to its size.

---

## I. Testing strategy

**Backend.**
- A permission-matrix subtest per new endpoint: unauthenticated → 401; an ordinary
  authenticated user → 403; Staff-only on a Root-gated action → 403; Staff on a
  Staff-gated read/mutation → 200; Root on a Root-gated action → 200. Built as a direct
  extension of this codebase's existing permission-matrix test pattern.
- Real issued access tokens in every test, never a authentication bypass shortcut —
  continuing this codebase's existing, explicit convention.
- Immutability tests: attempting to edit a locked plan's money fields returns a clear
  error and leaves the database row unchanged.
- Self-lockout and last-root tests: both named failure modes from Section E rejected,
  with the database left unchanged; a demotion that leaves at least one qualifying Root
  succeeds.
- Audit tests: every critical mutation produces exactly one `AuditEvent` with
  `is_critical=True`; a simulated failure of the audit write is proven to roll back the
  paired mutation, not partially apply it; observational actions never block on an
  audit-write failure.
- Sweep-trigger tests assert they call the exact same sweep-all service entry point
  this codebase's management-command tests already cover — proving no parallel sweep
  logic was written.
- The full existing tenant-isolation test suite is re-run unchanged throughout every
  phase except Phase 5, which ships its own dedicated isolation-style regression suite
  before the tenant-suspension check goes live.

**Frontend.**
- "The client-side gate is UX only" tests, extended to every new nested route, proving
  a non-staff viewer is redirected while the real boundary is asserted to be
  server-side.
- Stubbed-API tests per page covering loading, error, empty, and success states, plus a
  test that every mutating control is inert until its confirm modal is accepted.
- A contract test asserting every new `/api/platform/...` path is present in the
  frontend's tenant-exemption list and is called with no tenant header attached.

---

*This specification is the approved source of truth for the Operator Control Plane.
Implementation begins with Phase 1 only after this document is reviewed and the phase
is explicitly authorized.*

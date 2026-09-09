# Claude Code Implementation Specification — Stage B2

**Scope:** the Plan and Subscription API layer — `GET /api/plans/`,
`GET/POST/PATCH /api/subscriptions/current/`.

**Not in scope:** B3 (rewriting `test_isolation.py`'s `_auth_as` to use real tokens),
any frontend, and all of Phase 2 (Stripe, webhooks, usage metering, Celery, invoices,
reconciliation).

---

## 1. Objective

Route and implement the four subscription-related endpoints, exercising
`SubscriptionService` and its state-transition table via real HTTP requests for the
first time. This stage is what finally gives `test_isolation.py`'s two known failures
a real URL to hit — they are expected to change from `404` to `403`/`400` as a
byproduct of this stage existing, **without being fixed directly**. Fixing them into
their final correct state is B3's job, not this one — see §9 for the precise expected
outcome.

## 2. Inspect Before Implementing

Read these first. Repository is ground truth.

```
CLAUDE.md
docs/project-master-spec.md          — §B.5 (state machine), §B.7 (API contracts)
apps/billing/models.py               — Plan (incl. interval), Subscription (OneToOne, TenantScopedManager)
apps/billing/services.py             — SubscriptionService, LEGAL_TRANSITIONS, IllegalStateTransition
apps/tenants/permissions.py          — IsTenantMember, IsTenantOwner
apps/tenants/views.py                — the APIView + get_permissions pattern used in B1
apps/tenants/serializers.py          — the plain-Serializer-for-input pattern used in B1
apps/tenants/authentication.py       — GLOBAL_PATHS (exact-match — /api/plans/ is already in it)
config/urls.py                       — current routes; docstring lists what's wired
apps/tenants/tests/test_isolation.py — DO NOT MODIFY. Read it to understand current
                                        behavior and what changes once routes exist.
```

Current state: 35 tests, 33 passing. The 2 failures are `test_missing_tenant_header_returns_400`
(gets 404, wants 400) and `test_tenant_header_for_non_member_tenant_returns_403` (gets 404,
wants 403) — both because `/api/subscriptions/current/` doesn't exist yet.

## 3. Existing Functionality That Must Not Change

- `SubscriptionService` and `LEGAL_TRANSITIONS` in `apps/billing/services.py` — the
  transition table is locked (spec §B.5). Do not add `CANCELED → ACTIVE` or any other
  transition not already listed.
- `apps/tenants/authentication.py` — do not touch. `/api/plans/` is already in
  `GLOBAL_PATHS`; `/api/subscriptions/current/` is deliberately **not** there (it's
  tenant-scoped).
- `apps/tenants/tests/test_isolation.py` — **do not modify.** See §9 for what happens
  to it as a side effect of this stage, and why that's correct, not a bug to fix here.
- The `TenantScopedManager` pattern — `Subscription.objects.for_tenant(tenant)`, no
  ad hoc `.filter(tenant=...)`.

## 4. Required Changes

### 4.1 `GET /api/plans/`

- Global path (already in `GLOBAL_PATHS`), no `X-Tenant-ID` needed.
- Returns all `Plan` where `is_active=True`. Use the default manager — `Plan` is global,
  not tenant-owned; do not attach or use `TenantScopedManager` here.
- Permission: `IsAuthenticated` only (any authenticated user, any tenant or none).
- No pagination needed for Phase 1 (plan count is small); do not add DRF pagination
  classes speculatively.

### 4.2 `GET /api/subscriptions/current/`

- Tenant-scoped. Permission: `IsTenantMember`.
- Returns `request.tenant`'s subscription via `Subscription.objects.for_tenant(request.tenant)`.
- `Subscription` is `OneToOneField` to `Tenant` — at most one row. Use `.get()` inside
  `for_tenant(...)`, not `.filter().first()`.
- No subscription yet → **404** with a clear "no subscription for this tenant" message,
  not an empty 200. This is a real "doesn't exist," distinct from the cross-tenant
  isolation 404 — same status code, different reason; make sure error bodies don't
  imply the wrong one.

### 4.3 `POST /api/subscriptions/current/`

- Tenant-scoped. Permission: `IsTenantOwner`.
- Input: `plan_id` (or `plan` — pick one, be consistent with any naming convention
  already used elsewhere in the codebase; state which you used and why).
- Calls `SubscriptionService.create_subscription(tenant, plan, current_period_start, current_period_end)`.
- **Tenant is never accepted from the body** — comes only from `request.tenant`.
- Tenant already has a subscription (OneToOne) → 400, not a raw `IntegrityError`. Do not
  let this silently become a plan-change; creating when one exists is a distinct error
  from changing an existing one (that's PATCH, §4.4).
- `current_period_start`/`current_period_end`: for Phase 1, compute a sensible default
  period (e.g. now → now + 30 days, or based on `Plan.interval` if you want to use the
  field meaningfully) — state your choice explicitly in the report; this is not
  specified elsewhere and you're free to decide, but document the decision.
- Unknown/inactive `plan_id` → 400.
- 201 on success.

### 4.4 `PATCH /api/subscriptions/current/`

- Tenant-scoped. Permission: `IsTenantOwner`.
- Two possible operations depending on body — decide and document a clear contract
  rather than overloading ambiguously:
  - Changing `plan` → `SubscriptionService.change_plan(subscription, new_plan)`.
  - Changing `status` → `SubscriptionService.transition_status(subscription, new_status)`.
- `IllegalStateTransition` (e.g. attempting `CANCELED → ACTIVE`) → 400 with the
  service's rejection reason in the response body, not a generic error.
- No subscription exists yet → 404 (nothing to patch).
- Body containing `tenant_id` → no effect, same rule as every other endpoint.
- Directly setting `.status = ...` anywhere in the view is forbidden — must go through
  the service.

## 5. Files Likely Affected

```
new:      apps/billing/serializers.py, apps/billing/views.py,
          apps/billing/tests/__init__.py, apps/billing/tests/test_plan_api.py,
          apps/billing/tests/test_subscription_api.py
modified: config/urls.py
```

No model or migration changes expected in this stage — `Plan` and `Subscription`
already have everything needed. If you find you need a model change, stop and report
rather than proceeding silently.

## 6. Business Rules

- `CANCELED` is terminal. No code path in this stage may transition out of it.
- A tenant can have at most one subscription (enforced by the model's `OneToOneField`;
  the view/service must not work around this).
- Plans are global; subscriptions are tenant-owned.
- All mutations go through `SubscriptionService`. Views and serializers stay thin.

## 7. Security / Permission Requirements

- `IsTenantOwner` on both POST and PATCH — a MEMBER must get 403 on both.
- `IsTenantMember` (OWNER or MEMBER) on GET.
- `tenant_id` is never accepted from any request body in this stage, same as every
  prior stage.
- Server-side enforcement only; do not assume client-side hiding of controls is a
  security boundary.

## 8. Tenant-Isolation Requirements

- `GET /api/subscriptions/current/` must never return another tenant's subscription
  regardless of what's in the request.
- Since `Subscription` has no natural "foreign object ID" in the URL (it's always
  "current" for `request.tenant`), the classic cross-tenant-404 test shape from
  `test_isolation.py` doesn't directly apply here — isolation is proven by: a user in
  two tenants gets tenant A's subscription with `X-Tenant-ID: A` and tenant B's with
  `X-Tenant-ID: B`, never mixed up. Write that test explicitly.

## 9. Expected Effect on `test_isolation.py` — Read Carefully, Do Not "Fix"

Once `/api/subscriptions/current/` exists, `test_isolation.py`'s `_auth_as()` helper
(which uses `force_authenticate()` + a manually-set `X-Tenant-ID` header) will reach
this new URL for the first time. But `force_authenticate()` bypasses
`TenantJWTAuthentication` entirely (confirmed in the B1 session:
`rest_framework/request.py` replaces the authenticator tuple), so `request.tenant` is
never set by the real auth flow — `IsTenantMember`/`IsTenantOwner` will see no
membership and deny with **403** regardless of what the test's `X-Tenant-ID` header says
or what the test's docstring claims it's checking.

Concretely, expect:
- `test_missing_tenant_header_returns_400` — was 404, becomes **403** (still not 400).
- `test_tenant_header_for_non_member_tenant_returns_403` — was 404, may now correctly
  become **403** (right status, arguably for the wrong underlying reason given
  `force_authenticate`'s bypass).

**Do not modify `test_isolation.py` to make these pass or to adjust expectations.** Run
the suite, report the actual resulting pass/fail state and exact assertion errors, and
stop there. Getting `test_missing_tenant_header_returns_400` to genuinely assert 400
requires the helper to mint a real token instead of `force_authenticate` — that
rewrite is B3, deliberately out of scope here.

## 10. Edge Cases

- `GET /api/plans/` with no active plans → 200, empty list (not an error).
- `GET /api/subscriptions/current/` before any subscription created → 404.
- `POST` when a subscription already exists → 400, existing subscription untouched.
- `POST` with an inactive or nonexistent `plan_id` → 400.
- `PATCH` attempting an illegal transition (e.g. `CANCELED` → anything) → 400, status unchanged.
- `PATCH` with both `plan` and `status` in the body — decide and document behavior
  (e.g. reject as ambiguous, or apply both in a defined order); don't leave it
  undefined behavior that depends on dict ordering.
- MEMBER attempting POST or PATCH → 403.
- Missing `X-Tenant-ID` on any of the three tenant-scoped endpoints → 400 (per the
  existing, unmodified `authentication.py` contract).

## 11. Tests Required

New files, `apps/billing/tests/`. Mint real tokens (`AccessToken.for_user`), following
the pattern established in `apps/tenants/tests/test_tenant_api.py` and
`test_membership_api.py` from B1 — do not use `force_authenticate` for these new tests.

**Plans**
- Authenticated user gets active plans; inactive plans excluded.
- Unauthenticated → 401.

**Subscription — read**
- OWNER and MEMBER can both read.
- No subscription yet → 404.
- Two-tenant isolation: correct subscription returned per `X-Tenant-ID`, never crossed.

**Subscription — create**
- OWNER creates successfully → 201, correct plan and initial status (verify against
  `SubscriptionService.create_subscription` — don't assume TRIALING without checking).
- MEMBER attempting → 403.
- Creating when one already exists → 400, original subscription unchanged.
- Invalid `plan_id` → 400.
- Missing `X-Tenant-ID` → 400.

**Subscription — update**
- OWNER changes plan → 200, new plan reflected.
- OWNER makes a legal status transition → 200, status updated.
- OWNER attempts an illegal transition (e.g. `CANCELED` → `ACTIVE`) → 400, status
  unchanged, confirmed by re-fetching rather than trusting the response body.
- MEMBER attempting either → 403.
- No subscription to patch → 404.

## 12. Acceptance Criteria

1. `python manage.py check` passes.
2. `makemigrations --check` reports no changes (none expected — flag if something
   unexpected appears).
3. `python manage.py test` — all new billing tests pass. Report the exact new
   pass/fail state of `test_isolation.py` per §9 — do not adjust it to look better
   than it is.
4. Report: files created/modified, the `plan_id` vs `plan` field-naming decision, the
   default billing-period decision for creation, the ambiguous-PATCH-body decision, and
   the exact `test_isolation.py` outcome with real assertion text.

## 13. Must NOT Do

- Do not modify `test_isolation.py`.
- Do not add `CANCELED → ACTIVE` or any transition beyond `LEGAL_TRANSITIONS`.
- Do not attach `TenantScopedManager` to `Plan`.
- Do not build B3 (the real-token rewrite of `_auth_as`) as part of this stage, even
  though it would be a natural next step — report it as the logical next stage instead.
- Do not start Phase 2 (Stripe, webhooks, usage, Celery, invoices, reconciliation).
- Do not add pagination, filtering, or sorting to `/api/plans/` speculatively.
- Do not weaken any existing test to make a new one pass.

---

## Workflow

Produce a plan first and wait for approval before writing code.

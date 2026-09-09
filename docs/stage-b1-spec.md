# Claude Code Implementation Specification — Stage B1

**Scope:** signup endpoint, `Plan.interval` field, and the Tenant API layer
(tenant creation/listing, membership listing/creation).

**Not in scope:** the Plan/Subscription API layer (B2), real-JWT integration tests (B3),
any frontend, and all of Phase 2 (Stripe, webhooks, usage metering, Celery, invoices,
reconciliation).

---

## 1. Objective

Build four tenant/membership endpoints plus a minimal signup endpoint, and add a billing
interval to `Plan`. This is the first stage that produces working API endpoints — after it,
two of the six isolation tests should still fail (they need B2's subscription views), but
the tenant and membership flows become real and testable.

## 2. Inspect Before Implementing

Read these first. The repository is ground truth; if it contradicts this spec, report the
discrepancy rather than silently picking one.

```
CLAUDE.md                        — architecture rules, non-negotiable
docs/project-master-spec.md      — §A locked decisions, §B requirements
apps/tenants/models.py           — Tenant, Membership (Membership currently uses the DEFAULT manager)
apps/tenants/managers.py         — TenantScopedManager
apps/tenants/authentication.py   — GLOBAL_PATHS, the 400/403 contract
apps/tenants/permissions.py      — IsTenantMember, IsTenantOwner
apps/billing/models.py           — Plan, Subscription
apps/billing/services.py         — the service-layer pattern to follow
apps/users/models.py             — custom User + UserManager (email as USERNAME_FIELD)
config/urls.py                   — currently only wires login/refresh
apps/tenants/tests/test_isolation.py — must remain green where currently green
```

Current state: `manage.py check` passes, migrations applied, 6 isolation tests run with
4 passing / 2 failing (`404 != 400`, `404 != 403` — both because no subscription views exist).

## 3. Existing Functionality That Must Not Change

- `apps/tenants/authentication.py` — `GLOBAL_PATHS` as an **exact-match frozenset**, the
  400 (`TenantHeaderRequired`) / 403 (`PermissionDenied`) contract, and the `request._request`
  attachment. All three were deliberate corrections; do not "simplify" them.
- `apps/tenants/permissions.py` — reads `request.membership`, does not re-query.
- `apps/billing/services.py` — `SubscriptionService` and the transition table.
- `apps/tenants/tests/test_isolation.py` — **do not modify this file at all.** Its two
  current failures are expected and are fixed by B2, not by this stage.
- `apps/users/models.py` `UserManager` — `create_user(email, password)` signature.

## 4. Required Changes

### 4.1 Signup endpoint

```
POST /api/auth/register/
body: { "email": "...", "password": "..." }
→ 201 with the created user's id and email (never the password)
```

- Global path — add to `GLOBAL_PATHS` in `authentication.py`. This is the one permitted
  change to that file, and it must be added as an exact literal path, preserving
  exact-match semantics.
- Permission: `AllowAny` (explicit override — the DRF default is `IsAuthenticated`).
- Validate password with Django's `validate_password` (the validators are already
  configured in settings).
- Duplicate email → 400 with a field error, not a 500 from the unique constraint.
- Creation goes through a service, not the serializer.
- No email verification, no password reset, no activation flow. Deliberately minimal.

### 4.2 `Plan.interval`

Add to `apps/billing/models.py`:

```python
class Interval(models.TextChoices):
    MONTHLY = "MONTHLY", "Monthly"
    ANNUAL = "ANNUAL", "Annual"

interval = models.CharField(max_length=10, choices=Interval.choices, default=Interval.MONTHLY)
```

Generate the migration. Nothing else in this stage consumes it — it exists so Phase 2
proration has a period length and the pricing UI has a real field to toggle on. Do not
build proration logic now.

### 4.3 `Membership` → `TenantScopedManager`

Attach `objects = TenantScopedManager()` to `Membership` in `apps/tenants/models.py`
(spec §A.2.9). This is a locked decision that was pending this stage.

`TenantScopedManager` subclasses `models.Manager` and only *adds* `for_tenant()` — it does
not remove `.get()` or `.filter()`, so the existing
`Membership.objects.select_related("tenant").get(user=user, tenant_id=tenant_id)` lookup in
`TenantJWTAuthentication` continues to work unchanged. Verify this by running the tests.

Generate the resulting migration (managers-only, no schema change).

### 4.4 Tenant API layer

```
POST   /api/tenants/          global path, authenticated
GET    /api/tenants/me/       global path, authenticated
GET    /api/memberships/      tenant-scoped, IsTenantMember
POST   /api/memberships/      tenant-scoped, IsTenantOwner
```

**`POST /api/tenants/`**
- Input: `name`, `slug`. No tenant context required (none exists yet).
- Creates `Tenant` + an `OWNER` `Membership` for the requesting user, in one
  `transaction.atomic()` block, inside `TenantService.create_tenant(user, name, slug)`.
- Duplicate slug → 400 field error, not a raw `IntegrityError`.
- 201 on success, returning the tenant plus the caller's role.

**`GET /api/tenants/me/`**
- Returns every tenant the user has a `Membership` in, with that membership's role.
- Query from `Membership` filtered by `user=request.user` with `select_related("tenant")`.
  Do not loop over tenants issuing a membership query per tenant.

**`GET /api/memberships/`**
- Uses `Membership.objects.for_tenant(request.tenant)` — the scoped manager added in 4.3.
  Do not write `.filter(tenant=...)` at the call site.
- Both OWNER and MEMBER may list.

**`POST /api/memberships/`**
- OWNER only.
- Input: `email` of an **existing** user. No `role` field is accepted — the endpoint only
  ever assigns `MEMBER`. If `role` appears in the body it must not be honoured.
  Do not render or accept a role selector; this is not an invitation system (no token,
  no expiry, no acceptance step).
- Unknown email → 404. (This resolves the previously-undecided item in spec §E; record the
  choice.)
- Duplicate membership → 400.
- **Concurrency requirement (spec §A.4.16):** the pre-check is a UX convenience; the
  `UNIQUE(user, tenant)` constraint is the real guarantee. Catch `IntegrityError`
  **outside** the `transaction.atomic()` block that raised it, or use a nested savepoint
  and catch outside the inner block. Never catch it inside the block that raised it and
  continue using that transaction — Postgres marks it broken and the next query raises
  `TransactionManagementError`. Both the pre-check path and the `IntegrityError` path must
  return the identical clean 400.
- Membership creation logic goes in a service (extend `TenantService` or add
  `MembershipService` — your call, but state which and why).

## 5. Files Likely Affected

```
new:      apps/users/serializers.py, apps/users/services.py, apps/users/views.py
new:      apps/tenants/serializers.py, apps/tenants/services.py, apps/tenants/views.py
new:      apps/users/tests/ (with __init__.py), apps/tenants/tests/test_tenant_api.py,
          apps/tenants/tests/test_membership_api.py
modified: apps/tenants/models.py (manager only), apps/billing/models.py (interval field),
          apps/tenants/authentication.py (one GLOBAL_PATHS entry), config/urls.py
migrations: apps/billing (interval), apps/tenants (managers)
```

## 6. Business Rules

- `tenant_id` is never accepted from a request body on any endpoint in this stage.
- Tenant context comes only from `X-Tenant-ID` + `Membership` resolution.
- The membership endpoint can never produce an `OWNER`.
- Serializers validate input shape only; all mutations go through services.

## 7. Security / Permission Requirements

- `POST /api/auth/register/` is the only unauthenticated endpoint added. Everything else
  requires authentication, and the two membership endpoints additionally require tenant context.
- Registration must not leak whether an email already exists in a way that differs from
  ordinary validation errors — a normal 400 field error is fine.
- Never return password hashes in any response.
- Server-side permission enforcement is authoritative; do not rely on anything client-side.

## 8. Tenant Isolation Requirements

- `GET /api/memberships/` must return only the current tenant's members, via the scoped manager.
- A user belonging to two tenants must see only the one named in `X-Tenant-ID`.
- Adding the three new global paths must not weaken exact-match semantics in `GLOBAL_PATHS`.

## 9. Edge Cases

- Registering an existing email → 400.
- Registering with a weak password → 400 with the validator's message.
- Creating a tenant with a taken slug → 400.
- `GET /api/tenants/me/` for a user with zero memberships → 200 with an empty list, not 404.
- Adding a member who is already a member → 400 (both paths, see 4.4).
- Adding a nonexistent email → 404.
- A MEMBER attempting `POST /api/memberships/` → 403.
- A request with a valid JWT but no `X-Tenant-ID` on a tenant-scoped endpoint → 400.
- A request with `X-Tenant-ID` for a tenant the user isn't in → 403.

## 10. Tests Required

New test files. Do not modify `test_isolation.py`.

**Registration**
- Valid registration → 201, user exists, password is hashed not stored plaintext.
- Duplicate email → 400.
- Weak password → 400.
- No authentication required to reach the endpoint.

**Tenant creation / listing**
- Creates tenant and OWNER membership atomically.
- Duplicate slug → 400.
- Unauthenticated → 401.
- `/me/` returns correct tenants and roles for a user in two tenants.
- `/me/` with zero memberships → 200, empty list.

**Membership listing / creation**
- OWNER and MEMBER can both list.
- Listing returns only the current tenant's members (set up a user in two tenants and assert
  the other tenant's members are absent).
- MEMBER gets 403 on create.
- OWNER can add an existing user as MEMBER.
- Body containing `"role": "OWNER"` never produces an OWNER membership.
- Body containing `"tenant_id"` for another tenant has no effect.
- Duplicate member via the pre-check → 400.
- **Duplicate member via the `IntegrityError` path → 400.** Force the race (e.g. patch the
  pre-check to a no-op, or create the conflicting row between check and insert) so the
  constraint fires and the handler is genuinely exercised. A test that only hits the
  pre-check does not test the concurrency guarantee.
- Nonexistent email → 404.

## 11. Acceptance Criteria

1. `python manage.py check` passes.
2. `makemigrations` produces only the expected billing (interval) and tenants (managers)
   migrations — flag anything unexpected.
3. `python manage.py migrate` applies cleanly.
4. `python manage.py test` — all new tests pass; `test_isolation.py` still has exactly its
   current 4 passing, and its 2 failures are still `404 != 400` and `404 != 403` (they are
   B2's job). If any previously-passing isolation test breaks, stop and report.
5. Report: files created, files modified, which service holds membership creation and why,
   the actual `IntegrityError` handling structure used (paste the code), and anything in the
   repo that contradicted this spec.

## 12. Must NOT Do

- Do not modify `test_isolation.py`, or create subscription views to make its 2 failures pass.
- Do not change `GLOBAL_PATHS` to prefix matching, or add anything to it beyond
  `/api/auth/register/`.
- Do not add invitation tokens, expiry, acceptance flows, email sending, or password reset.
- Do not add a `role` field to the membership creation endpoint.
- Do not implement proration or any use of `Plan.interval` beyond adding the field.
- Do not start B2 (subscription views), B3 (real-JWT tests), the frontend, or Phase 2.
- Do not catch `IntegrityError` inside the atomic block that raised it.
- Do not weaken any existing test to make new code pass.

---

## Workflow

Produce a plan first and wait for approval before writing code. Then implement, run the
full test suite, and report actual output.

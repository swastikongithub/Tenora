# Claude Code Implementation Specification — Stage B3

**Scope:** rewrite `apps/tenants/tests/test_isolation.py`'s `_auth_as()` helper to use
real JWT authentication instead of `force_authenticate()`. This is the last piece of
Phase 1.

**Not in scope:** any new endpoint, any frontend, all of Phase 2.

---

## 1. Objective

`test_isolation.py` is the project's single most important test file — the signature
suite proving cross-tenant isolation. It currently passes 6/7 relevant assertions for
the wrong reason: `_auth_as()` uses `force_authenticate()`, which replaces DRF's
authenticator tuple entirely (confirmed in B1/B2: `rest_framework/request.py`), so
`TenantJWTAuthentication.authenticate()` never runs. Every test in this file exercises
`IsTenantMember`/`IsTenantOwner` and the view/manager layer, but **none of them have
ever actually tested `TenantJWTAuthentication` itself** — the class containing the
`GLOBAL_PATHS` exact-match logic, the 400/403 status contract, and the `ValidationError`
fix from B1. That's the code with the most corrections behind it in this project, and
it currently has zero real test coverage.

This stage closes that gap. After it, `test_missing_tenant_header_returns_400` should
finally assert what its name says: **400**, not 403.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md
apps/tenants/tests/test_isolation.py       — THE file being rewritten
apps/tenants/tests/test_tenant_api.py      — real-token pattern from B1
apps/tenants/tests/test_membership_api.py  — real-token pattern from B1, incl. _auth() helper shape
apps/billing/tests/test_subscription_api.py — real-token pattern from B2
apps/tenants/authentication.py             — what's actually being tested now
apps/tenants/permissions.py
```

Three test files already establish a working real-token pattern (`AccessToken.for_user`
+ `Authorization: Bearer ...` + `X-Tenant-ID` header). This stage applies that same
established pattern to the one file that still doesn't use it — it is not inventing a
new approach.

Current state: 57 tests total, 56 passing, 1 failing
(`test_missing_tenant_header_returns_400`, asserts 400, gets 403).

## 3. Existing Functionality That Must Not Change

- **Every existing assertion in `test_isolation.py` must be preserved.** This stage
  changes *how* requests are authenticated, not *what* the tests check. The six test
  method names, their docstrings' intent, and their expected status codes stay as they
  are — except the one that's currently wrong for the wrong reason (see §4).
- `TenantJWTAuthentication`, `GLOBAL_PATHS`, `IsTenantMember`, `IsTenantOwner`,
  `TenantScopedManager` — do not modify. This stage is a **test-only** change.
- All other test files (`test_register.py`, `test_tenant_api.py`,
  `test_membership_api.py`, `test_plan_api.py`, `test_subscription_api.py`) — do not touch.

## 4. Required Changes

### 4.1 Rewrite `_auth_as()`

Replace:
```python
def _auth_as(self, user, tenant):
    self.client.force_authenticate(user=user)
    self.client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
```

With a version that mints a real token, following the exact pattern already used in
`test_membership_api.py` and `test_subscription_api.py`:
```python
def _auth_as(self, user, tenant):
    token = AccessToken.for_user(user)
    self.client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
```
Add the `AccessToken` import at the top of the file, matching how the other test files
import it.

### 4.2 The no-tenant-header test needs its own auth, not `_auth_as`

`test_missing_tenant_header_returns_400` deliberately does **not** send `X-Tenant-ID` —
that's the entire point of the test. `_auth_as()` always sets both headers, so this
test cannot use it. Check how it currently authenticates without going through
`_auth_as` (it may already partially bypass it, or may need a small local helper that
sets only `Authorization`, no `X-Tenant-ID`). Write whatever is needed so this test
sends a real, valid JWT with no tenant header at all, and report exactly what you did.

### 4.3 Re-verify every existing assertion still holds for the right reason

Once real tokens are in place, re-run each test and confirm the status code it asserts
is now being produced by the actual code path its name claims:

- `test_get_foreign_subscription_returns_404` — should still be 404, now genuinely via
  `TenantJWTAuthentication` resolving the caller's real tenant, then the scoped manager
  failing to find the other tenant's subscription.
- `test_patch_foreign_subscription_returns_404` — same, PATCH.
- `test_delete_foreign_subscription_returns_404` — same, DELETE.
- `test_forged_tenant_id_in_body_is_not_honored` — should still pass; confirm the body's
  `tenant_id` still has no effect now that the real auth path is resolving tenant from
  the header, not the body.
- `test_missing_tenant_header_returns_400` — **this is the one that changes.** Should
  now genuinely return 400 from `TenantHeaderRequired`, not 403 from `IsTenantMember`.
- `test_tenant_header_for_non_member_tenant_returns_403` — should still be 403, now
  genuinely from `TenantJWTAuthentication`'s `PermissionDenied` when the `Membership`
  lookup fails, rather than (previously) `IsTenantMember` denying on unset
  `request.membership`.

If any of these produces a different status code than before, or fails, **stop and
report** — do not adjust the test to match. A change in outcome here means either this
spec's understanding of the auth flow is wrong, or something in the underlying code
doesn't behave as documented, and either is worth surfacing rather than papering over.

## 5. Files Affected

```
modified: apps/tenants/tests/test_isolation.py (rewritten helper + auth for one test)
```

Nothing else. No production code changes are expected in this stage. If you find you
need to change non-test code to make this work, stop and report why before proceeding
— that would mean B1/B2 left something broken that only real auth exposes.

## 6. Edge Cases / Things to Verify

- Confirm token generation works with this project's UUID primary key (already verified
  working in B1/B2 — `AccessToken.for_user` stringifies the UUID,
  `TenantJWTAuthentication` casts it back via the underlying `JWTAuthentication`). Don't
  re-derive this from scratch; it's established.
- Confirm no test in this file now accidentally depends on request/response state that
  `force_authenticate` provided differently than real auth does (e.g. `request.user`
  being set identically either way — it should be, but verify).

## 7. Tests Required

This stage *is* the test change — there's no new test file. The requirement is that
all 6 tests in `test_isolation.py` pass, with `test_missing_tenant_header_returns_400`
now genuinely asserting 400.

## 8. Acceptance Criteria

1. `python manage.py check` passes.
2. `python manage.py test` — **all tests pass, project-wide.** Expected: 57/57 (up
   from 56/57). Report the exact number.
3. `test_missing_tenant_header_returns_400` passes with a real 400, not 403.
4. Every other test in `test_isolation.py` still passes, and you've confirmed (per §4.3)
   each is now passing for the reason its name claims, not incidentally.
5. No production code file was modified. If one had to be, report exactly why before
   proceeding, don't just do it silently.
6. Update `docs/project-master-spec.md`: the known limitation about `test_isolation.py`
   using `force_authenticate` (mentioned in §B.17 / wherever B1/B2's updates left it)
   is now resolved — mark it as such. This closes the last open item from Phase 1's
   original "definition of done."

## 9. Must NOT Do

- Do not weaken, remove, or reinterpret any existing assertion to make it pass.
- Do not modify `authentication.py`, `permissions.py`, `managers.py`, or any model.
- Do not touch any other test file.
- Do not start Stage C or Phase 2, even though this is the natural point to.
- If any test's outcome changes unexpectedly (beyond the one predicted change), stop
  and report rather than silently adjusting the test to match the new result.

---

## Workflow

Produce a plan first and wait for approval before writing code. This is a small,
focused change — the plan should be short. If it isn't, that's a sign the scope is
drifting beyond what's specified here.

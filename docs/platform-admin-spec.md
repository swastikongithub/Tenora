# Claude Code Implementation Specification — Platform Admin Dashboard

**Scope:** a read-only dashboard for the platform operator (you) to see every
tenant and every subscription across the entire system — the one deliberate,
documented exception to this project's tenant-isolation architecture. New
backend endpoints that intentionally do not scope by tenant, gated by a new
`IsPlatformStaff` permission; a new frontend route reachable only by platform
staff.

**Not in scope:** any mutating action (suspending a tenant, force-cancelling
a subscription, editing another tenant's data) — this stage is view-only.
Razorpay/Stage D, the cancellation UI, any change to how tenant-scoped
endpoints work for ordinary users.

---

## 1. Objective

Every endpoint built so far deliberately filters by tenant — that's the
entire point of `TenantScopedManager`, `GLOBAL_PATHS`, and the isolation test
suites across B1–C6. This stage builds the **one intentional exception**:
a small set of endpoints that deliberately see across all tenants, because
the person using them is the platform operator, not a tenant's OWNER or
MEMBER.

**This exception must stay narrowly scoped.** Nothing about how any existing
tenant-scoped endpoint resolves, authenticates, or authorizes changes. The
new endpoints are additive and separate; they don't touch
`TenantJWTAuthentication`, `TenantScopedManager`, or any existing permission
class.

**Reusing `is_staff`, not inventing a new field, is the correct call here —
unlike the `is_active` reuse the email-verification stage correctly
rejected.** `is_staff` already means "this person can access privileged,
platform-level tooling" (it already gates Django admin). Using the same flag
for this dashboard is the same concept, not two different meanings forced
into one field — the opposite situation from `is_active`/"verified," where
two genuinely different concepts would have collided.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md            — confirm no existing endpoint already
                                          covers any of this (it shouldn't)
apps/tenants/models.py, apps/billing/models.py — Tenant, Membership,
                                          Subscription, Plan field names —
                                          ground truth for what the aggregate
                                          queries below actually query
apps/users/views.py, serializers.py    — MeView's current UserSerializer —
                                          needs `is_staff` added so the
                                          frontend can decide whether to show
                                          this dashboard at all
apps/tenants/authentication.py         — GLOBAL_PATHS — the new endpoints go
                                          here (no X-Tenant-ID needed — there
                                          is no single tenant context for a
                                          platform-wide view), but they get a
                                          different, new permission class
                                          layered on top, not IsTenantMember/
                                          IsTenantOwner
apps/tenants/permissions.py            — the existing pattern
                                          (IsTenantMember/IsTenantOwner) to
                                          follow structurally for the new
                                          IsPlatformStaff class — though it
                                          checks something entirely
                                          different (request.user.is_staff,
                                          not tenant membership)
frontend/src/lib/use-current-user.ts   — where is_staff becomes available to
                                          the frontend once the backend
                                          serializer exposes it
frontend/src/components/Table.tsx      — reused for the tenant list, incl.
                                          its mobile transform
frontend/src/routes/AppRoutes.tsx      — where the new gated route goes
```

Current state: Google Sign-In + email verification committed. Backend
107/107, frontend 257/257. `is_staff` already exists on `User`
(inherited from `AbstractUser`) and is already `True` for the existing
Django superuser account — no migration or data change needed for that.

## 3. Existing Functionality That Must Not Change

- `TenantJWTAuthentication`, `TenantScopedManager`, `IsTenantMember`,
  `IsTenantOwner`, every existing tenant-scoped endpoint's behavior — all
  untouched. This stage adds new endpoints; it does not modify how any
  existing one resolves tenant context or authorization.
- Every currently-passing test must still pass.
- Ordinary users (non-staff) must see zero behavior change anywhere in the
  app they already use.

## 4. Required Changes

### 4.1 `IsPlatformStaff` permission

New DRF permission class checking `request.user.is_staff` — structurally
similar to `IsTenantOwner`'s shape, but checking a platform-wide flag on the
user, not anything tenant/membership-derived. Use judgment on where it
lives (a new `apps/platform/` app is the natural home, given this feature
cross-cuts `apps/tenants` and `apps/billing` rather than belonging to
either) — report where and why.

### 4.2 New app structure

A new `apps/platform/` (or similarly named) Django app — no models needed
(it only reads existing `Tenant`/`Membership`/`Subscription`/`Plan` data via
aggregation), just `views.py`, `serializers.py`, `permissions.py`. Add to
`INSTALLED_APPS`.

### 4.3 Endpoints

```
GET /api/platform/tenants/
  → list every tenant, regardless of who's asking — deliberately no
    TenantScopedManager, no X-Tenant-ID requirement. Each item: id, name,
    slug, created_at, member_count (a real Count() annotation, not a
    Python-side loop), and its subscription summary (plan name + status,
    or null if none).

GET /api/platform/stats/
  → real aggregate counts, computed via the ORM (Count, annotate,
    TruncMonth or similar), never hand-computed in Python from a fetched
    list:
    - total tenant count
    - subscription status breakdown (count per Status value, including a
      count for "no subscription")
    - plan distribution (count of tenants per Plan)
    - tenant signups over time (count of tenants created per month, or a
      reasonable granularity given current data volume) — this is
      legitimate, real, historical data (Tenant.created_at already exists
      on every row), unlike anything that would have been fabricated on
      the Overview dashboard (C6) — this is the first page in the project
      allowed to show a genuine time-series chart, precisely because real
      historical data exists at the platform level that doesn't exist at
      the single-tenant level.
```

Both endpoints: global path (`GLOBAL_PATHS`, no `X-Tenant-ID`), permission
class `IsPlatformStaff` (not `IsAuthenticated` alone — a logged-in ordinary
user must get 403, not 200 with data they shouldn't see).

**No pagination** — match the existing convention (memberships/plans lists
don't paginate today); revisit only if data volume ever makes that a real
problem, not preemptively.

### 4.4 `MeView` — expose `is_staff`

Add `is_staff` to the existing `UserSerializer`/`MeView` response — this is
what lets the frontend decide whether to show any platform-admin UI at all.
Small, additive change to an existing, tested endpoint — verify existing
tests for it still pass with the added field.

### 4.5 Frontend route

A new route (e.g. `/platform-admin`), reachable only when
`useCurrentUser()`'s `is_staff` is `true`. Non-staff users hitting this
route directly (typed URL) get redirected away or shown a clear "not
available" state — **this is UX only; the real boundary is
`IsPlatformStaff` on the backend**, state this explicitly in code, same
discipline as every other client-side permission check in this project.

Layout: use judgment on whether this reuses the existing `TopNavbar`/
`AppShell` (with the tenant switcher hidden or disabled, since there's no
"current tenant" concept on this page) or gets a simpler, dedicated shell —
report which and why.

### 4.6 Frontend UI

- Stats section: real KPI cards (total tenants, status breakdown) plus two
  charts — a status/plan distribution chart and a signups-over-time chart.
- **Charting approach: hand-rolled SVG, not a new charting library
  dependency**, consistent with this project's established pattern of
  preferring lean, custom-built visuals over adding a dependency for a
  simple need (the same reasoning that rejected GSAP, Three.js, and Lottie
  for the `AuthArtPanel` work). Two simple chart types (a bar/column chart
  for distributions, a line or bar chart for the time series) don't justify
  a new dependency. If, during implementation, this genuinely proves more
  complex than expected, report that and propose the smallest reasonable
  library rather than over-building custom SVG chart logic — but the
  starting assumption is hand-rolled, token-driven SVG.
- Tenant list: the existing `Table` primitive, including its mobile
  stacked-card transform — reused, not reinvented.

## 5. Files Likely Affected

```
Backend:
  new:      apps/platform/ (views.py, serializers.py, permissions.py,
                             apps.py, __init__.py, tests/)
  modified: config/settings.py (INSTALLED_APPS)
            config/urls.py (new routes)
            apps/tenants/authentication.py (GLOBAL_PATHS +2)
            apps/users/serializers.py (is_staff added to UserSerializer)

Frontend:
  new:      frontend/src/routes/PlatformAdminPage.tsx (or similar)
            chart components (hand-rolled SVG, per §4.6)
            tests for the above
  modified: frontend/src/lib/global-paths.ts (+2)
            frontend/src/routes/AppRoutes.tsx (new gated route)
            wherever useCurrentUser()'s type/shape is defined (+is_staff)
```

No change to any existing tenant-scoped endpoint, model, or test.

## 6. Business Rules

- This is the **only** place in the entire codebase where cross-tenant data
  is deliberately returned in one response. It must never leak into any
  other endpoint's behavior.
- View-only in this stage — no endpoint here mutates any tenant's data.

## 7. Security Requirements

- `IsPlatformStaff` is the real boundary — verified by a test asserting a
  non-staff authenticated user gets 403, not by relying on the frontend
  hiding a nav link.
- No new PII exposure beyond what already exists — tenant names/slugs and
  subscription status/plan are already visible to each tenant's own
  members; this dashboard just aggregates the same categories of
  already-existing data across tenants, for the one role designed to see
  that aggregate.

## 8. Edge Cases

- A tenant with no subscription — appears in the list with a null
  subscription summary, and counts toward the "no subscription" bucket in
  stats, not silently omitted.
- Zero tenants in the system (a fresh, empty deployment) — stats show zero
  counts and an empty chart state, not an error.
- A non-staff user directly hitting `/api/platform/tenants/` with a valid
  token — 403, not 404 (404 would incorrectly imply the endpoint doesn't
  exist; 403 correctly states "you can't do this").

## 9. Tests Required

- **The anti-isolation test — this stage's signature test, the deliberate
  opposite of every isolation test in this project**: a platform-staff user
  can see tenants A, B, and C together in one response — assert this
  explicitly, naming it clearly as the intentional exception it is.
- Non-staff authenticated user gets 403 on both new endpoints.
- Unauthenticated request gets 401.
- Stats aggregates are mathematically verified against known seeded
  fixture data (create N tenants with known statuses/plans, assert the
  returned counts match exactly).
- `MeView` still returns everything it did before, plus `is_staff`,
  correctly reflecting `True`/`False` for different test users.
- Frontend: staff user sees the platform-admin route/nav entry and it
  renders real data; non-staff user does not see it and is blocked from
  navigating there directly.

## 10. Acceptance Criteria

1. `manage.py check`, `manage.py test` — full count reported.
2. `npm run build`, `npm test`, `npm run lint` — full count reported.
3. Manual walkthrough, screenshotted, both themes: log in as the existing
   staff account, view the dashboard with real seeded multi-tenant data
   (create a couple more demo tenants via Django admin if needed for a
   meaningful screenshot), confirm the charts render real numbers. Then log
   in as an ordinary non-staff user and confirm no trace of this dashboard
   is reachable.
4. Confirm zero change to any existing tenant-scoped test's behavior.
5. `git status` — no unrelated file changed.
6. Report: where `IsPlatformStaff` and the new app were placed and why, and
   confirmation the anti-isolation test explicitly proves cross-tenant data
   is returned (this is the one place that's supposed to happen).

## 11. Must NOT Do

- Do not add any mutating action (suspend, cancel, edit) — view-only.
- Do not modify `TenantJWTAuthentication`, `TenantScopedManager`, or any
  existing tenant-scoped view/permission.
- Do not add a new charting library — hand-rolled SVG, per §4.6, unless a
  genuine, reported blocker makes that impractical.
- Do not invent a new "platform staff" field — reuse `is_staff`.
- Do not fabricate any statistic — every number traces to a real
  aggregation query.
- Do not build Razorpay, the cancellation UI, or any other queued stage.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

```
Read docs/platform-admin-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.
```

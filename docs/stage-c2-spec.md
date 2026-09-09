# Claude Code Implementation Specification — Stage C2

**Scope:** the frontend's cross-cutting infrastructure — API client, authentication
(token storage + refresh), tenant context (switcher + cache isolation), routing, and
the app shell (sidebar + layout). This is the highest-risk frontend stage: it's where
the frontend's version of the backend's tenant-isolation guarantee gets built.

**Not in scope:** any real page content (Login, Workspace, Members, Subscription,
Overview — all C3–C6), any backend change, Stage D / Phase 2.

---

## 1. Objective

C1 built correct, accessible, token-driven components with nothing to plug them into.
C2 builds everything those components will be plugged into: how the app knows who's
logged in, which tenant is active, how requests reach the API correctly, and the shell
every future page lives inside.

**The one requirement that matters most in this stage**, stated plainly because it's
easy to under-engineer: **switching tenants must make it structurally impossible for
stale data from the previous tenant to render.** Not "we remember to clear the cache"
— *impossible by construction*, the same way the backend's `TenantScopedManager`
requires an explicit `tenant` argument rather than trusting a developer to remember to
filter. §4.3 specifies the mechanism that makes this a structural guarantee rather than
a discipline. This is the frontend's equivalent of the backend's signature isolation
test suite — treat it with the same seriousness.

Two secondary things this stage must get right because everything after it depends on
them:
- **Auth must survive a page reload** without either forcing a re-login every time or
  storing tokens somewhere trivially stealable by XSS.
- **The app shell (sidebar, tenant switcher) must be navigable end-to-end today**, even
  though the pages behind each nav item don't exist until C3–C6. A shell you can't
  click through isn't verified, it's asserted.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md              — §B.7 (API contracts), §A (locked decisions)
docs/ui-design-specification.md          — §C.2 (Tenant Switcher — THE spec for §4.3
                                            below), §C.6 (security constraints),
                                            §C.7/§C.8 (responsive/accessibility)
docs/stage-c1-spec.md, stage-c1-refinement-spec.md — what already exists in frontend/
frontend/src/components/                 — the primitives C2 builds on; do not
                                            recreate any of them
apps/tenants/authentication.py           — GLOBAL_PATHS (exact list), the 400/403
                                            contract — the frontend must match this
                                            exactly, not guess at it
config/urls.py                           — the real, current endpoint list
```

Current state: Stage C1 + C1a committed (`214d7ca`), 35/35 frontend tests, 57/57
backend tests. `frontend/` has components and tokens; no router, no API calls, no auth,
no pages.

Real backend endpoints this stage integrates with (verify against `config/urls.py`,
don't assume):
```
Global (no X-Tenant-ID):
  POST /api/auth/login/
  POST /api/auth/refresh/
  POST /api/auth/register/
  GET  /api/tenants/me/
  POST /api/tenants/
  GET  /api/plans/

Tenant-scoped (X-Tenant-ID required):
  GET/POST  /api/memberships/
  GET/POST/PATCH  /api/subscriptions/current/
```

## 3. Existing Functionality That Must Not Change

- No backend file may be modified. See §4.6 for how cross-origin dev requests are
  handled without touching Django.
- No C1 component is redesigned. The app shell composes existing primitives (Card,
  Badge, Button, EmptyState, etc.) — it does not introduce new visual primitives. If a
  genuinely new primitive turns out to be needed (e.g. `Select`, `Alert`, `Nav`), that's
  expected per the UI spec's C1-deferred list — build only what's needed, following the
  existing token-driven pattern, and report it as a scope addition.
- All 35 frontend and 57 backend tests must still pass.

## 4. Required Changes

### 4.1 API client — `src/lib/api-client.ts` (or similar)

A single fetch wrapper every request goes through. Centralizing this is not optional —
per-call header logic is exactly how a request accidentally ships without
`X-Tenant-ID`, or ships it when it shouldn't.

- Base URL from an environment variable (`VITE_API_BASE_URL` or similar), not
  hardcoded.
- Attaches `Authorization: Bearer <access token>` to every request except the ones
  that don't need it (registration, login itself).
- Attaches `X-Tenant-ID: <current tenant id>` to every request the current route
  requires it for, and **never** to the global paths listed in §2 — mirror the
  backend's `GLOBAL_PATHS` set exactly, as a matching exact list in the client, not a
  guess or a prefix check (the backend spec explicitly forbids prefix matching for the
  same reason — don't reintroduce that mistake on the frontend).
- On a `401` response: attempt exactly one silent token refresh (§4.2), retry the
  original request once with the new access token, and if that also fails, treat the
  session as ended (§4.2's logout path). Never retry more than once.
- Normalizes error responses into a consistent shape the UI can render (status code +
  message + field errors where the backend provides them).
- **`tenant_id` (or any tenant identifier) is never sent in a request body.**

### 4.2 Auth — `src/lib/auth/` (context + hooks)

**Token storage decision (locked for this stage):**
- **Access token: in-memory only** (React state/context), never written to
  `localStorage` or `sessionStorage`.
- **Refresh token: `sessionStorage`.** Real tradeoff, documented in a code comment at
  the point of storage: `sessionStorage` is readable by any script on the page (same
  XSS exposure as memory), but clears on tab close, unlike `localStorage`.
- **On app load:** if a refresh token exists in `sessionStorage`, attempt
  `POST /api/auth/refresh/` immediately, before rendering any authenticated UI. Failure
  → clear it, treat as logged out.
- **Login:** stores access token in memory, refresh token in `sessionStorage`.
- **Logout:** no `/api/auth/logout/` endpoint exists — logout is client-side only:
  clear stored tokens, clear tenant context, redirect to login. **Report this as a
  gap** (a real logout should blacklist the refresh token server-side; the
  `token_blacklist` app is already installed). Do not build the backend endpoint here.
- **Refresh rotation:** `ROTATE_REFRESH_TOKENS: True` +
  `BLACKLIST_AFTER_ROTATION: True` — every refresh returns a new refresh token that
  must replace the old one in storage.

### 4.3 Tenant context — `src/lib/tenant/` — THE isolation-critical piece

**Mechanism (required, not a suggestion):** every tenant-scoped server-state query
must include the current tenant id as an explicit segment of its cache key, e.g.
`['tenant', tenantId, 'members']` — never a bare key that happens to hold whatever
tenant was last fetched. This mirrors the backend's `TenantScopedManager.for_tenant
(tenant)` taking tenant as an explicit argument rather than inferring it from ambient
state: make the correct behavior structural. When `tenantId` changes, the query key
changes, and the previous tenant's cached data becomes a different, inactive cache
entry — there is no code path by which it can render under the new tenant. Do not
implement this as "clear the whole cache and refetch" as the primary mechanism — that's
fragile (easy to forget for a query added in C4/C5) and wrong for genuinely global data.
A manual invalidation call may exist as a UX nicety but must not be what isolation
actually depends on.

**Global vs tenant-scoped keys:** `/api/tenants/me/` and `/api/plans/` data must NOT be
tenant-namespaced. Use a clear convention, e.g. `['global', 'plans']` vs.
`['tenant', tenantId, 'members']`.

**Tenant context provides:** the list of tenants + roles (from `/api/tenants/me/`),
the current tenant id, a `switchTenant(tenantId)` function, reachable at every
breakpoint including mobile (§C.7).

**Persisting selection across reloads:** storing the last-selected tenant id in
`localStorage` as a UX convenience is fine — but state explicitly in a code comment
that this value is never trusted as authorization; the server re-resolves `Membership`
on every request regardless. If the stored id isn't in the current
`/api/tenants/me/` list on load, fall back to tenant selection, don't error.

**The signature test for this stage** (write it, name it clearly):
```
Given: a user who is a member of Tenant A and Tenant B, with different cached
       member lists for each already in the query cache
When:  switchTenant(tenantB.id) is called while a component reading Tenant A's
       member list is still mounted
Then:  the component must show Tenant B's data (or a loading state), never a
       flash or persistence of Tenant A's data
```

### 4.4 Server state — TanStack Query (or state the alternative and why)

Recommended, specifically because its query-key-based cache model is what makes §4.3's
structural guarantee straightforward. A different choice must still satisfy §4.3 —
report how.

### 4.5 Routing & app shell

- React Router, with a `ProtectedRoute` wrapper redirecting unauthenticated access to
  `/login`. The redirect must wait for §4.2's silent-refresh-on-load to resolve first —
  no flash-then-redirect on a reload with a valid refresh token.
- App shell (UI spec §C.1 Nav + §C.2): sidebar with tenant switcher pinned top, nav
  below, user menu (email + logout) pinned bottom. Responsive per §C.7 — icon rail on
  tablet, drawer on mobile, tenant switcher reachable in the mobile top bar.
- **Route stubs** for Workspace/Members/Subscription/Overview — minimal placeholders
  using `EmptyState`, naming which stage builds the real page. Same governance pattern
  as C1's showcase: clearly temporary, replaced page-by-page as C3–C6 land.
- `/login` gets slightly more than a bare stub — see §4.6.

### 4.6 A minimal login form — scaffolding, not C3's page

Build a minimal functional login form (email + password, using C1's `Input`/`Button`,
no new visual design) at `/login`, so this stage can be verified end-to-end. Mark it
clearly temporary (README note, in-page note), same pattern as C1's showcase. Do NOT
build the split-panel layout, imagery, or copy from the UI spec's Page 1 section —
that's C3's actual deliverable.

### 4.7 Cross-origin requests in dev — no backend change

Use Vite's dev-server proxy (`server.proxy` in `vite.config.ts`) to route `/api/*` to
Django, avoiding CORS without touching `config/settings.py`. Production CORS strategy
is deferred to the Docker stage after Stage C — do not add `django-cors-headers` now.

## 5. Files Likely Affected

```
new:      frontend/src/lib/api-client.ts (or api/ directory)
          frontend/src/lib/auth/ (context, hooks, types)
          frontend/src/lib/tenant/ (context, hooks, types)
          frontend/src/routes/ or src/pages/ (route stubs + minimal login)
          frontend/src/components/layout/ (AppShell, Sidebar, TenantSwitcher, UserMenu)
          frontend/src/App.tsx rewritten to mount the router — confirm the DEV-only
          showcase from C1 still works and is still absent from production
          test files for all of the above
modified: frontend/vite.config.ts (dev proxy), frontend/package.json (new deps),
          frontend/README.md
```

No backend file. If a backend change seems necessary, stop and report why.

## 6. Business Rules

- `X-Tenant-ID` matches `GLOBAL_PATHS` exactly — attached or omitted accordingly.
- Tenant id never sent in a request body.
- Client-held current-tenant value is never authorization, only "which header to
  send."
- Exactly one silent refresh attempt on a 401, never a loop.

## 7. Security Requirements

- Access token memory-only; refresh token `sessionStorage`, tradeoff documented in
  code.
- No card/CVV/payment fields anywhere.
- Login failure (`401`) renders one generic message regardless of whether the email
  exists or the password was wrong — don't un-distinguish what the backend already
  keeps ambiguous.

## 8. Tenant-Isolation Requirements (this stage's core deliverable)

- [ ] Tenant-scoped query cache keys include tenant id explicitly (§4.3).
- [ ] Switching tenant cannot render stale previous-tenant data, verified by the
      signature test in §4.3, not just asserted.
- [ ] Global data is not tenant-namespaced and is not needlessly cleared on switch.
- [ ] The client never sends `tenant_id` in a body.
- [ ] The client-held tenant selection is documented as non-authoritative.

## 9. Edge Cases

- Reload with a valid refresh token → silently re-authenticated, no login flash.
- Reload with an expired/invalid refresh token → clean redirect to login.
- User removed from their last-selected tenant between sessions → graceful fallback,
  not an error state.
- `401` on a non-login request → one-shot refresh-and-retry, not immediate logout.
- A second `401` after refresh-and-retry → logout, redirect to `/login`.
- Switching tenant mid-mutation for the old tenant — state what happens; don't
  silently apply the old tenant's mutation result under the new tenant's UI.
- Rapid double-switching (A → B → A) — final state must reflect the last selection,
  not a race between two in-flight fetches.

## 10. Tests Required

Use MSW (Mock Service Worker) to intercept HTTP at the network level so tests run
without a live Django server.

- API client: `Authorization` attached correctly; `X-Tenant-ID` attached only on
  tenant-scoped paths matching `GLOBAL_PATHS` exactly; one 401 triggers
  refresh-and-retry, not a loop; a second consecutive 401 logs out.
- Auth: login stores tokens correctly; logout clears both; app-load silent refresh
  works when valid and fails gracefully when not; refresh rotation replaces the stored
  token.
- Tenant context: **the §4.3 signature test**, verbatim — the most important test in
  this stage, must exist explicitly, not be implied by other passing tests.
- Routing: unauthenticated → redirected; authenticated → not.
- App shell: tenant switcher renders and is interactable at desktop and mobile
  breakpoints (full visual responsive testing is manual, per C1's precedent).

## 11. Acceptance Criteria

1. `npm run build` clean.
2. `npm test` — all previous tests pass plus new ones, exact count reported. The §4.3
   signature test must be individually identifiable in the report.
3. `npm run lint` clean.
4. `.venv/Scripts/python.exe manage.py test` — still 57/57.
5. Manual walkthrough, screenshotted: log in via `/login` with a real backend account,
   see the shell with the tenant switcher populated from `/api/tenants/me/`, switch
   tenants (create a second tenant/membership via Django admin if needed), confirm
   route stubs render, log out, confirm redirect to `/login`.
6. Report the logout-has-no-backend-endpoint gap explicitly.
7. Report which server-state library was used and confirm it satisfies §4.3.
8. `git status` — no file outside `frontend/` modified.

## 12. Must NOT Do

- Do not modify any backend file, including for CORS — use the Vite proxy.
- Do not build C3's real Login page, or any of Workspace/Members/Subscription/Overview
  — route stubs only.
- Do not store the access token in `localStorage` or `sessionStorage`.
- Do not implement tenant-switch cache safety as "clear everything and refetch" as the
  primary mechanism — the query-key-namespacing approach in §4.3 is required.
- Do not build a backend logout/blacklist endpoint — report the gap, don't fix it.
- Do not add `django-cors-headers` or any backend CORS configuration.
- Do not weaken any existing test.
- Do not start C3.

---

## Workflow

Produce a plan first and wait for approval before writing code. Given this stage's
size, it's reasonable to propose splitting implementation into two sub-sessions (e.g.,
API client + auth first, then tenant context + router + shell) — if so, say so as part
of the plan rather than silently doing all of it in one giant pass.

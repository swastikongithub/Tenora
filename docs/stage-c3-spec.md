# Claude Code Implementation Specification — Stage C3

**Scope:** §0 is a small, explicitly-scoped backend addendum (two tiny endpoints,
decided upfront, not discovered mid-session) that closes gaps flagged across B1–C2.
Everything after §0 is frontend: the real Login page, a minimal Register flow, and the
Workspace Selection & Creation page — replacing C2's scaffolding.

**Not in scope:** Members (C4), Subscription & Plans (C5), Overview (C6), Stage D /
Phase 2. §0 is the only backend work in this stage — everything else stays frontend.

---

## 0. Backend Addendum — Two Small Endpoints (do this first, its own commit)

Three gaps have been flagged repeatedly across B1, C2 session 1, and C2 session 2:
no way to create a user without Django admin access from the running app, no way for
the frontend to know who's logged in after a reload, and no server-side session
termination on logout. The first is fixed by wiring the frontend to the *existing*
`POST /api/auth/register/` endpoint (§2, no backend change needed there — it already
exists from B1). The other two need two small, well-justified additions.

### 0.1 `GET /api/users/me/`

- Global path (add to `GLOBAL_PATHS` in `apps/tenants/authentication.py` — the one
  permitted edit to that file, exact-match entry, not a prefix).
- `IsAuthenticated`. Returns `{id, email}` for the requesting user. Nothing else —
  no tenant list (that's `/api/tenants/me/`, already exists), no role, no PII beyond
  what's already public within the app.
- This is what lets `UserMenu` show the real email after a silent-refresh reload,
  instead of the "Signed in" fallback C2 built as a stopgap.

### 0.2 `POST /api/auth/logout/`

- Global path (same `GLOBAL_PATHS` addition).
- `IsAuthenticated`. Accepts `{refresh}` in the body, blacklists it via
  `RefreshToken(token).blacklist()` (the `token_blacklist` app is already installed
  per Stage A — this endpoint is the first thing that actually uses it for logout
  rather than just rotation).
- Invalid/already-blacklisted/missing token → 400, not a 500. Logging out with a bad
  token should still be a graceful no-op from the client's perspective — the frontend
  clears its local state regardless of this endpoint's exact response, but the
  endpoint itself must not crash on bad input.
- This closes the "refresh token stays valid after logout" gap C2 reported.

### 0.3 Required for §0

- Tests for both endpoints: `/me/` returns correct data for the authenticated user
  and 401 for none; `/logout/` blacklists successfully, rejects a malformed/missing
  token cleanly, and — importantly — verify that using a blacklisted token afterward
  at `/api/auth/refresh/` genuinely fails (this is the actual guarantee being added,
  not just "the endpoint returns 200").
- `python manage.py test` — must stay at 57/57 plus these new ones; report the new
  total.
- **This is its own commit, before any frontend work in this stage begins.** Small,
  reviewable, separate from the frontend changes that consume it.
- Update `docs/project-master-spec.md` §B.7 (add both routes) and close out the
  gap notes from C2's reports (logout, current-user) — same "record the resolution"
  pattern used when B3 closed its own tracked gap.

---

## 1. Objective (frontend portion)

Replace C2's deliberately bare scaffolding with the two real pages the UI design spec
already fully specifies: Login (§C.4 Page 1) and Workspace Selection & Creation
(§C.4 Page 2). Also retire the two pieces of temporary scaffolding whose removal was
promised at this exact stage: the C1 DEV component showcase and C2's minimal login
form.

Additionally, since the UI spec's Login page design includes a "New here? Create
account" affordance and the backend has had a working `/api/auth/register/` endpoint
since B1 with no UI ever built for it, this stage adds a minimal registration flow.
This directly resolves the "users can only be created via Django admin" friction that
has come up repeatedly during backend testing.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md         — §B.7 (add §0's routes here), §C.4 Page 1 & Page 2
docs/ui-design-specification.md     — §C.4 full Page 1 and Page 2 specs (the design
                                       authority for this stage — read both in full)
docs/stage-c2-spec.md               — what C2 already built (auth, tenant context,
                                       routing, shell) — this stage consumes it, does
                                       not rebuild it
frontend/src/lib/auth/              — AuthProvider, token-store, session — reused as-is
frontend/src/lib/tenant/            — TenantProvider — reused as-is
frontend/src/routes/LoginPage.tsx   — the C2 scaffold this stage replaces
frontend/src/dev/                   — the C1 showcase this stage removes
apps/tenants/authentication.py      — GLOBAL_PATHS, for the §0 additions
```

Current state: Stage C2 committed (`6968a03`), 105/105 frontend tests, 57/57 backend
tests. Real login/tenant-switch/logout flow already works end-to-end against C2's
minimal form — this stage is about the *real* UI, not new backend plumbing beyond §0.

## 3. Existing Functionality That Must Not Change

- `AuthProvider`, `TenantProvider`, `ProtectedRoute`, the query-key isolation
  mechanism from C2 §4.3, `api-client.ts` — all reused as-is. This stage builds pages
  that *use* this infrastructure; it does not modify how auth or tenant isolation
  work.
- All 105 frontend and 57 (+ §0's additions) backend tests must still pass.
- No component from C1/C1a is redesigned — Login/Register/Workspace pages compose
  existing primitives (`Input`, `Button`, `Card`, `Alert`, `Modal`, `EmptyState`,
  `Skeleton`), following the token system, not introducing new visual language.

## 4. Required Changes

### 4.1 Real Login page — per UI spec §C.4 Page 1

Build to the full spec: split-panel layout (visual panel + form, collapsing per
§C.7's responsive rules — visual panel becomes a top banner on tablet, disappears on
mobile), the generic-401-message behavior already established in C2 (don't
regress this), loading/error states per the spec's UI-component mapping table.

The visual panel is **original artwork or a CSS gradient/pattern** — not a stock
photo, not anything resembling copyrighted material. This was stated in the original
UI spec and still applies.

Add the "New here? Create account" link, wired to §4.2.

### 4.2 Minimal Register flow

Not fully specified visually anywhere (the master spec flagged this as a real gap in
§C.9/§E) — so this stage designs it minimally, consistent with Login's visual
language rather than inventing a new one:
- Email, password, confirm-password (client-side match check before submit — the
  backend only needs one `password` field per B1's `RegisterSerializer`).
- Calls `POST /api/auth/register/`. Success → log the user in automatically (call
  `/api/auth/login/` with the same credentials, or use the register response if it
  returns tokens — verify which against the actual B1 implementation, don't assume)
  and redirect into the app.
- Duplicate email / weak password → the backend's actual field-error shape
  (`{"email": [...]}` / `{"password": [...]}`) rendered inline per field, using the
  same `ApiError.fieldErrors` normalization C2's `api-client.ts` already provides.
- This can be a separate route (`/register`) or a toggle within the Login page's
  layout — implementer's call, report which and why.

### 4.3 Workspace Selection & Creation — per UI spec §C.4 Page 2

- List view: tenants the user belongs to, each showing name, slug, and role badge
  (`OWNER` accent / `MEMBER` neutral) — this data already exists in `TenantProvider`
  from C2 (the `/api/tenants/me/` global-keyed query); **reuse it, don't refetch
  separately.**
- Empty state (`EmptyState` primitive): no workspaces yet, with a "Create workspace"
  action.
- Create workspace: a `Modal` (from C1) with name + slug fields, calling
  `POST /api/tenants/`. Duplicate slug → inline field error, not a toast (per the
  original UI spec's stated pattern for this exact case). Success → close modal,
  select the new workspace as active (via `TenantProvider.switchTenant`), navigate
  into the app shell.
- Selecting an existing workspace row sets it active the same way and proceeds into
  the shell.

### 4.4 Wire `UserMenu` to `GET /api/users/me/`

Replace C2's "email known only within the login session, else 'Signed in'" fallback
with a real fetch on app load (global query key, e.g. `['global', 'me']`). Keep a
brief loading skeleton state for the moment before it resolves — never flash "Signed
in" and then replace it with the email a second later if avoidable; prefer showing
the skeleton until the real value is known.

### 4.5 Retire scaffolding — both removal obligations, due at this stage

- **C1's DEV showcase** (`/dev/showcase` route + `src/dev/`): delete it, per the
  removal obligation recorded in C1's spec and `frontend/README.md`. It has served
  its purpose — C1/C1a's components are now proven in real pages.
- **C2's minimal login form**: replaced by §4.1's real page. Remove the "temporary
  scaffolding" note that accompanied it; there's nothing left marked temporary in the
  auth flow after this stage.
- Update `frontend/README.md` to remove references to both as if they still exist.

### 4.6 Wire logout to §0.2

`AuthProvider.logout()` (built in C2, currently client-side only) should now also
call `POST /api/auth/logout/` with the current refresh token, best-effort — if that
call fails (network error, already-expired token), still proceed with the local
token-clearing and redirect; don't block logout on the server call succeeding. Report
this composition explicitly.

## 5. Files Likely Affected

```
Backend (§0, its own commit):
  modified: apps/tenants/authentication.py (GLOBAL_PATHS +2 entries)
            config/urls.py (+2 routes)
            docs/project-master-spec.md (§B.7 + gap closures)
  new:      a small view/serializer for each endpoint (apps/users/ or apps/tenants/,
            wherever fits the existing app structure — report where and why)
            tests for both

Frontend:
  new:      frontend/src/routes/LoginPage.tsx (rewritten, or kept + heavily expanded)
            frontend/src/routes/RegisterPage.tsx (or a Login-page toggle — §4.2)
            frontend/src/routes/WorkspacePage.tsx (or similar)
            frontend/src/routes/CreateWorkspaceModal.tsx (or co-located)
            tests for all of the above
  modified: frontend/src/components/layout/UserMenu.tsx (§4.4)
            frontend/src/lib/auth/* (§4.6's logout composition)
            frontend/src/routes/index or router config (new routes, showcase removed)
            frontend/README.md
  deleted:  frontend/src/dev/ and its route entry
```

## 6. Business Rules

- Tenant creation and selection both route through `TenantProvider.switchTenant` —
  no page sets the active tenant by any other mechanism.
- Register-then-login must not silently swallow a registration success followed by a
  login failure — if that combination somehow occurs, surface it, don't leave the
  user on a spinner.
- `tenant_id` still never appears in any request body from any new page.

## 7. Security Requirements

- Login/Register error messages still don't distinguish "email doesn't exist" from
  "wrong password" (Login) or leak which emails are registered beyond the standard
  "already registered" validation error Register necessarily gives (that one's
  unavoidable — a registration form has to say "email taken" to be usable; this is
  different from Login's stricter non-disclosure requirement and should not be
  conflated with it).
- No payment/card fields anywhere, still.
- The visual panel on Login must not be a real photo of a real person or any
  copyrighted asset.

## 8. Edge Cases

- User has zero workspaces after login/register → Workspace page's empty state,
  not an error.
- User has exactly one workspace → still show the selection page (don't
  auto-navigate past it) unless the UI spec explicitly calls for auto-selection in
  the single-workspace case — check §C.4 Page 2 for this and follow it; report which
  behavior was specified.
- Registration with an email that's already registered, differing only in case →
  should be rejected (B1's `UserManager.normalize_email` already lowercases on
  write and on lookup) — verify the frontend's duplicate-email error rendering
  handles this correctly, it's the same backend behavior as any other duplicate.
- Logout when the network is down → local state still clears, user still lands on
  Login (§4.6).
- `/api/users/me/` fails to load (network error, not auth error) → `UserMenu` shows
  its loading/fallback state gracefully, doesn't crash the shell.

## 9. Tests Required

**Backend (§0):**
- `/api/users/me/` — authenticated returns correct `{id, email}`; unauthenticated
  401.
- `/api/auth/logout/` — valid refresh token blacklists successfully; the blacklisted
  token then fails at `/api/auth/refresh/` (the real guarantee, not just a 200 from
  logout); malformed/missing token → 400, not 500.

**Frontend:**
- Login: renders, submits, generic error on 401, redirects to Workspace (or shell,
  per whatever the actual post-login flow is) on success.
- Register: field errors render correctly (duplicate email, weak password);
  password-confirmation mismatch caught client-side before submit; successful
  registration leads to an authenticated state.
- Workspace: renders the list from existing `TenantProvider` data (don't assert a
  duplicate network call); empty state when no workspaces; create-workspace modal
  validates and submits; duplicate slug renders inline, not a toast; selecting a
  workspace calls `switchTenant` and navigates correctly.
- UserMenu: shows the fetched email, not the C2 fallback, once `/me/` resolves.
- Confirm `/dev/showcase` is genuinely gone — a test or build-output check asserting
  it 404s or isn't in the route table, not just "the folder is deleted."

## 10. Acceptance Criteria

1. `python manage.py check` and `python manage.py test` — §0's endpoints working,
   full count reported.
2. `npm run build` clean.
3. `npm test` — all previous 105 pass, plus new ones, exact count reported.
4. `npm run lint` clean.
5. Manual walkthrough, screenshotted: register a brand-new user through the UI (not
   Django admin), land authenticated, create a workspace through the UI, see it in
   the switcher, log out, log back in with the same credentials, confirm the email
   shows correctly in `UserMenu` after a page reload (proving §0.1 + §4.4 together).
6. Confirm `/dev/showcase` and the C2 login scaffold are both gone.
7. `git status` — backend changes only in §0's commit; frontend changes only in
   `frontend/`.

## 11. Must NOT Do

- Do not build Members, Subscription, or Overview pages — C4/C5/C6.
- Do not modify `AuthProvider`, `TenantProvider`, `api-client.ts`, or the query-key
  isolation mechanism from C2 — this stage consumes that infrastructure, it doesn't
  change it.
- Do not add any backend endpoint beyond the two named in §0. If something else
  seems to need a backend change, stop and report — don't expand §0 mid-session.
- Do not build password reset or email verification — still explicitly out of scope,
  same as the original signup-endpoint decision.
- Do not weaken any existing test.
- Do not start C4.

---

## Workflow

§0 first, its own commit, before any frontend code is touched. Then produce a plan
for the frontend portion and wait for approval before writing code. Given the size
(three new pages plus two scaffolding removals), splitting into sub-sessions is
reasonable — propose a split if it makes sense, same as C2.

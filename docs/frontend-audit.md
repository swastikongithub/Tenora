# Tenora Frontend Audit (UI‑02)

**Status:** COMPLETE — Pass 1 (security & coupling) + Pass 2 (visual / component /
state / responsive / accessibility / identity) both delivered. Awaiting review;
to be committed as the UI‑02 checkpoint once approved.

**This is a read‑only audit.** No source, test, config, route, API, theme, or
dependency file was modified. The only file created is this one. UI‑01's
checkpoint commit `3807b0a` is untouched. Every classification and coupling claim
is traced to real code at the cited path; nothing is inferred from a filename.

**Pass 1 findings and every discrepancy flag (§0, D‑0.1…D‑0.6) are preserved
verbatim.** Pass 2 adds five further discrepancies (D‑0.7…D‑0.11) in §0.

---

## 0. Pre‑audit discrepancies (flagged, not resolved)

Per `docs/ui-02-audit-spec.md` §1 and this project's CLAUDE.md rule, discrepancies
between what the specs/UI‑01 claim and what the code actually is are reported, not
silently corrected.

| # | Discrepancy | Detail |
|---|---|---|
| **D‑0.1** | **`docs/tenora-redesign-master-spec.md` does not exist in the repo.** | `docs/ui-02-audit-spec.md` §2 lists it as a required inspection input. The finalized "Tenora UI/UX Redesign — Master Specification (Revised)" was supplied in conversation only and was **not** saved to the repo (confirmed: `docs/` contains `authpanel-redesign-spec.md`, `navbar-redesign-spec.md`, `login_desktop_redesign_concept.html`, but no redesign master spec). Per the session directive, this audit uses the **in‑conversation master‑spec text** as authoritative and does **not** add the missing file. References to it below are cited as "redesign master spec §N". |
| **D‑0.2** | **No settings / profile / account / tenant‑settings route or page exists.** | `grep -rniE "path=[\"'](settings\|profile\|account\|tenant-settings)"` on `frontend/src/` returns nothing. `AppRoutes.tsx` defines only login, register, verify‑email, overview, workspace, members, subscription, platform‑admin. Account‑adjacent behaviour (email display, theme toggle, logout) lives inline in `AccountMenu` → `UserMenu` → `ThemeToggle`. The audit spec's §4/§10 and redesign master spec §11 (UI‑08 "Settings/Account/Profile, Tenant Settings") name pages that **are not built**. Documented as an absence; not invented (audit spec §6). Full treatment in §10 (Pass 2). |
| **D‑0.3** | **`GET /api/users/me/` returns `{ id, email, is_staff }`, not `{ id, email }`.** | `apps/users/serializers.py::MeSerializer` (`fields = UserSerializer.Meta.fields + ["is_staff"]`), `apps/users/views.py::MeView` docstring: "`{ id, email, is_staff }`". The earlier Stage C3 §0 backend spec said "`{id, email}` only" — that predates the platform‑admin stage. The frontend (`use-current-user.ts`) correctly consumes `is_staff`. UI‑01 did not assert the shape, so this is a spec‑vs‑code drift, not a UI‑01 error. |
| **D‑0.4** | **UI‑01 §7.1 claim: "`AuthArtPanel` is the one place with ambient motion."** | **Incomplete.** `TenantSwitcher.tsx` and `AccountMenu.tsx` both use `framer-motion` (`AnimatePresence` + `motion.div` fade/slide/scale on open), each gated by `useMediaQuery('(prefers-reduced-motion: reduce)')`. So there are **three** sources of non‑essential motion, all reduced‑motion‑gated. UI‑01 explicitly flagged itself as "a light read… not the UI‑02 audit", so this is the gap being closed, not a contradiction — but it is recorded here per audit spec §1/§21. |
| **D‑0.5** | **`/api/plans/archived/` is not a real frontend feature.** | It appears only in `frontend/src/lib/__tests__/api-client.test.ts` and `global-paths.test.ts` as a **fixture** proving `GLOBAL_PATHS` is exact‑match (so `/plans/` is exempt from `X-Tenant-ID` but `/plans/archived/` would not be). No production code calls it. Any reader scanning endpoint lists should not treat it as a surface. |
| **D‑0.6** | **The frontend is not provider‑agnostic about billing.** | Redesign master spec §25 ("no silent provider‑boundary decisions"). The frontend explicitly names Razorpay: `CheckoutStartResponse.razorpay_subscription_id` / `.razorpay_key_id` and `CheckoutSuccessPayload.razorpay_payment_id` / `_subscription_id` / `_signature` (`SubscriptionPage.tsx`, `useRazorpayCheckout.ts`); `index.html` loads `https://checkout.razorpay.com/v1/checkout.js`; `useRazorpayCheckout` polls `window.Razorpay`. This is existing, shipped coupling — the audit documents it (§7, §13, §21); it is **not** a decision UI‑02 makes. Any UI‑0x stage that would change what the checkout UI reveals about the adapter boundary needs explicit sign‑off. |
| **D‑0.7** | **UI‑01 §7.1 claim "restrained shadows plus one opt‑in accent glow" is imprecise.** | `theme.css` defines **three** shadow tokens: `--shadow-card` (`0 1px 2px rgba(0,0,0,.4)`), `--shadow-overlay` (`0 8px 32px rgba(0,0,0,.6)`), `--shadow-accent-glow`. So it is "two plain shadows + one accent glow", not "restrained shadows [plural] + one glow". Minor; UI‑01's *intent* (shadows are restrained) is confirmed. Recorded per audit spec §21. |
| **D‑0.8** | **`Table`'s sort, row‑click, and row‑selection features are entirely unused by application code.** | `Table.tsx` implements `sortable` columns (`aria-sort`, `SortGlyph`), `onRowClick`, `selectedRowKey` (a reserved `border-l-2` selection rail so selecting never shifts layout), `sort`/`onSortChange`. **No page passes any of them** — `MembersPage` and `PlatformAdminPage` pass only `columns`, `rows`, `rowKey`, `caption`, `renderMobileCard` (grep‑verified). These features are exercised only by `Table.test.tsx`. Not a contradiction of a UI‑01 claim (UI‑01 §8.8 proposed the selection rail as a *keep*, without claiming it is in use), but the redesign should know the rail is dead code today. |
| **D‑0.9** | **Empty‑state rendering is inconsistent — the `EmptyState` primitive is used on only 2 of ~5 empty surfaces.** | `EmptyState` is imported by `SubscriptionPage` and `WorkspacePage` only. `OverviewPage`'s "No active subscription" is a hand‑rolled `<Card><h2><p>`; `MembersPage`'s empty state is an `<Alert variant="danger">` (empty is treated as an error, §8); `PlatformAdminPage`'s "no tenants" is a hand‑rolled `<Card><p>`. This is not a bug — each was a deliberate per‑page call — but it is a real consistency gap the redesign will have to reconcile. §20. |
| **D‑0.10** | **`MembersPage` keeps a local `formatJoined` that duplicates `format.formatDate`.** | `MembersPage.tsx:35‑44` — byte‑equivalent behaviour to `format.ts::formatDate` (same options, same em‑dash fallback). `format.ts`'s own header comment says `formatDate` "is lifted from the local helper `MembersPage` has had since C4" — so the local copy should have been removed and wasn't. Safe C‑class refactor (§20). |
| **D‑0.11** | **`GoogleSignInButton` and `useRazorpayCheckout` both poll on a 100ms `setInterval` with no timeout ceiling.** | `GoogleSignInButton.tsx:82` and `useRazorpayCheckout.ts:68` — each polls `window.google` / `window.Razorpay` every 100ms until the CDN script parses, with **no maximum attempts / no give‑up**. If the CDN is blocked (ad‑blocker, network policy, offline), the interval runs indefinitely (cleared only on unmount). Low severity — the interval is cheap and each has a graceful "still loading" fallback on the action path — but it is unbounded work. Documented, not fixed. |

---

## 1. Purpose and scope

This document is the UI‑02 deliverable required by `docs/ui-02-audit-spec.md`: a
code‑traced inventory of the current Tenora frontend, classifying each significant
piece **A** (functionally frozen), **B** (visual implementation replaceable),
**C** (safe to generalize), or **D** (do not touch), so UI‑03…UI‑09 work from a
map rather than assumption.

**Pass 1 scope (this delivery):** architecture; authentication; tenant
lifecycle/isolation; subscription/billing; members/team A/D coupling; overview
coupling; platform administration; API/data integration map; out‑of‑scope
confirmation; the A/D portions of the route/component/master matrices;
protected/high‑risk areas.

**Pass 2 scope (delivered):** full shared‑component inventory (B/C);
members/settings visual layer; state‑handling matrix; responsive inventory;
accessibility inventory; existing visual‑system inventory; `AuthArtPanel`/identity
assessment; safe‑refactor list; UI‑05…UI‑09 sequencing implications; open
questions; acceptance evidence; final consolidation + internal‑consistency check.

**Out of scope entirely:** UI‑03 (prototype), UI‑04 (design system), any visual
change, any backend change, any dependency change, re‑deriving UI‑01's reference
research.

---

## 2. D1–D8 baseline and UI redesign context

- **D1–D8 (backend, commit `dc87ec0`) are closed and frozen.** This redesign is a
  UI/UX phase, not "D9". No backend architecture, billing logic, tenancy, auth,
  webhook, metering, proration, Celery, or reconciliation code is reopened. If a
  genuine frontend blocker needs a backend contract change, it must be surfaced
  and approved before implementation — never decided mid‑stage (redesign master
  spec §2).
- **Redesign context source:** the in‑conversation "Tenora UI/UX Redesign —
  Master Specification (Revised)" (see **D‑0.1**). Locked rules this audit
  respects and verifies:
  - **§7** — the `TRIALING/ACTIVE/PAST_DUE/CANCELED → warning/success/danger/neutral`
    Badge mapping is **restyled, never remapped**. Verified present and identical
    in three places (§7 of this doc).
  - **§12 / §22** — **no new frontend surface for backend‑only capabilities**
    (usage metering D5, proration D6, reconciliation D8, webhook processing
    D1–D4). Verified: none exists today (§ 4.2 of this doc).
  - **§19** — no new UI dependency without justification exceeding its cost.
- **UI‑01 output:** `docs/design-reference-analysis.md` (commit `3807b0a`) —
  context only. Its §7 "existing identity" claims are what this audit
  independently verifies; discrepancies found so far are **D‑0.4** (and see §7,
  §17 in Pass 2).

---

## 3. Frontend architecture overview

### 3.1 Stack (traced to `frontend/package.json`, `vite.config.ts`, `src/main.tsx`)

- **React 19 + TypeScript + Vite** (`@vitejs/plugin-react`), **Tailwind CSS v4**
  via `@tailwindcss/vite` (no `tailwind.config.js` — v4 config is CSS‑first, in
  `src/styles/theme.css`).
- **Runtime dependencies (`package.json` `dependencies`):** `react`, `react-dom`,
  `react-router-dom`, `@tanstack/react-query`, `framer-motion`,
  `@fontsource/geist-sans`, `@fontsource/geist-mono`. **Seven.** No component
  library, no charting library, no HTTP client, no state library beyond
  React Query.
- **Two runtime CDN `<script>`s (`index.html`), both documented exceptions:**
  - `https://accounts.google.com/gsi/client` (Google Identity Services) — consumed
    by `GoogleSignInButton.tsx` via `window.google.accounts.id`.
  - `https://checkout.razorpay.com/v1/checkout.js` (Razorpay Checkout) — consumed
    by `useRazorpayCheckout.ts` via `window.Razorpay`.
- **Fonts** are bundled (`@fontsource`, imported in `main.tsx`): Geist Sans
  400/500/600, Geist Mono `latin-400`. No font CDN.
- **Dev API access:** `vite.config.ts` proxies `/api` → `http://localhost:8000`
  (override `VITE_API_PROXY_TARGET`). No CORS config anywhere — same‑origin by
  design (C2 §4.7).

### 3.2 Provider stack (traced to `src/App.tsx` + `src/routes/ProtectedRoute.tsx`)

```
<ThemeProvider>                     src/lib/theme/ThemeProvider.tsx
  <QueryClientProvider>             singleton from src/lib/query-client.ts
    <AuthProvider>                  src/lib/auth/AuthProvider.tsx
      <BrowserRouter>
        <AppRoutes>                 src/routes/AppRoutes.tsx
          /login /register /verify-email      (public, no shell)
          <ProtectedRoute>          src/routes/ProtectedRoute.tsx
            status 'loading'  → full-page loader (NOT a redirect)
            status 'unauthenticated' → <Navigate to="/login">
            status 'authenticated' →
              <TenantProvider>      src/lib/tenant/TenantProvider.tsx
                <AppShell>          src/components/layout/AppShell.tsx
                  <TopNavbar/>
                  <main><Outlet/></main>   the matched page renders here
```

**Key structural facts:**
- **`TenantProvider` mounts only inside `ProtectedRoute`, only when
  `status === 'authenticated'`.** Tenant context does not exist for the public
  routes. (`ProtectedRoute.tsx:38`.)
- **`ThemeProvider` is outside everything** — theme is display chrome, works
  provider‑less in tests (`theme-store.ts` header comment; `ThemeProvider.tsx`
  uses `useSyncExternalStore`).
- `AppShell` constrains page content to `max-w-[1400px] p-6` and renders
  `<TopNavbar/>` above `<Outlet/>`.
- `AppRoutes` catch‑all: `<Route path="*" element={<Navigate to="/" replace/>}/>`
  → `/` → `index` redirect → `/overview`.

### 3.3 Data layer

- **One fetch wrapper:** `src/lib/api-client.ts` `request()`. Every API call
  except three raw‑fetch exceptions goes through it (§5.2).
- **One error shape:** `src/lib/api-error.ts` `ApiError` (`status`, `message`,
  `code?`, `fieldErrors`). `ApiError.network()` → `status: 0`.
- **Server‑state cache:** `@tanstack/react-query`, singleton `queryClient`
  (`src/lib/query-client.ts`): `retry: false`, `refetchOnWindowFocus: false`,
  `staleTime: 30_000`, `mutations.retry: false`. **`retry: false` is load‑bearing**
  — the api‑client already performs the one refresh‑and‑retry that matters; a
  generic retry on top would replay failed requests and mask real errors.
- **Cache keys:** `src/lib/query-keys.ts` — the structural half of tenant
  isolation (§6.3).
- **No `useMutation` anywhere** — confirmed by grep. Every mutation is a plain
  `async` function + `useState`, page‑owned, followed by
  `queryClient.invalidateQueries({ queryKey })`.

### 3.4 Test infrastructure (context only — tests are evidence, not audited artifacts)

- **Vitest + jsdom + Testing Library + MSW.** `src/test/setup.ts`,
  `src/test/msw/{server,handlers}.ts`, `src/test/fixtures.ts` (291 lines — shared
  tenant/user fixtures + MSW handlers).
- **~30 test files, ~5,900 lines.** The functional contracts (what makes an area
  "A") are encoded here. The largest: `SubscriptionPage.test.tsx` (870),
  `OverviewPage.test.tsx` (464), `MembersPage.test.tsx` (331),
  `api-client.test.ts` (328), `RegisterPage.test.tsx` (270),
  `auth-context.test.tsx` (196), `identity-reset.test.tsx` (193).
- Two named **signature tests** for tenant isolation:
  `src/lib/tenant/__tests__/tenant-isolation.test.tsx`,
  `src/lib/tenant/__tests__/tenant-context.test.tsx`.

### 3.5 Non‑test source inventory (scope reality)

~69 non‑test source files, ~6,700 lines + `theme.css` (338). Breakdown:
`src/routes/` 20 files ~3,100 lines · `src/components/` 10 files ~830 ·
`src/components/layout/` 11 files ~880 · `src/lib/` ~24 files ~1,150 ·
`src/` root 3 files ~85.

---

## 4. Route inventory

`AppRoutes.tsx` defines **7 real routes + 2 redirects**.

**Every route's page component is class B (visual composition replaceable) with an
enumerated set of frozen‑A behaviours** — except `ProtectedRoute` itself, which is
pure‑A (no visual surface). No route component is C or D as a whole (the D‑class
coupling lives in the `lib/*` layer and in `useRazorpayCheckout`, which the pages
consume). The table below gives access + the A/D behaviour each page must preserve;
the shared‑component visual dependencies are in §12.

| Route | Access | Component (lines) | A/D coupling (traced) |
|---|---|---|---|
| `/login` | public, no shell | `LoginPage` (121) | **A:** 401 → one generic message via `messageFor`, **must not** distinguish unknown‑email vs wrong‑password (C2 §7 / `auth-context.ts` docstring). `isAuthenticated` → `<Navigate to="/workspace">`. On success → `navigate('/workspace')`. Invokes `useAuth().login`. Hosts `GoogleSignInButton`. Page composition itself is **B** (Pass 2). |
| `/register` | public, no shell | `RegisterPage` (238) | **A:** **no auto‑login after register** (email‑verification gate — an unverified account cannot obtain tokens). `POST /auth/register/` → "check your email" state + `POST /auth/resend-verification/`. Field errors via `ApiError.fieldErrors` (email/password). "email already registered" **is** disclosed (unavoidable for signup; distinct from Login's rule). Page composition **B**. |
| `/verify-email` | public, no shell, **outside `ProtectedRoute`** | `VerifyEmailPage` (167) | **A:** `POST /auth/verify-email/` fired **exactly once** — `firedRef` (never reset) + `mountedRef` (reset per effect) guard StrictMode's mount→cleanup→mount double‑fire, which here shows a false failure because the token is single‑use. Missing `?token=` → error state, no request. Backend's generic `{detail}` rendered verbatim, cases never distinguished. Page composition **B**. |
| `/` | protected wrapper | `ProtectedRoute` (42) | **A:** status `'loading'` → full‑page loader, **not** a redirect (the on‑load silent refresh must resolve first or a valid reload flashes `/login`). `'unauthenticated'` → `<Navigate to="/login">`. `'authenticated'` → mounts `<TenantProvider><AppShell/>`. |
| `index` | — | `<Navigate to="/overview" replace>` | redirect |
| `/overview` | protected | `OverviewPage` (450) | **A:** per‑tile query‑failure isolation is a *contract*, not incidental — **no combined pending/error boolean anywhere**; each tile/panel reads only its own query state. Two independent tenant‑scoped queries (`currentSubscription`, `members`), both refetch on tenant switch via key shape. `404` on subscription → "no subscription" empty state (via `ApiError.status === 404`, never `.code`). Status→Badge maps **copied** from `SubscriptionPage` (§7). Page composition **B**. |
| `/workspace` | protected | `WorkspacePage` (146) | **A:** reads `useTenant()` — **does not re‑fetch** the tenant list. `switchTenant()` is the **only** mechanism that sets the active tenant. A just‑created workspace is selected via a `pendingId` effect that waits for `TenantProvider`'s list to actually contain it (avoids a stale‑closure race). No single‑workspace auto‑select (spec decision). Page composition **B**. |
| `/members` | protected | `MembersPage` (172) | **A:** list is `GET /memberships/` under `queryKeys.members(currentTenantId)` (tenant‑scoped, `enabled: currentTenantId != null`). Empty list treated as an **error** (a tenant always has its OWNER). "Add member" shown only for `role === 'OWNER'` — **UX only**, `IsTenantOwner` on the backend is the boundary. `POST /memberships/` → invalidate the members key. Page composition + `Table` usage **B**. |
| `/subscription` | protected | `SubscriptionPage` (507) | **A + D** — see §7. Largest page. Mixes a **global** query (`plans()`) with a **tenant‑scoped** one (`currentSubscription(tenantId)`); `404` → empty state; `CANCELED` is terminal (no reactivate control at all); `PATCH {plan_id}` for a change vs `PATCH {status:'CANCELED'}` for cancel (the only `status` write); checkout flow (**D**, provider‑coupled). Page composition **B**. |
| `/platform-admin` | protected + **staff** | `PlatformAdminPage` (339) | **A:** client gate is `isStaffResolving` → loader, then `!isStaff` → `<Navigate to="/overview">` — **UX only**; `IsAuthenticated + IsPlatformStaff` on `/api/platform/*` is the boundary (403 to non‑staff). Both queries `enabled: isStaff`, keyed `['global','platform',…]` (a tenant switch must not drop them). Per‑query failure isolation (like Overview). Page + `PlatformBarChart` composition **B**. |
| `*` | — | `<Navigate to="/" replace>` | redirect (also: `showcase-removed.test.tsx` asserts `/dev/showcase` is gone) |

**No `/settings`, `/profile`, `/account`, `/tenant-settings`** (D‑0.2).

### 4.2 Explicit out‑of‑scope confirmation (audit spec §4.2 / redesign master spec §12, §22)

Verified by full endpoint grep of `frontend/src/` (non‑test):

| Backend‑only capability | Frontend surface today | Built in this redesign? |
|---|---|---|
| Usage metering (D5, `UsageRecord`, `/…/meter`) | **None.** No endpoint consumed, no page, no component. | **No.** |
| Proration audit (D6, `ProrationRecord`) | **None.** | **No.** |
| Reconciliation discrepancies (D8, `ReconciliationDiscrepancy`) | **None.** | **No.** |
| Webhook processing / events (D1–D4, `WebhookEvent`) | **None** — internal mechanism, not tenant‑facing. | **No.** |

The only billing‑domain data the tenant frontend consumes is
`GET /subscriptions/current/` (+ `checkout` / `confirm-checkout`) and
`GET /plans/`. This audit **documents these absences; it does not fill them.**
Any "system pulse" or similar idea from UI‑01 is bounded to
subscription + membership data already consumed (UI‑01 §6.2, as reconciled).

---

## 5. Authentication audit

### 5.1 Modules and responsibilities (traced)

| File | Lines | Role | Class |
|---|---|---|---|
| `src/lib/config.ts` | 37 | `API_BASE_URL` (`VITE_API_BASE_URL ?? '/api'`), `apiBasePath()` (path portion, trailing slash stripped, for the `GLOBAL_PATHS` exact match), `GOOGLE_OAUTH_CLIENT_ID` (`?? ''`). The one env‑reading module. | **D** — every request path and the tenant/auth header decision derive from `apiBasePath()`. |
| `src/lib/global-paths.ts` | 57 | Frontend mirror of `apps/tenants/authentication.py::GLOBAL_PATHS`. `GLOBAL_PATHS` (exact‑match `Set`, **never prefix**) + `NO_AUTH_PATHS` (subset, no `Authorization`). `isGlobalPath()` / `isNoAuthPath()`. | **D** — a path drifting from the Python set silently ships a request without `X-Tenant-ID` (backend 400) or leaks a tenant header onto a global route. |
| `src/lib/auth/token-store.ts` | 70 | Access token in **module closure only** (never storage — a persisted bearer token is XSS‑exfiltratable for its 30‑min life). Refresh token in **`sessionStorage`** key `billing.refresh_token` (clears on tab close; explicitly a tradeoff, not best practice — the real fix is an HttpOnly cookie, needs backend). All accessors wrapped in `try/catch` (locked‑down privacy modes throw). | **D** — token lifetime/storage is security‑sensitive. |
| `src/lib/auth/refresh.ts` | 87 | `performRefresh()` → raw `fetch POST /auth/refresh/` (cannot route through api‑client — recursion). Handles SimpleJWT rotation (`ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`): a new `refresh` in the response **must** replace the stored one. Non‑2xx → `clearTokens()`. Transport failure → keep token (retry later). `refreshOnce()` **coalesces** concurrent callers into one round trip via an `inFlight` promise — critical, because with rotation on, N parallel refreshes would blacklist the token mid‑flight. | **D** — the coalescing is the difference between "a burst of 401s recovers" and "the user is logged out". |
| `src/lib/auth/session.ts` | 33 | `onSessionEnded(listener)` pub/sub + `endSession()` (clear tokens, notify all listeners). Lets the non‑React api‑client signal "session over" without depending on React or the router. Idempotent. | **D** — the seam between a failed request deep in a fetch and the React auth state. |
| `src/lib/auth/logout.ts` | 40 | `logoutOnce()` → raw `fetch POST /auth/logout/` with `{ refresh }` + `Authorization` header, `keepalive: true`, fire‑and‑forget (`.catch` swallows). Not routed through api‑client for the same reason as `refresh.ts` (a 401→refresh→retry→endSession cycle is nonsense for a request whose job is to end the session), plus it needs to read both tokens synchronously before the caller's `endSession()` clears them. | **D** — ordering‑sensitive; blacklists the refresh token server‑side. |
| `src/lib/auth/AuthProvider.tsx` | 157 | React seam. `status: 'loading' | 'authenticated' | 'unauthenticated'`; `userEmail` (login‑session only — no endpoint recovers it after a silent‑refresh reload); `login`, `loginWithGoogle`, `logout`. Bootstrap effect (see 5.4). `onSessionEnded` subscription → `clearIdentityState()` + `setUserEmail(null)` + `setStatus('unauthenticated')`. | **D**. |
| `src/lib/auth/auth-context.ts` | 49 | `AuthContext` + `useAuth()` (throws outside provider). Type‑only + hook, split from the provider for the `react-refresh` lint rule. | **D** (contract surface). |
| `src/lib/auth/index.ts` | 8 | Public surface: `AuthProvider`, `useAuth`, types, `onSessionEnded`, `getAccessToken`/`getRefreshToken`/`clearTokens`. | **D**. |

### 5.2 The three raw‑fetch paths (bypass `apiClient` — by design)

1. `api-client.ts:104` — the wrapper's own `fetch`.
2. `refresh.ts:38` — `POST /auth/refresh/` (recursion avoidance).
3. `logout.ts:31` — `POST /auth/logout/` (`keepalive`, fire‑and‑forget, sync token read).

Any redesign work that "consolidates HTTP calls" must preserve all three as
exceptions. **D.**

### 5.3 `request()` order of operations (`api-client.ts:70‑133`) — the load‑bearing sequence

1. `djangoPath = apiBasePath() + path`; compute `global = isGlobalPath(djangoPath)`,
   `noAuth = isNoAuthPath(djangoPath)`.
2. If a body is present, **`assertNoTenantInBody`** throws on any of
   `tenant_id` / `tenant` / `tenantId` (CLAUDE.md: tenant never in a body).
3. `Content-Type: application/json` set for a body unless already present.
4. Unless `noAuth`: `Authorization: Bearer <getAccessToken()>` if an access token
   exists.
5. Unless `global`: `X-Tenant-ID: <getCurrentTenantId()>` **if a tenant id is set**
   (else the header is omitted and the backend answers 400 — in practice
   `TenantProvider` guarantees one before any tenant‑scoped query runs).
6. `fetch`. `AbortError` re‑thrown as‑is; any other throw → `ApiError.network()`
   (`status: 0`).
7. **401 handling (`!noAuth` only):** if not already a retry → `await refreshOnce()`;
   on success → **one** recursive `request(..., isRetry=true)`. If refresh failed
   **or** the retry still 401 → `endSession()` + throw the `ApiError`.
   **Never more than one retry, never a loop** (`isRetry` flag). Verified by
   `api-client.test.ts`.
8. Any other `!response.ok` → throw `ApiError.fromBody(...)`.
9. `parseBody` — `204`/empty → `undefined`; JSON parse, falling back to raw text.

**`apiClient` surface:** `get`, `post`, `patch`, `delete` (no `put`).

### 5.4 On‑load bootstrap (`AuthProvider.tsx:69‑103`) — StrictMode‑hardened

- `bootstrapped` ref guards StrictMode's double effect invocation, **but is reset
  to `false` in cleanup** so the second mount re‑runs bootstrap. Without the reset,
  the first run's `cancelled` closure is already `true` when its `await` resolves
  and the second run bails on the guard → `status` stuck on `'loading'` forever on
  any authenticated reload. (A real, documented past hang.)
- Flow: no refresh token → `'unauthenticated'`. Else `await refreshOnce()` → ok
  → `'authenticated'`; not ok → `clearTokens()` + `'unauthenticated'`.

### 5.5 Identity reset (`AuthProvider.tsx:53‑57`, `clearIdentityState`)

`queryClient.clear()` + `setCurrentTenantId(null)` + `clearStoredTenantId()`
(removes `localStorage['billing.last_tenant_id']`). Called on:
- **session end** (`onSessionEnded` handler), and
- **every successful `login()` and `loginWithGoogle()`** — deliberately redundant,
  so a future auth‑flow change can't reintroduce cross‑identity reuse.

The bug it fixes: a logout→login (or Google login) with **no full reload** left
the prior user's React Query cache (incl. `['global','tenants','me']`) and the
`billing.last_tenant_id` hint in place; `TenantProvider` then re‑selected the
prior user's tenant, and the first tenant‑scoped request shipped a stale
`X-Tenant-ID`, which the backend correctly 403s (`not_a_member`). Covered by
`identity-reset.test.tsx` (193 lines).

### 5.6 Auth‑page entry points (pages are **B**, behaviours are **A**)

- **`LoginPage`** — `useAuth().login(email, password)`; `messageFor` maps
  `401 → "Email or password is incorrect."` (generic), `0 → connection`, other →
  server error. On success `navigate('/workspace', {replace:true})`. Early
  `isAuthenticated → <Navigate to="/workspace">`.
- **`RegisterPage`** — client‑side confirm‑password match **before** any request;
  `POST /auth/register/` via `apiClient` (no auth token yet; global + no‑auth
  path). Success → `CheckYourEmail` state (resend button → `POST
  /auth/resend-verification/`). **No token is ever stored here.**
- **`VerifyEmailPage`** — `POST /auth/verify-email/` (global, no‑auth). Single‑fire
  guard (5.6 / §4 table). `ResendForm` → `POST /auth/resend-verification/`.
- **`GoogleSignInButton`** (shared by Login + Register) — loads GIS from the
  `index.html` CDN script; polls `window.google.accounts.id` every 100ms until
  ready; `initialize()` runs **once** (`initializedRef`), `renderButton()` re‑runs
  on theme change (`filled_black` dark / `outline` light — GIS renders static
  markup, no live theme swap). Callback → `useAuth().loginWithGoogle(credential)`
  → `POST /auth/google/` `{ credential }`. Renders `null` when
  `GOOGLE_OAUTH_CLIENT_ID` is empty (the whole button silently absent).
  **D** for the GIS integration + `window.google` global + the callback→token
  path; **B** for the container styling / divider layout around it.

### 5.7 Backend contracts these depend on (verified, `config/urls.py` + `apps/users/`)

| Endpoint | View | Auth | Notes |
|---|---|---|---|
| `POST /api/auth/login/` | (SimpleJWT‑derived) `name="token_obtain_pair"` | none | returns `{ access, refresh }`. Email‑verified gate in `apps/users/auth.py` — byte‑identical `AuthenticationFailed` for wrong‑password vs unverified (CLAUDE.md). |
| `POST /api/auth/refresh/` | `TokenRefreshView` | none | rotation on → returns new `{ access, refresh }`. |
| `POST /api/auth/register/` | `RegisterView` | none | → 201 `{ id, email }`, **no tokens**. |
| `POST /api/auth/logout/` | `LogoutView` | Bearer | blacklists `{ refresh }`; malformed/expired/already‑blacklisted → 400 not 500. |
| `POST /api/auth/verify-email/` | `VerifyEmailView` | none | single generic `{ detail }` for invalid/expired/used. |
| `POST /api/auth/resend-verification/` | (rate‑limited, `ScopedRateThrottle` 5/hr) | none | non‑disclosing — identical response always. |
| `POST /api/auth/google/` | `GoogleSignInView` | none | `{ credential }` → `{ access, refresh }`. |
| `GET /api/users/me/` | `MeView` | Bearer | `{ id, email, is_staff }` (**D‑0.3**). |

All of `/api/auth/*` and `/api/users/me/` are in the frontend `GLOBAL_PATHS`
mirror; `/api/auth/{login,refresh,register,verify-email,resend-verification,google}`
are additionally in `NO_AUTH_PATHS`. `/api/auth/logout/` and `/api/users/me/` are
global but **authenticated** (deliberately not in `NO_AUTH_PATHS`).

---

## 6. Tenant lifecycle audit

### 6.1 Modules (traced)

| File | Lines | Role | Class |
|---|---|---|---|
| `src/lib/tenant/current-tenant.ts` | 42 | Module‑closure holder for the active tenant id (the value the api‑client sends as `X-Tenant-ID`). `get/setCurrentTenantId`. `LAST_TENANT_STORAGE_KEY = 'billing.last_tenant_id'`, `clearStoredTenantId()`. **Explicitly NOT authorization** — the backend re‑resolves `Membership` from JWT + header every request. | **D** — non‑React holder the api‑client reads on every tenant‑scoped call. |
| `src/lib/tenant/TenantProvider.tsx` | 126 | Fetches `GET /tenants/me/` under `queryKeys.tenantsMe()` (`['global','tenants','me']`). Resolves the active tenant (6.2). **Writes `setCurrentTenantId(selectedId)` DURING RENDER** (6.3). Mirrors selection to `localStorage` in an effect. `switchTenant`, `refetch`. Derives `status: loading|error|empty|ready`. | **D**. |
| `src/lib/tenant/tenant-context.ts` | 37 | `TenantContext` + `useTenant()` (throws outside provider). `TenantContextValue`: `tenants`, `currentTenant`, `currentTenantId`, `status`, `switchTenant`, `refetch`. | **D** (contract). |
| `src/lib/tenant/types.ts` | 17 | `TenantRole = 'OWNER'|'MEMBER'`; `TenantMembership` (`id,name,slug,created_at,is_active,role` — backend flattens `role` onto the serialized `Tenant`); `TenantStatus`. | **A** (shape mirrors backend serializer). |
| `src/lib/tenant/index.ts` | 7 | Public surface. | **D**. |

### 6.2 Active‑tenant resolution (`TenantProvider.tsx:64‑75`)

On every change to `query.data` (the tenant list): keep the current selection if
it's still in the list; else use the stored `localStorage` id **if it's in the
list** (a stale stored id is **ignored, not an error** — "removed from your
last‑selected workspace between sessions"); else `list[0]?.id ?? null`.

### 6.3 The render‑time header write (`TenantProvider.tsx:82‑85`) — deliberate, load‑bearing

```
if (getCurrentTenantId() !== selectedId) {
  setCurrentTenantId(selectedId)
}
```

Done **during render**, not in an effect: `current-tenant.ts` is an external
(non‑React) store, the write is idempotent, and a child that mounts on the same
render as the selection (e.g. `MembersPage`'s tenant‑scoped query) **must** see
the header before its first fetch — a parent effect runs *after* child effects,
which is too late. This exact bug shipped once (C4): `GET /memberships/` fired
with no header → 400 (real backend) / `[]` (tests). Any redesign of `TenantProvider`
**must keep the synchronous write**. **D.**

### 6.4 Tenant cache isolation (`query-keys.ts`) — the structural guarantee

- **Tenant‑scoped keys carry the tenant id as an explicit segment:**
  `members(id) → ['tenant', id, 'members']`,
  `currentSubscription(id) → ['tenant', id, 'subscription', 'current']`.
  Mirrors the backend's `TenantScopedManager.for_tenant(tenant)` taking `tenant`
  explicitly rather than from ambient state.
- **Global keys are namespaced `['global', …]`:** `currentUser`, `tenantsMe`,
  `plans`, `platformTenants`, `platformStats`. A tenant switch **must not** drop
  these.
- When the active tenant changes, the *key* changes → the previous tenant's
  cached data becomes a different, inactive cache entry with **no render path**
  under the new tenant. Isolation is a property of the key shape, **not** of any
  component remembering to call `invalidate` or `clear`.
- Exports `TENANT_KEY_ROOT = 'tenant'`, `GLOBAL_KEY_ROOT = 'global'` for
  tests/tooling.
- **Verified end‑to‑end** by `tenant-isolation.test.tsx`: switching tenant with a
  mounted consumer shows the new tenant's data (or loading), never a flash of the
  old; and crucially asserts isolation did **not** come from nuking the cache
  (`getQueryData(members(A))` and `getQueryData(tenantsMe())` both survive).

### 6.5 `X-Tenant-ID` end‑to‑end path

`switchTenant(id)` → `setSelectedId` → render → `setCurrentTenantId(id)` (holder)
→ `apiClient.request()` reads `getCurrentTenantId()` → sets `X-Tenant-ID` unless
`isGlobalPath(djangoPath)`. Backend `TenantJWTAuthentication` re‑resolves
`Membership` from JWT + header (a forged/stale value → 403/404, never access).

### 6.6 Tenant CRUD from the frontend

- **List:** `GET /tenants/me/` (global, authenticated) — `TenantProvider` only.
- **Create:** `POST /tenants/` (global — no tenant exists yet; authenticated) —
  `CreateWorkspaceModal` → `WorkspacePage.handleCreated` primes
  `queryKeys.tenantsMe()` cache + sets `pendingId` → effect selects it. `slug`
  duplicate → `{ slug: [...] }` inline field error (not a toast).
- **No update / delete** of a tenant from the frontend. (No tenant‑settings page —
  D‑0.2.)

### 6.7 Backend contract (verified)

`GET /api/tenants/me/` → `MyTenantsView` (flattens `role` onto each `Tenant`).
`POST /api/tenants/` → create as OWNER. Both in `GLOBAL_PATHS` (frontend + backend).

---

## 7. Subscription / billing audit

**Files:** `SubscriptionPage.tsx` (507), `PlanGrid.tsx` (183),
`ChangePlanConfirmModal.tsx` (94), `CancelSubscriptionModal.tsx` (99),
`useRazorpayCheckout.ts` (109), `format.ts` (98, shared). Contract test:
`SubscriptionPage.test.tsx` (870), `CancelSubscriptionModal.test.tsx` (92),
`useRazorpayCheckout.test.tsx` (89).

### 7.1 The two‑query mix (`SubscriptionPage.tsx:127‑147`) — **A**

| Query | Key | Path | `X-Tenant-ID`? | Tenant switch behaviour |
|---|---|---|---|---|
| Plans | `queryKeys.plans()` = `['global','plans']` | `GET /plans/` | **No** (`/api/plans/` in `GLOBAL_PATHS`) | **Must not** refetch or drop |
| Current subscription | `queryKeys.currentSubscription(tenantId ?? '∅')` | `GET /subscriptions/current/` | **Yes** | Key changes → previous tenant's subscription can never render under the new one; `enabled: currentTenantId != null` |

This is the first page in the app to mix a global and a tenant‑scoped query; a
signature test in `SubscriptionPage.test.tsx` asserts plans is fetched once and
not refetched on switch while subscription is.

### 7.2 Subscription state handling — **A**

- **`404` from `/subscriptions/current/` is NOT an error** — it is "this tenant has
  no subscription yet", a legitimate empty state. Detected as
  `subError instanceof ApiError && subError.status === 404`. **Never** `.code`
  (an unrelated DRF string). Only a non‑404 failure gets the retry Alert.
- **`CANCELED` is terminal** (master spec §B.5). There is **no reactivate control —
  not a disabled one, none at all**, because no such transition exists to attempt.
  Plan selection is also closed off (`canManage = isOwner && currentTenantId &&
  !canceled`) — the backend rejects a plan change on a terminal subscription and
  the page stops offering it.
- **Status → Badge variant map** (`SubscriptionPage.tsx:96‑101`) — this file is the
  **source of truth**:
  `ACTIVE→success, TRIALING→warning, PAST_DUE→danger, CANCELED→neutral`.
  **Copied verbatim** (not imported — the maps are module‑private and the file was
  frozen for the stage that needed them) into:
  - `OverviewPage.tsx:40‑45` (`STATUS_VARIANT` / `STATUS_LABEL`)
  - `PlatformAdminPage.tsx:52‑66` (+ its own `NONE` key for a tenant with no sub)

  **Three copies.** Redesign master spec §7 requires this mapping preserved and
  kept in sync — a restyle of `Badge` must not touch these values. **A.**

### 7.3 Mutations — page‑owned, `plan_id` vs `status` — **A**

All via `apiClient.patch('/subscriptions/current/', body)` (tenant‑scoped):

| Action | Body | Trigger | Gate |
|---|---|---|---|
| Change plan | `{ plan_id }` **only** | `PlanGrid` select (existing sub) → `ChangePlanConfirmModal` confirm | `canManage`; backend `IsTenantOwner` + `SubscriptionService.change_plan` (rejects CANCELED → `IllegalStateTransition` keyed to `plan_id`) |
| Cancel | `{ status: 'CANCELED' }` **only** — the one `status` write on the page | danger‑zone footer button → `CancelSubscriptionModal` type‑to‑confirm | `canCancel`; backend `IsTenantOwner` + `LEGAL_TRANSITIONS` guard (keyed to `status`) |

`assertNoTenantInBody` in the api‑client guarantees no `tenant_id` slips in.
On success → `queryClient.invalidateQueries({ queryKey: subscriptionKey })`.
Error ladder (`messageFor`, `SubscriptionPage.tsx:494`): `fieldErrors.plan_id` →
`fieldErrors.status` → `403` → `0` → server message → generic.

### 7.4 Checkout / subscribe flow — **D** (provider‑coupled)

When there is **no** subscription, selecting a plan runs `startCheckout`:

1. `POST /subscriptions/current/checkout/` `{ plan_id }` → `{ razorpay_subscription_id,
   razorpay_key_id, plan }` (`CheckoutStartResponse`). Backend `IsTenantOwner`
   (`billing/views.py:155`).
2. `useRazorpayCheckout().openCheckout({...})` — constructs `new window.Razorpay({
   key, subscription_id, name, description, handler, modal.ondismiss, theme })`
   and calls `rzp.open()`. The hook **does not talk to the Tenora backend**.
   `settled` flag ensures exactly one of confirmed/dismissed/failed fires.
3. On Checkout success → `handler(response)` → `confirmCheckout(payload)` →
   `POST /subscriptions/current/confirm-checkout/` `{ razorpay_payment_id,
   razorpay_subscription_id, razorpay_signature }` (`CheckoutSuccessPayload`).
   Backend `IsTenantOwner` (`billing/views.py:214`) — **verifies the handshake
   only, activates nothing**.
4. UI shows an **ephemeral** "processing" state (`checkoutState`, lost on reload).
   Local activation waits for D3's webhook. On confirm failure → an honest
   "we couldn't verify" message; the webhook remains authoritative.
5. `onDismissed` → "checkout closed, nothing changed" info Alert.
   `onFailed(message)` → danger Alert (from `payment.failed` event `error.description`).

**Provider‑boundary facts (D‑0.6):** the frontend knows it is Razorpay — field
names, `window.Razorpay`, `checkout.razorpay.com` CDN script, the hook name.
`useRazorpayCheckout.ts` is **D**: no visual redesign may alter what it reveals
about the adapter boundary without sign‑off (redesign master spec §25).
The surrounding page copy / Alert styling is **B**.

### 7.5 `PlanGrid.tsx` — dual mode — **A** (semantics) / **B** (card visuals)

- **Selectable** (`onSelect` given — OWNER, non‑CANCELED): a real
  `role="radiogroup"` of `role="radio"` `<button>`s with a **roving tabindex**
  (checked card is the tab stop, falls back to index 0). Arrow/Home/End move focus
  but **do not select** — activation is explicit (Enter/Space/click), because
  strict WAI‑ARIA select‑on‑arrow would fire a real plan change on every keystroke
  while browsing. There is no `RadioGroup` primitive in `components/` (C1‑deferred);
  the only other ARIA‑radio in the repo is `TenantSwitcher`'s `menuitemradio`
  (a menu pattern, not reusable here).
- **Read‑only** (`onSelect` omitted — MEMBER, or CANCELED): a plain `<ul>` marking
  the current plan. Disabled radios were rejected as dishonest.

The **keyboard semantics are A** (a redesign must preserve the roving tabindex and
the "arrow moves, doesn't select" rule); the card layout/typography is **B**.
Full accessibility detail → §16 (Pass 2).

### 7.6 `CancelSubscriptionModal.tsx` — type‑to‑confirm — **A** (the gate) / **B** (visuals)

- Destructive button stays `disabled` until `typed.trim() === workspaceName.trim()`
  (trim‑both‑sides forgives copy‑paste whitespace; otherwise exact, case‑sensitive).
- `hasUnsavedChanges={typed.length > 0}` → a stray backdrop click won't discard a
  half‑typed confirmation (Escape / close button / "Keep subscription" still work).
- Field resets on close (`useEffect` on `!open`).
- Copy honesty is a **contract** (`cancellation-spec.md` §1/§4.4): the text claims
  no refund, no access gating, no "start again later" — because none exist.

### 7.7 `format.ts` — shared money/date — **A** (money arithmetic) / **C** (could move, low value)

- `formatMoney(cents, currency)` — minor‑unit exponent from
  `Intl.NumberFormat(...).resolvedOptions().maximumFractionDigits`, **not** a
  hardcoded `/100` (JPY has 0 minor units). `RangeError` on a bad currency code →
  `"<amount> <CODE>"` fallback rather than blanking a billing page. **CLAUDE.md:
  "Never floats. Never a hardcoded `$`."** — this file is why. The integer‑cents
  discipline is **A**.
- `formatDate(iso)` — `toLocaleDateString`, em‑dash fallback on unparseable.
- `formatRelativeDate(iso)` — local‑midnight day diff (an 11pm render won't say
  "in 0 days" for tomorrow), `Intl.RelativeTimeFormat` `numeric:'auto'`.
- Consumers: `SubscriptionPage`, `OverviewPage`, `PlatformAdminPage`,
  `ChangePlanConfirmModal`, `PlanGrid`. (`MembersPage` keeps a *local* `formatJoined`
  — a pre‑existing minor duplication, noted for §20 Pass 2.)

---

## 8. Members / team audit

### 8.1 A/D coupling (this pass)

- **List:** `GET /memberships/` under `queryKeys.members(currentTenantId ?? '∅')`
  — tenant‑scoped, `enabled: currentTenantId != null`. Switching tenant swaps
  cache entry and refetches (never shows the previous tenant's members) — §6.4. **A.**
- **Empty = error:** `data.length === 0` renders the danger Alert, not a cheerful
  empty state — a tenant always has its creating OWNER, so zero means something is
  wrong. **A** (business‑state interpretation).
- **RBAC:** "Add member" button rendered only when `role === 'OWNER' &&
  currentTenantId`. **UX only** — `IsTenantOwner` on `POST /api/memberships/` is
  the boundary; a MEMBER reaching the modal via a stale render gets a 403 →
  form‑level Alert (`AddMemberModal.tsx:70`). **A.**
- **Add:** `POST /memberships/` `{ email }` (no role field — the endpoint only ever
  assigns MEMBER; a selector would imply a capability the API lacks). Error ladder:
  `fieldErrors.email` → `404` (unknown user, `detail` shown against the field per
  spec) → `403` → `0` → generic. On success → `invalidateQueries(members key)`.
  No optimistic insert (infrequent action; server row order stays authoritative). **A.**
- **No remove / role‑change** from the frontend. (`apiClient.delete('/memberships/')`
  exists in the client surface but **is not called by any page** — grep confirms
  only the `get`/`post` are used. It appears in `api-client.test.ts` only.)

### 8.2 Visual layer — **B**

- **`MembersPage`** — `<section className="mx-auto max-w-3xl">`, a flex header
  row (`h1` + conditional "Add member" `<Button>`), a muted lede `<p>`, then a
  branch: `!currentTenantId` → info `Alert` linking `/workspace` · `isPending` →
  `<Skeleton count={5} height={52}>` · `isError || isEmpty` → danger `Alert` with
  a Retry `<Button size="sm" variant="secondary">` · else `<Table>`.
- **`Table` columns:** `email` (a `<span className="block max-w-[22rem] truncate"
  title={m.email}>`), `role` (`roleBadge` → `<Badge variant={OWNER?'accent':'neutral'}>`),
  `joined` (`<span className="whitespace-nowrap">` + local `formatJoined` —
  **D‑0.10**).
- **`renderMobileCard`** (< 768px): stacked email `<span>` + a `<span>` row of
  `roleBadge` + "Joined …". Same data, list layout.
- **`AddMemberModal`** — `<Modal size="form">` (480px, full‑screen sheet
  `< 768px`), a `<form id="add-member-form">` submitted by a footer `<Button
  type="submit" form={FORM_ID}>`; single `<Input>` with `helperText` toggling
  between the format hint and `emailError`; `<Alert variant="danger">` for
  form‑level (403/network) errors; `hasUnsavedChanges={email.trim() !== ''}`.
- All spacing/typography is token utilities; nothing here is C or D. The **A**
  behaviours (§8.1) sit under this visual layer unchanged.

---

## 9. Overview / dashboard audit

**File:** `OverviewPage.tsx` (450). Contract test: `OverviewPage.test.tsx` (464).

### 9.1 A coupling (this pass)

- **Two independent tenant‑scoped queries:** `currentSubscription(tenantId)` and
  `members(tenantId)`, both `enabled: currentTenantId != null`, both refetch
  together on tenant switch via key shape (no new keys — reuses
  `SubscriptionPage`/`MembersPage` conventions).
- **Per‑tile failure isolation is the page's actual job, not incidental**
  (`stage-c6-spec.md` §1): there is **no combined `pending`/`error` boolean
  anywhere**. Each KPI tile / panel reads only its own query's `isPending` /
  `isError`. A subscription failure cannot blank the members panel and vice‑versa.
  This is **A** — a redesign that introduces a shared loading gate would regress
  the contract.
- **`404` on subscription → "no active subscription"** empty state (same
  `ApiError.status === 404` rule as `SubscriptionPage`, applied independently so a
  subscription failure is never confused with a members failure).
- **Members empty → treated as failure** (same rule as `MembersPage`).
- **Status → Badge maps copied from `SubscriptionPage`** (§7.2) — the 2nd of 3
  copies.
- **No fabricated data:** every value traces to `/subscriptions/current/`,
  `/memberships/`, `/tenants/me/` (via `useTenant()`), or `/users/me/` (via
  `useCurrentUser()`). The "Member since" date is the viewer's own
  `Membership.created_at` found in the members list — **deliberately a different
  date** from the tenant's `created_at` ("Workspace created"); conflating them
  would fabricate meaning.
- `formatRelativeDate` (`format.ts`) renders the renewal date as both absolute and
  relative.

### 9.2 Panels / KPI layout / tile composition — **B**

- `<section className="mx-auto max-w-5xl">`, `h1` (`text-display`) + lede `p`.
- **KPI row:** `<div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2
  xl:grid-cols-4">` holding, per branch: three `<TileSkeleton>` (a local helper —
  `<Card>` + two `<Skeleton>`) · a `sm:col-span-2 xl:col-span-3` danger `Alert` ·
  a hand‑rolled "No active subscription" `<Card>` (**D‑0.9** — not `EmptyState`) ·
  or the four real tiles: **`<Card featured>` "Subscription"** (the **only**
  `featured` in the app — grep‑verified; matches the §C.1a one‑per‑page rule) with
  a `<Badge>` action + plan name + `STATUS_EXPLANATION` line; "Current plan"
  (`<Card>` + `formatMoney` + `INTERVAL_LABEL`); "Renews" / "Period ended"
  (`<Card>` + `formatDate` + `formatRelativeDate`); "Team size" (`<Card>` + count,
  or its own danger `Alert` on members failure — the visible proof of per‑tile
  isolation).
- **Panels:** `<div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-2">` —
  "Members" `<Card>` (5‑row `<ul>` of email + `roleBadge`, "View all" link),
  "Plan" `<Card>` (`<dl>` name/price/period), and a `lg:col-span-2` "Workspace"
  `<Card>` (`<dl>` name/slug(mono)/created/member‑since/role + `ROLE_EXPLANATION`).
- Every panel independently branches `subPending`/`subFailed`/`noSubscription` or
  `membersPending`/`membersFailed` — never a shared boolean (**A**, §9.1).
- Copy constants (`STATUS_EXPLANATION`, `INTERVAL_LABEL`, `ROLE_EXPLANATION`) are
  module‑local — plain‑English "what the state means" lines. Their *tone* is
  something the redesign's editorial‑voice direction (UI‑01 §4.5) would touch;
  the strings themselves are **B**.

---

## 10. Settings / profile / tenant settings audit

**Finding: no settings, profile, account, or tenant‑settings route or page
exists** (**D‑0.2** — `grep -rniE "path=[\"'](settings|profile|account|tenant-settings)"`
on `frontend/src/` returns nothing; `AppRoutes.tsx` has no such `<Route>`).

**All account‑adjacent behaviour, in full:**

| Capability | Where it lives | Backend |
|---|---|---|
| See your email | `useCurrentUser()` → `AuthProvider.userEmail` (login‑session) ‖ `GET /users/me/` ‖ `null` → `UserMenu` renders it or the neutral label "Signed in" | `GET /api/users/me/` |
| Switch theme | `ThemeToggle` (in `UserMenu`, in the `AccountMenu` overlay) → `useTheme().toggleTheme` → `theme-store` → `localStorage['billing.theme']` + `<html data-theme>` | none (client‑only) |
| Log out | `UserMenu` "Log out" `<Button variant="ghost" size="sm">` → `useAuth().logout()` + `navigate('/login', {replace:true})` | `POST /api/auth/logout/` (best‑effort) |
| Create a workspace | `/workspace` → `CreateWorkspaceModal` | `POST /api/tenants/` |
| Switch active workspace | `TenantSwitcher` (navbar) / `WorkspacePage` rows | client selection only |

**Not present anywhere:** change password, change email, delete account, edit
profile (name/avatar), rename a tenant, delete a tenant, transfer ownership,
manage notification preferences, view/rotate API keys, view billing history /
invoices, manage payment methods, session management.

**Redesign implication (not a decision UI‑02 makes):** redesign master spec §11
lists "Settings/Account/Profile, Tenant Settings" as UI‑08 pages. **Building any
of them is new‑feature work, not a re‑skin** — most have **no backend endpoint**
(`config/urls.py` has nothing under `/api/users/<id>/`, `/api/settings/`,
`/api/tenants/<id>/` update/delete). Per audit spec §6 and redesign master spec
§12/§22, this audit **documents the void and does not fill it**. §23 records the
open question.

---

## 11. Platform administration audit

**File:** `PlatformAdminPage.tsx` (339), `PlatformBarChart.tsx` (99). Test:
`PlatformAdminPage.test.tsx` (163), `PlatformBarChart.test.tsx` (64).

### 11.1 Access gating — **A** (UX only; backend is the boundary)

- `const { isStaff, isStaffResolving } = useCurrentUser()`.
- `isStaffResolving` → full‑panel loader. **Deliberately not `resolving`** —
  `resolving` has an `AuthProvider.userEmail` fast path and can be `false` while
  `is_staff` (from the still‑pending `/users/me/` query) is genuinely unknown;
  gating on `resolving` would flash a false "access denied" for a staff member who
  just logged in (`use-current-user.ts:41‑47`).
- `!isStaff` → `<Navigate to="/overview" replace>`.
- **The real boundary:** `IsAuthenticated + IsPlatformStaff` on `/api/platform/*`
  (`apps/platform/views.py:37,63`, `apps/platform/permissions.py`) — 403 to any
  non‑staff caller regardless of what renders. `useCurrentUser().isStaff` defaults
  to `false` until `/users/me/` resolves and on error — the safe default.
- **`is_staff` is the same platform‑tooling concept as Django admin's**
  (`apps/users/serializers.py::MeSerializer` docstring); it is **not** a
  tenant/membership role.

### 11.2 Data — **A** (global keys, `enabled: isStaff`)

| Query | Key | Path | Notes |
|---|---|---|---|
| Stats | `queryKeys.platformStats()` = `['global','platform','stats']` | `GET /platform/stats/` | `enabled: isStaff`. Shape: `total_tenants`, `status_breakdown: Record<StatusKey,number>`, `plan_distribution[]`, `signups_over_time[]`. |
| Tenants | `queryKeys.platformTenants()` = `['global','platform','tenants']` | `GET /platform/tenants/` | `enabled: isStaff`. Shape: `PlatformTenant[]` (`id,name,slug,created_at,member_count,subscription:{plan_name,status}|null`). |

Both keys are **`['global', …]`** — this data is explicitly **not** tenant‑scoped
(cross‑tenant is the whole point), so a tenant switch in the navbar switcher must
not drop it (`query-keys.ts:40‑47`). Both in the frontend `GLOBAL_PATHS` mirror
(no `X-Tenant-ID`) but authenticated. Per‑query failure isolation, like Overview.

### 11.3 `STATUS_VARIANT` / `STATUS_LABEL` — the 3rd copy of the §7.2 map, plus a
local `NONE` key (a tenant with no subscription). **A** — keep in sync.

### 11.4 `PlatformBarChart` — hand‑rolled SVG, deliberately **not** a charting
library (redesign master spec §19; same reasoning that kept GSAP/Three/Lottie
out). Reused 3× (status counts, plan distribution, monthly signups). Every bar
has a visible text label **and** its numeric value as `<text>` — never
colour‑only. Zero‑data → explicit empty message. Uses `var(--color-accent-600)` /
`var(--color-secondary)` / `var(--color-primary)` directly in SVG attributes.
Chart **visual** treatment (bar geometry, colour, the `text-[11px]` sizing) is
**B**; the `role="img"` + `aria-label` (`"<title>: <label> <value>, …"`) and the
"label + value, never colour‑only" rule are **A** (accessibility discipline).
`PlatformAdminPage` composition (KPI `grid-cols-2 sm:grid-cols-3 xl:grid-cols-6`,
the two chart `<Card>`s, the tenant `<Table>`) is **B**.

---

## 12. Shared component inventory

Two tables: **12.A** the coupling‑heavy layer (A/D), **12.B** the visual layer
(B/C). Every consumer list is grep‑verified. Section 4 (routes), this section, and
section 19 (master matrix) are cross‑checked in §19.4.

### 12.A — Coupling‑heavy layer (A / D)

| Component | Lines | Role | Consumers (traced) | Class | Coupling / risk |
|---|---|---|---|---|---|
| `lib/api-client.ts` | 146 | The one fetch wrapper (§5.3) | every page/hook that hits the API; `refresh.ts`/`session.ts`/`token-store.ts`/`global-paths.ts`/`current-tenant.ts` | **D** | 401 refresh/retry loop; `X-Tenant-ID` + `Authorization` decisions; `assertNoTenantInBody`; `ApiError` normalization. A misclassification here breaks every page. |
| `lib/api-error.ts` | 72 | `ApiError` (`status`, `message`, `code?`, `fieldErrors`); `fromBody` understands DRF `{detail}` and `{field:[...]}` | every error path in the app | **A** | Not styling — it is the contract every `catch` block destructures (`.status === 404`, `.fieldErrors.email`, `.status === 0`). Adding/removing a field would ripple through ~15 call sites. |
| `lib/global-paths.ts` | 57 | Exact‑match mirror of backend `GLOBAL_PATHS` / `NO_AUTH_PATHS` | `api-client.ts` | **D** | Security control — drift = silent tenant‑header leak or missing header. |
| `lib/config.ts` | 37 | env reads; `apiBasePath()` | `api-client.ts`, `refresh.ts`, `logout.ts`, `GoogleSignInButton` | **D** | Every request URL + the global/no‑auth decision derives from it. |
| `lib/query-keys.ts` | 53 | all cache keys; global vs tenant partition | every `useQuery` in the app | **D** | The structural half of tenant isolation. A bare key (no `tenantId` segment) reintroduces cross‑tenant leakage. |
| `lib/query-client.ts` | 28 | singleton `QueryClient`; `retry:false` etc. | `App.tsx`, `AuthProvider` (`.clear()`), every page (`useQuery`) | **A** | `retry: false` is depended on by the api‑client's single‑retry design; `staleTime: 30_000`; `.clear()` is called by `clearIdentityState`. No visual surface — behaviour only. |
| `lib/auth/*` (7 files) | ~445 | see §5.1 | api‑client, `App.tsx`, `ProtectedRoute`, `useCurrentUser`, `UserMenu`, auth pages | **D** | token lifetime, refresh coalescing, session‑end pub/sub, identity reset. |
| `lib/tenant/*` (5 files) | ~230 | see §6.1 | `ProtectedRoute`, api‑client (holder), `TopNavbar`/`TenantSwitcher`, every tenant‑scoped page, `AccountMenu` | **D** | render‑time header write; active‑tenant resolution; isolation contract. |
| `routes/ProtectedRoute.tsx` | 42 | auth gate + mounts `TenantProvider`+`AppShell` | `AppRoutes` | **A** | loading‑gate‑before‑redirect ordering (prevents `/login` flash on valid reload). |
| `components/layout/use-current-user.ts` | 67 | resolves email + `isStaff` (+ `isStaffResolving`) | `TopNavbar` (nav append), `AccountMenu`, `UserMenu`, `PlatformAdminPage` | **A/D** | `isStaff` is the client gate source for `/platform-admin`; the `/users/me/` query has **no `enabled` guard** so it fires as soon as the shell mounts. The `isStaffResolving` vs `resolving` distinction is subtle and load‑bearing (§11.1). |
| `routes/useRazorpayCheckout.ts` | 109 | opens Razorpay Checkout; polls `window.Razorpay` | `SubscriptionPage` | **D** | external SDK; the only frontend↔payment‑provider touchpoint; `settled` once‑only guard; provider‑boundary (§7.4, D‑0.6). |
| `components/layout/TopNavbar.tsx` | 144 | sticky bar; primary nav; hamburger < 1024px; hosts `TenantSwitcher` + `AccountMenu` | `AppShell` | **A** (RBAC nav append: `isStaff ? [...NAV_ITEMS, PLATFORM_ADMIN_NAV_ITEM] : NAV_ITEMS`; active‑route styling is multi‑signal — bg + weight + glow, not colour‑only; desktop nav vs mobile panel are **conditionally rendered**, not CSS‑hidden) + **B** (all chrome/spacing/typography) | route list correctness; the `< 1024px` collapse breakpoint. |
| `components/layout/nav-items.tsx` | 78 | `NAV_ITEMS` (4: overview/workspace/members/subscription) + `PLATFORM_ADMIN_NAV_ITEM` (staff) | `TopNavbar` | **A** (the `to` values + the staff‑item separation — "the nav link is UX only; `IsPlatformStaff` on the backend is the real boundary") + **B** (the inline SVG icons) | routes must match `AppRoutes`. |
| `components/layout/TenantSwitcher.tsx` | 245 | the active‑tenant selector; portaled overlay | `TopNavbar` | **A** (`switchTenant` on select + `close()` + focus return; **blocking** inline retry on error — "the rest of the app is unusable without tenant context"; skeleton while loading; empty → link to `/workspace`) + **B** (the overlay: scrim, blur, Framer fade/slide, panel geometry) | tenant switching is the single most important interaction; error state must stay blocking. |
| `components/layout/AccountMenu.tsx` | 134 | avatar → portaled overlay hosting `UserMenu` | `TopNavbar` | **A** (a **genuine** tenant switch — defined→different‑defined id, `prevTenantId` ref guards the initial null→first resolve — closes the menu; `useFocusTrap`) + **B** (the overlay visuals) | the "genuine switch only" guard is subtle. |
| `components/layout/use-disclosure.ts` | 47 | open/close + Escape (focus return) + outside‑pointer close | `TenantSwitcher`, `AccountMenu`, `TopNavbar` mobile panel | **A** (keyboard/focus behaviour) + **C** candidate (Pass 2) | shared plumbing. |
| `components/layout/use-focus-trap.ts` | 84 | focus‑in / Tab‑cycle / focus‑restore / opt‑in scroll‑lock | `TenantSwitcher` (`lockScroll:false`), `AccountMenu` | **A** (accessibility mechanism) | **Deliberately a copy of** `Modal.tsx:45‑96`, not shared — `Modal` is a shipped tested primitive and "this stage has no business refactoring it" (navbar‑redesign §4.2). Pass 2 §20 will note whether a *future* shared extraction is safe. |

### 12.B — Visual layer (B / C)

All eight `components/index.ts` primitives + the remaining layout chrome. **Class
is the component as a whole**; where a single behaviour inside a B component is
frozen, it is called out and also appears in §19's A list.

| Component | Lines | Role | Consumers (grep‑verified) | Class | Notes / frozen‑A carve‑outs / refactor |
|---|---|---|---|---|---|
| `components/Alert.tsx` | 138 | full‑width bar; `variant` info/success/warning/danger; optional `title`, `action` slot; `role="alert"` (assertive, default for `danger`) vs `role="status"` | 12 files: every modal + `LoginPage`/`RegisterPage`/`VerifyEmailPage`/`MembersPage`/`OverviewPage`/`PlatformAdminPage`/`SubscriptionPage`/`WorkspacePage` | **B** | **A carve‑out:** the `assertive ?? variant === 'danger'` → `role` choice is an a11y contract (form errors must announce). Icons are inline SVG, `aria-hidden`. Colour via `border-l-*` + `bg-*/12` tokens. Most‑used primitive. |
| `components/Badge.tsx` | 54 | status pill; `variant` success/warning/danger/neutral/accent; `h-[22px] rounded-sm px-2 text-caption font-medium` | 7 files: `TenantSwitcher`, `MembersPage`, `OverviewPage`, `PlanGrid`, `PlatformAdminPage`, `SubscriptionPage`, `WorkspacePage` | **B** | **A carve‑out:** **throws** if `children` is null/false/empty‑string (`"status must never be conveyed by color alone (§C.8)"`). The five `variant → bg-*/12 text-*` mappings must not be remapped (redesign master spec §7) but their *values* are token‑driven and restyleable. |
| `components/Button.tsx` | 118 | `variant` primary/secondary/ghost/danger; `size` sm/md; `loading` (spinner replaces label, width‑stable via `visibility:hidden`) | 15 files (every page + `EmptyState`, `TenantSwitcher`, `UserMenu`) | **B** | **A carve‑out:** `disabled={disabled || loading}`, `aria-busy={loading}`, `type` defaults to `"button"` (not submit). The `focus-visible:outline-2 outline-offset-2 outline-accent-600` ring is shared across all variants — the a11y baseline. Ghost/primary/glow treatments are pure visual. |
| `components/Card.tsx` | 53 | `rounded-lg border border-subtle bg-raised p-6`; optional `title` (`h2`) + `actions` header row; **`featured`** → `bg-featured` gradient + `shadow-accent-glow` | 6 files: `OverviewPage` (incl. the only `featured` usage), `PlatformAdminPage`, `RegisterPage`, `SubscriptionPage`, `VerifyEmailPage`, `WorkspacePage` | **B** | `featured` is used **exactly once** app‑wide (`OverviewPage` Subscription tile) — matches the §C.1a one‑per‑page rule (**D‑0.9** context). Fully restyleable. |
| `components/EmptyState.tsx` | 52 | centred `icon` (default SVG) + `headline` (`h2`) + `description` + optional `action` slot | **2 files only**: `SubscriptionPage`, `WorkspacePage` (**D‑0.9** — other empty surfaces hand‑roll) | **B** | The default icon uses `text-muted` (decorative — allowed by the §C.8 usage rule). Consolidating all empty surfaces onto this primitive is a **C** refactor (§20.3). |
| `components/Input.tsx` | 60 | `label` (required) + `<input>` + optional `helperText` (turns `text-danger` on `error`); `useId` wiring; `aria-invalid`, `aria-describedby` | 6 files: all four form modals + `LoginPage`/`RegisterPage`/`VerifyEmailPage` | **B** | **A carve‑out:** `aria-invalid={error || undefined}`, `aria-describedby` → helper id, `disabled` opacity. Helper text uses `text-secondary` (readable) never `text-muted` (§C.8). No `<textarea>`/`<select>` sibling exists. |
| `components/Modal.tsx` | 161 | portaled dialog; `size` form(480)/detail(640); `hasUnsavedChanges` (backdrop‑click guard); focus trap + restore + body‑scroll‑lock inline; Escape; `role="dialog"` `aria-modal` `aria-labelledby`; `max-md` full‑screen sheet | 4 files: `AddMemberModal`, `CancelSubscriptionModal`, `ChangePlanConfirmModal`, `CreateWorkspaceModal` | **B** *(shell)* + **A** *(mechanics)* | **A carve‑out:** the focus‑trap / Escape / scroll‑lock / backdrop‑guard logic (`Modal.tsx:45‑96`) is a tested a11y mechanism. `use-focus-trap.ts` is a **deliberate copy** of it (navbar‑redesign §4.2 forbids refactoring `Modal`). The header/footer/padding layout is B. |
| `components/Skeleton.tsx` | 54 | N stacked `animate-pulse bg-overlay` blocks; `role="status" aria-live="polite" aria-busy` + sr‑only label | 7 files: `TenantSwitcher`, `UserMenu`, `MembersPage`, `OverviewPage`, `PlatformAdminPage`, `SubscriptionPage`, `WorkspacePage` | **B** | **A carve‑out:** the `role="status"` + sr‑only label (announces "Loading"). The pulse is CSS `animate-pulse` — disabled by the global `prefers-reduced-motion` rule in `theme.css`. Fully restyleable shape. |
| `components/Table.tsx` | 192 | `columns`/`rows`/`rowKey`; **also** `sortable`(+`aria-sort`,`SortGlyph`), `onRowClick`, `selectedRowKey` (2px reserved selection rail), `sort`/`onSortChange`; `renderMobileCard` → stacked `<ul>` below 768px | **2 files**: `MembersPage`, `PlatformAdminPage` — **both pass only `columns/rows/rowKey/caption/renderMobileCard`** | **B** | **D‑0.8: sort / row‑click / selection are dead code** (grep‑verified unused by pages; exercised only in `Table.test.tsx`). **A carve‑out:** the < 768px stacked‑card transform (never a horizontal scroll — §C.7) and `<caption className="sr-only">`. `useMediaQuery('(min-width: 768px)')`. |
| `components/use-media-query.ts` | 24 | reactive `matchMedia`; **defaults `true`** when `matchMedia` absent (desktop is the fallback) | `Table`, `TopNavbar`, `AccountMenu`, `TenantSwitcher`, `AuthArtPanel` | **A** | Small but load‑bearing — the `true` default decides SSR/old‑jsdom layout. Behaviour only, no visual surface. **Not** C (changing the default flips responsive fallbacks). |
| `components/layout/AppShell.tsx` | 23 | `<div bg-base><TopNavbar/><main className="mx-auto max-w-[1400px] p-6"><Outlet/></main></div>` | `ProtectedRoute` | **B** | The `max-w-[1400px] p-6` container is the single global content frame — the redesign will almost certainly change it. No coupling. |
| `components/layout/Wordmark.tsx` | 42 | accent glyph (`size-7 rounded-md bg-accent-600` "B") + "Billing Engine" label; `labelClassName` lets the navbar hide the label at narrow widths | `TopNavbar` (wrapped in a `<Link>`), `AuthLayout`, `AuthArtPanel` | **B** | The literal text "Billing Engine" and the "B" glyph are the current product identity — redesign territory. Deliberately not a link (callers wrap it). |
| `components/layout/UserMenu.tsx` | 49 | account‑menu body: email line (or "Signed in") + `<ThemeToggle/>` + "Log out" `<Button variant="ghost" size="sm">` | `AccountMenu` (only) | **B** | **A carve‑out:** "Log out" → `useAuth().logout()` + `navigate('/login')`. The `resolving` → `<Skeleton>` vs email vs "Signed in" branch. |
| `components/layout/ThemeToggle.tsx` | 61 | toggle `<button aria-pressed={isDark}>` with a fixed label "Dark mode" + sun/moon icon | `UserMenu` (only) | **B** | **A carve‑out:** `aria-pressed` carries the state; label is fixed (state, not a changing name, is the signal); icon `aria-hidden`. `useTheme().toggleTheme`. |
| `lib/cn.ts` | 11 | `cn(...parts)` — filter falsy + `.join(' ')`. **Not** a Tailwind‑aware merge. | every component | **A** *(shared primitive)* | 11 lines, zero deps. Not C — it is already minimal, and components rely on its "later class wins by source order only, variants are mutually exclusive" contract. |
| `lib/theme/*` (4 files, ~180 lines) | — | `theme-store` (framework‑free source of truth: `data-theme` attr + `localStorage['billing.theme']` + OS‑follow‑until‑chosen + cross‑tab `storage` sync); `ThemeProvider` (`useSyncExternalStore` seam); `theme-context`/`useTheme` (works provider‑less) | `App.tsx`, `ThemeToggle`, `GoogleSignInButton` (re‑render on flip), `AuthArtPanel` (via CSS) | **A** | Theme is "display chrome, not an authorization concern" (its own docstrings) — but the *mechanism* (pre‑paint inline script in `index.html` ↔ store ↔ `<html data-theme>` ↔ `theme.css` selectors) is a coordinated system a redesign must not break. The **token values** it resolves are §17 (fully restyleable); the **plumbing** is A. |

### 12.C — Refactor candidates within the layout hooks

- `use-disclosure.ts` (47) — **C** *(low value, defer)*. It is already a clean
  shared hook used by 3 surfaces; no refactor is needed. If UI‑05 rebuilds the
  navbar, keep it as‑is. **No new dependency implied.**
- `use-focus-trap.ts` (84) — **not C in this phase.** It is a deliberate copy of
  `Modal`'s trap; §20.4 explains why merging them is out of scope for a re‑skin.

---

## 13. Data / API integration map

Every endpoint the **non‑test** frontend consumes, traced to the calling file.

| Method + path | Caller(s) | Query key / mutation | `X-Tenant-ID` | `Authorization` | Backend view / gate |
|---|---|---|---|---|---|
| `POST /api/auth/login/` | `AuthProvider.login` (via `apiClient`) | — | no (global) | no (no‑auth) | SimpleJWT → `{access,refresh}` |
| `POST /api/auth/refresh/` | `refresh.ts` (**raw fetch**) | — | no | no | `TokenRefreshView`, rotation |
| `POST /api/auth/register/` | `RegisterPage` (via `apiClient`) | — | no | no | `RegisterView` → 201 `{id,email}` |
| `POST /api/auth/logout/` | `logout.ts` (**raw fetch**, `keepalive`) | — | no | **yes** | `LogoutView` blacklist |
| `POST /api/auth/verify-email/` | `VerifyEmailPage` | — | no | no | `VerifyEmailView` |
| `POST /api/auth/resend-verification/` | `RegisterPage.CheckYourEmail`, `VerifyEmailPage.ResendForm` | — | no | no | rate‑limited, non‑disclosing |
| `POST /api/auth/google/` | `AuthProvider.loginWithGoogle` | — | no | no | `GoogleSignInView` → `{access,refresh}` |
| `GET /api/users/me/` | `useCurrentUser` | `['global','user','me']` | no (global) | **yes** | `MeView` → `{id,email,is_staff}` |
| `GET /api/tenants/me/` | `TenantProvider` | `['global','tenants','me']` | no (global) | **yes** | `MyTenantsView` (`role` flattened) |
| `POST /api/tenants/` | `CreateWorkspaceModal` | mutation → primes `tenantsMe` cache | no (global) | **yes** | create as OWNER |
| `GET /api/memberships/` | `MembersPage`, `OverviewPage` | `['tenant',id,'members']` | **yes** | yes | `IsTenantMember` |
| `POST /api/memberships/` | `AddMemberModal` | mutation → invalidate members key | **yes** | yes | `IsTenantOwner` |
| `GET /api/plans/` | `SubscriptionPage` | `['global','plans']` | no (global) | yes | plan catalogue |
| `GET /api/subscriptions/current/` | `SubscriptionPage`, `OverviewPage` | `['tenant',id,'subscription','current']` | **yes** | yes | `404` = no subscription (a valid state) |
| `PATCH /api/subscriptions/current/` | `SubscriptionPage` (`changePlan`, `cancelSubscription`) | mutation → invalidate subscription key | **yes** | yes | `IsTenantOwner`; `plan_id` change or `status:'CANCELED'` |
| `POST /api/subscriptions/current/checkout/` | `SubscriptionPage.startCheckout` | mutation | **yes** | yes | `IsTenantOwner` → `{razorpay_subscription_id, razorpay_key_id, plan}` |
| `POST /api/subscriptions/current/confirm-checkout/` | `SubscriptionPage.confirmCheckout` | mutation | **yes** | yes | `IsTenantOwner` — verifies handshake, activates nothing |
| `GET /api/platform/stats/` | `PlatformAdminPage` | `['global','platform','stats']` | no (global) | yes | `IsPlatformStaff` |
| `GET /api/platform/tenants/` | `PlatformAdminPage` | `['global','platform','tenants']` | no (global) | yes | `IsPlatformStaff` |
| *(external)* `POST https://accounts.google.com/gsi/...` | `GoogleSignInButton` (GIS SDK) | — | — | — | Google; not our backend |
| *(external)* `new window.Razorpay(...).open()` | `useRazorpayCheckout` | — | — | — | Razorpay Checkout; not our backend |

**`apiClient.delete`** exists but is called by **no page** (only `api-client.test.ts`).
`GET /api/plans/archived/` is **test fixtures only** (D‑0.5).

**Cache invalidation summary:** every mutation is followed by
`queryClient.invalidateQueries({ queryKey })` for the affected tenant‑scoped key;
`CreateWorkspaceModal` instead **primes** `queryKeys.tenantsMe()` via
`setQueryData`. `AuthProvider.clearIdentityState` calls `queryClient.clear()`
(everything) on login and session‑end.

---

## 14. State‑handling inventory

Legend: ● present · ○ absent (and whether that is correct) · n/a not applicable.
Traced to code. "Perm." = permission‑restricted rendering.

| Page / component | Loading | Success | Empty | Error | Perm. | Disabled | Pending (in‑flight) | Destructive confirm | Responsive |
|---|---|---|---|---|---|---|---|---|---|
| `LoginPage` | ● `Button loading` | ● redirect `/workspace` | n/a | ● generic `Alert` (401→one message; 0→connection; other→server) | n/a | ● inputs `disabled={submitting}` | ● `submitting` | n/a | ● `AuthLayout` |
| `RegisterPage` | ● `Button loading` | ● "Check your email" `Card` state | n/a | ● field `Input error/helperText` + form `Alert` | n/a | ● | ● | n/a | ● `AuthLayout` |
| `VerifyEmailPage` | ● `status:'pending'` "Verifying…" | ● "You're verified" `Card` | n/a | ● "Verification failed" `Alert` + `ResendForm` | n/a | ● resend `Button loading` | ● | n/a | ● `AuthLayout` |
| `ProtectedRoute` | ● full‑page `role="status"` loader | ● mounts shell | n/a | ○ — a dead session routes to `/login` via `onSessionEnded`, not an error UI (correct) | ● `unauthenticated` → `<Navigate>` | n/a | n/a | n/a | ● |
| `WorkspacePage` | ● `Skeleton count={3}` | ● `<ul>` of tenant rows | ● `status:'empty'` → `EmptyState` + "Create workspace" | ● `status:'error'` → `Alert` + Retry | ○ — no per‑role gating (any member can create/select) | n/a | ● `pendingId` after create | ○ (creating a workspace is not destructive) | ● `max-w-[560px]` |
| `MembersPage` | ● `Skeleton count={5}` | ● `<Table>` | **● treated as ERROR** (`Alert`, not an empty state — a tenant always has its OWNER) | ● `Alert` + Retry | ● "Add member" only for OWNER (UX; `IsTenantOwner` is the boundary) | ● `AddMemberModal` inputs `disabled={submitting}` | ● `submitting` | ○ n/a (add is not destructive) | ● `Table.renderMobileCard` < 768px |
| `AddMemberModal` | n/a | ● `onAdded` → close + invalidate | n/a | ● email field error / form `Alert` (403/404/0) | ● 403 → form `Alert` | ● | ● `Button loading` | n/a | ● `Modal max-md` sheet |
| `SubscriptionPage` | ● `Skeleton height={148}` (sub) + `Skeleton count={3}` (plans) | ● subscription `Card` + `PlanGrid` | **● `404` → `EmptyState` "No active subscription"** (distinct from error); plans `[]` → `Alert variant="warning"` | ● non‑404 sub failure → `Alert`+Retry; plans failure → `Alert`+Retry; action failure → `Alert` (error ladder) | ● `canManage` / `canCancel` gate plan selection & the cancel button (OWNER + non‑CANCELED; UX only) | ● `PlanGrid busy={submitting}` (`opacity-60`, radios `disabled`) | ● `submitting`; **ephemeral `checkoutState:'processing'`** (lost on reload — deliberate) | **● `CancelSubscriptionModal` type‑to‑confirm** | ● `max-w-3xl`; `PlanGrid` 1→2→3 cols; `dl` `flex-col sm:flex-row` |
| `PlanGrid` | n/a | ● radiogroup or read‑only `<ul>` | ● (parent handles `plans:[]`) | n/a | ● read‑only `<ul>` when `onSelect` omitted (MEMBER / CANCELED) | ● `disabled={busy}` on radios | ● `busy` → `opacity-60` | n/a | ● `grid sm:grid-cols-2 lg:grid-cols-3` |
| `ChangePlanConfirmModal` | n/a | ● parent closes on success | n/a | ● `error` prop → `Alert` (modal stays open) | n/a | ● footer buttons `disabled={submitting}` | ● `Button loading` | ● (this **is** the confirm step; plain confirm, not type‑to‑confirm) | ● `Modal` |
| `CancelSubscriptionModal` | n/a | ● parent closes on success | n/a | ● `error` prop → `Alert` (stays open) | n/a | ● `disabled={!confirmed}` until name typed; `disabled={submitting}` | ● `Button loading` | **● type‑to‑confirm** (`typed.trim() === workspaceName.trim()`); `hasUnsavedChanges` backdrop guard | ● `Modal` |
| `OverviewPage` | ● per‑tile `TileSkeleton` + `Skeleton` in panels | ● KPI row + panels | ● `404` sub → "No active subscription" `Card`; members `[]` → `Alert` (failure) | **● per‑tile** — sub failure `Alert` in its own tile, members failure `Alert` in the Team tile, independently | ● no `currentTenantId` → `Alert` "Choose a workspace"; owner‑only "Change plan" link | n/a (read‑only page) | n/a | n/a | ● `grid-cols-1 sm:grid-cols-2 xl:grid-cols-4` KPIs; `lg:grid-cols-2` panels |
| `PlatformAdminPage` | ● `isStaffResolving` full‑panel loader; per‑query `Skeleton` | ● KPI row + 2 chart `Card`s + tenant `Table` | ● `!tenants.data.length` → `Card` "No tenants yet"; `PlatformBarChart` zero‑data → explicit message | **● per‑query** — stats `Alert`+Retry, tenants `Alert`+Retry, independently | **● `!isStaff` → `<Navigate to="/overview">`** (UX; `IsPlatformStaff` is the boundary) | n/a | n/a | n/a | ● KPI `grid-cols-2 sm:grid-cols-3 xl:grid-cols-6`; `lg:grid-cols-2` charts; `Table.renderMobileCard` |
| `TenantSwitcher` | ● `Skeleton` pill | ● trigger + portaled `<ul>` | ● `status:'empty'` → "No workspace selected" + `/workspace` link | **● BLOCKING** inline `Alert`‑style bar + Retry ("the rest of the app is unusable without tenant context") | n/a | n/a | n/a | n/a | ● 150→190→230px slot; portaled panel `getBoundingClientRect` |
| `AccountMenu` / `UserMenu` | ● `resolving` → `Skeleton` (email) | ● email or "Signed in" | n/a | ○ — `/users/me/` failure → `email = null` → "Signed in" (graceful, not an error UI) | n/a | n/a | n/a | ● Log out is not gated / not typed | ● `right-4 top-[4.5rem]` fixed panel |

**Gaps worth the redesign's attention (documented, not fixed):**
- **`ChangePlanConfirmModal` has no type‑to‑confirm** — a plan change is a
  billing‑affecting action behind only a plain confirm, whereas cancel has the
  type‑to‑confirm gate. Deliberate (cancel is *irreversible*, a plan change is
  not), but the redesign should decide if the friction gradient is right.
- **Two loader idioms coexist:** `<Skeleton>` (structural, layout‑matching) on
  data pages, and a centred **text** "Loading…" in `role="status"` on
  `ProtectedRoute` and `PlatformAdminPage`'s gate. Not wrong; inconsistent.
- **`WorkspacePage` is not role‑gated at all** — every authenticated user can
  reach it, create a workspace (becoming its OWNER), and select any workspace
  they belong to. Correct per spec (no MEMBER restriction on workspace creation),
  noted so the redesign doesn't add a phantom gate.

## 15. Responsive behavior inventory

**Breakpoints in use (Tailwind v4 defaults — no config override):** `sm` 640 ·
`md` 768 · `lg` 1024 · `xl` 1280. Prefix usage across non‑test source
(grep‑counted): `sm:` ×15, `md:` ×11, `xl:` ×8, `lg:` ×6, `max-md:` ×4. No `2xl:`.

**JS media queries (`useMediaQuery`, grep‑verified — 5 call sites):**
- `'(min-width: 1024px)'` — `TopNavbar` (`isDesktop`: desktop `<nav>` vs hamburger
  panel, **conditionally rendered**, not CSS‑hidden).
- `'(min-width: 768px)'` — `Table` (`wide`: `<table>` vs stacked `<ul>` of
  `renderMobileCard`).
- `'(prefers-reduced-motion: reduce)'` — `AuthArtPanel`, `TenantSwitcher`,
  `AccountMenu` (all three gate Framer motion).
- `'(prefers-color-scheme: light)'` — `theme-store` + the `index.html` inline
  script (theme resolution).

**Per‑surface responsive behaviour (as it exists today):**

| Surface | Desktop | Tablet | Mobile |
|---|---|---|---|
| `AppShell` | `<main className="mx-auto max-w-[1400px] p-6">` — one frame at every width; padding does not shrink below `p-6` (24px) | same | same (24px gutters on a phone — a redesign candidate) |
| `TopNavbar` | `h-16` sticky bar, full `<nav>` inline | **< 1024px:** nav collapses to a hamburger panel (`border-t` block below the bar); wordmark label hidden below `md` (`Wordmark labelClassName="hidden md:inline"`); switcher slot 190px (`sm`) | switcher slot 150px; glyph‑only wordmark; hamburger |
| `AuthLayout` | **≥ 1280 (`xl`):** `grid grid-cols-2` — art panel left 50%, form right 50% | **768–1279 (`md`):** `flex flex-col`; art panel becomes a `h-[36vh]` top banner (`md:block xl:h-full`) | **< 768:** art panel `hidden`; form full‑width, `px-4`, its own `<Wordmark className="md:hidden">` |
| `AuthArtPanel` | tall split geometry | dedicated `@media (min-width:768px) and (max-width:1279.98px)` block re‑proportions the planes/rings + shrinks headline | not rendered |
| `Modal` | centred, `max-w-[480px]` (form) / `[640px]` (detail) | same | **`max-md`:** `h-full max-w-full rounded-none` — full‑screen sheet; backdrop `p-0` |
| `Table` (Members, Platform Admin) | `<table>` | `<table>` (≥ 768) | **< 768:** stacked `<ul>` of `renderMobileCard` — **never a horizontal scroll** (§C.7) |
| KPI grids | `xl:grid-cols-4` (Overview) / `xl:grid-cols-6` (Platform Admin) | `sm:grid-cols-2` / `sm:grid-cols-3` | `grid-cols-1` / `grid-cols-2` |
| `PlanGrid` | `lg:grid-cols-3` | `sm:grid-cols-2` | 1 col |
| `TenantSwitcher` / `AccountMenu` overlays | portaled, positioned by measured rect / fixed geometry | same | panel `max-w-[calc(100vw-1rem)]` |
| Page `<section>` widths | `max-w-3xl` (Members, Subscription), `max-w-5xl` (Overview, Platform Admin), `max-w-[560px]` (Workspace) | fluid down | fluid down, `p-6` gutter from `AppShell` |

**Not a "shrunk desktop":** the app has genuine mobile transforms (stacked table
cards, full‑screen modal sheets, the auth banner). **Gaps:** the `AppShell` 24px
gutter never shrinks; there is no `xs`/`< 400px` handling anywhere; the KPI grids
jump straight `1 → 2` with no intermediate.

## 16. Accessibility inventory (as it exists today — problems documented, not fixed)

### 16.1 Strong, consistent patterns (traced)

| Pattern | Where |
|---|---|
| **`focus-visible:outline-2 outline-offset-2 outline-accent-600`** ring | 13 non‑test files — `Button`, `Input`, `Modal`, `Table`, `ThemeToggle`, `TopNavbar`, `TenantSwitcher`, `AccountMenu`, `PlanGrid`, `LoginPage`, `RegisterPage`, `VerifyEmailPage`, `WorkspacePage`. The single a11y baseline. |
| **`prefers-reduced-motion`** honoured **globally** | `theme.css` `@media (prefers-reduced-motion: reduce)` zeroes all `animation-duration`/`transition-duration`/`transition-delay` + `scroll-behavior:auto`. **Plus** three components disable Framer motion entirely (not slow it): `AuthArtPanel`, `TenantSwitcher`, `AccountMenu` (each via `useMediaQuery`, **not** framer's caching `useReducedMotion`). `data-motion="full"|"reduced"` reflects the path. |
| **Status never colour‑alone** | `Badge` throws without a text label; `PlatformBarChart` renders label **and** value as `<text>` + `role="img"` `aria-label`; every status `Badge` is paired with a `STATUS_LABEL` word. |
| **Focus management on overlays** | `Modal` (inline trap + restore + scroll‑lock), `use-focus-trap` (the copy, for the two menus), `use-disclosure` (Escape → close + return focus to trigger; outside‑pointer close). |
| **Live regions** | `Skeleton` `role="status" aria-live="polite" aria-busy` + sr‑only "Loading"; `ProtectedRoute` / `PlatformAdminPage` gate loaders `role="status" aria-live="polite"`; `Alert` `role="alert"` (assertive, default `danger`) vs `role="status"`. |
| **Semantic structure** | `AuthArtPanel` decorative layers in an `aria-hidden` `.authart__decor`; the eyebrow + headline are real text **outside** it. `NavLink` supplies `aria-current="page"` on the active nav item (asserted by `TopNavbar.test.tsx`). `<caption className="sr-only">` on `Table`. `Modal` `role="dialog" aria-modal aria-labelledby`. |
| **Form fields** | `Input` — `<label htmlFor>` + `useId`, `aria-invalid={error||undefined}`, `aria-describedby` → helper id; helper text uses `text-secondary` (readable), never `text-muted`. |
| **Custom widgets** | `PlanGrid` — `role="radiogroup"` / `role="radio"` + roving tabindex + `aria-checked`; `TenantSwitcher` option `role="menuitemradio"` + `aria-checked`; `ThemeToggle` `aria-pressed` + fixed label. |
| **Reduced‑contrast token discipline** | `theme.css` documents that `text-muted` **fails WCAG AA** and is for decoration only; components that show readable content use `text-secondary` (measured 7.6:1+ dark / 7.9:1+ light). Every dark/light token pair carries a measured ratio in the spec. |
| **Touch targets** | `Button` `size sm` `h-8` / `md` `h-10`; nav links `px-3 py-2`; the hamburger `size-9`; the avatar `size-9`. Mostly ≥ 36px; `Button sm` at 32px is the smallest. |

### 16.2 Gaps / weaknesses observed (NOT fixed — audit spec §6)

1. **`ChangePlanConfirmModal` / `CancelSubscriptionModal` footer buttons are
   passed to `Modal`'s `footer` slot**, which renders them *outside* the
   `overflow-y-auto` body but *inside* the trapped dialog — fine — however the
   **`Modal` focus trap's `FOCUSABLE` query runs once per `open`** and does not
   observe DOM changes; a modal whose body content changes after open (e.g.
   `CancelSubscriptionModal` enabling its danger button once the name is typed)
   still traps correctly (the button was always in the DOM, just `disabled` →
   note `disabled` buttons are excluded from `FOCUSABLE`), so tab‑order shifts
   when it enables. Minor; worth a redesign‑time check.
2. **`AuthArtPanel` `.authart__headline` is a `<p>`, not a heading** — deliberate
   (it's marketing copy and an `<h2>` would precede the form's `<h1>` in DOM), but
   it means the visually‑dominant text on the auth page is not in the heading
   outline. Documented trade‑off in the component; the redesign should reconfirm.
3. **`PlanGrid` arrow keys move focus but the `aria-checked` state does not
   follow** — correct for the "browsing ≠ selecting" decision, but a strict AT
   user expecting WAI‑ARIA radio semantics gets non‑standard behaviour. The
   component documents this explicitly.
4. **`TenantSwitcher` / `AccountMenu` panels use `role="menu"` but contain
   `role="menuitemradio"` (switcher) or arbitrary content (`UserMenu` — a skeleton,
   a toggle button, a logout button)** — `AccountMenu`'s panel is a `role="menu"`
   whose children are not `menuitem`s. Technically loose ARIA. Not a
   keyboard‑operability failure (focus trap + Tab work), but a redesign that
   rebuilds the menus should tighten the roles.
5. **No skip‑link** to bypass the navbar to `<main>`. `sr-only` is used only 3×
   (Skeleton label, Table caption, Button spinner text).
6. **`title=` attributes for truncation reveal** (Members email, Overview ×4,
   Platform Admin, Subscription) — the full value on hover/long‑press. The
   truncated text is still visible so this is progressive enhancement, not a
   hover‑only dependency, but `title` is not keyboard‑accessible.
7. **The `AppShell` full‑page loader in `ProtectedRoute` uses `&hellip;`** as
   visible text inside `role="status"` — announced as "Loading…" which is fine.

### 16.3 A full accessibility *re‑verification* (that every one of these survives
the re‑skin) is UI‑10 acceptance evidence, not something UI‑02 can assert now —
recorded here as the checklist UI‑10 must run (redesign master spec §16, §21).

## 17. Existing visual‑system inventory (factual — NOT redesigned)

**Single source of truth:** `src/styles/theme.css` (338 lines) + `main.tsx` font
imports + the `index.html` pre‑paint theme script. **CLAUDE.md / this file's §3:
`theme.css` is the only place raw colour/size/shadow values may appear**; every
component consumes them via Tailwind utilities.

### 17.1 Mechanism

- Tailwind v4, CSS‑first config: `@import 'tailwindcss'` + an `@theme { … }` block.
  **No `tailwind.config.js`.**
- **Dark is the `:root` default** (the `@theme` block). **Light is a parallel
  override** under `:root[data-theme='light']` (same specificity, emitted after,
  so it wins when the attribute is `light`). An explicit `data-theme="dark"`
  simply fails to match the light block.
- `index.html` inline script sets `data-theme` **before first paint** (stored
  choice → OS → dark). `theme-store` takes over on mount; the attribute stays
  authoritative.
- **Tailwind‑v4 utility‑name coupling (D‑0 context):** token vars deliberately
  drop the role word — `--color-primary` (not `--color-text-primary`) so the
  generated utility is `text-primary` (matching the §C.1 token names) rather than
  `text-text-primary`. One documented side effect: `--color-base` makes
  `text-base` a *colour* utility, shadowing Tailwind's built‑in `text-base`
  font‑size — harmless because the type scale is `text-display/h1/h2/body/label/
  caption/mono`, never `text-base`.

### 17.2 Token families (names + roles; values are in `theme.css`, not reproduced
in bulk here — the redesign replaces them)

| Family | Tokens | Notes |
|---|---|---|
| Surface | `base` (page), `raised` (cards/panels), `overlay` (modals/dropdowns/hover), `subtle` (hairline borders/dividers → `border-subtle`), `strong` (input borders/focused dividers → `border-strong`) | 3 planes + 2 border weights. Dark = cool near‑blacks; light = near‑whites. |
| Text | `primary`, `secondary` (labels/helper — readable), `muted` (**fails AA — decoration only**, documented rule) | |
| Accent | `accent-600` (base — buttons/active nav/focus ring/coloured borders), `accent-500` (emphasis — hover fill **and** accent text), `accent-subtle` (`rgba(...,0.12)` — active nav bg / selected row), `on-accent` (label on an accent‑600 fill — near‑white both themes) | **Cross‑theme note in `theme.css`:** `-600`/`-500` are **roles, not ramp steps** — `-500` is *lighter* than `-600` in dark, *darker* in light (a forced inversion because `-500` doubles as a text colour needing 4.5:1). |
| Status | `success`, `warning`, `danger`, `neutral` — "never the only signal, always paired with a text label" | Light values are darkened hues (a glow‑on‑black hue washes out as text on white); each clears 4.5:1 as Badge text on its own 12%‑alpha tint. |
| Typography | `--font-sans` (`'Geist Sans', system-ui, …`), `--font-mono` (`'Geist Mono', ui-monospace, …`). Scale: `display` 32/40/600 · `h1` 24/32/600 · `h2` 18/26/600 · `body` 14/22/400 · `label` 13/18/500 · `caption` 12/16/400 · `mono` 13/–/400 | Bundled `@fontsource` (sans 400/500/600, mono `latin-400`). **Weight range 400–600 only.** |
| Spacing | Tailwind default (0.25rem = 4px base) kept deliberately — steps 1/2/3/4/6/8/12/16 = 4/8/12/16/24/32/48/64 (the §C.1 scale). rem‑based (scales with user font size). No override. |
| Radius | `sm` 6px (inputs/badges), `md` 10px (buttons/cards), `lg` 16px (panels/modals) |
| Elevation | `--shadow-card` (`0 1px 2px rgba(0,0,0,.4)` dark), `--shadow-overlay` (`0 8px 32px rgba(0,0,0,.6)`), `--shadow-accent-glow` (`0 0 0 1px accent-600, 0 4px 24px rgba(124,92,255,.2)`). Light: softer, cooler‑near‑black, lower alpha (dark shadows "read as bruises" on white). (**D‑0.7:** two plain shadows + one glow, not "shadows [plural] + glow".) |
| Scrim | `--color-scrim` — `rgba(0,0,0,.6)` dark / `rgba(15,15,24,.45)` light. Behind `Modal` + the two navbar overlays. |
| Featured surface | `--gradient-featured` — a `linear-gradient` with `color-mix(accent-600 24% [dark] / 14% [light], raised)`. Only via the `@utility bg-featured` (sets `background-image` only, so `bg-raised` is the fallback if `color-mix` can't parse). |

### 17.3 Custom utilities (`@utility`)

- `num` → `font-variant-numeric: tabular-nums`. A collision‑proof alias for
  `tabular-nums`, used on **every** money/count/ID (`OverviewPage`,
  `SubscriptionPage`, `PlatformAdminPage`, `PlanGrid`, `ChangePlanConfirmModal`).
- `bg-featured` → `background-image: var(--gradient-featured)`.

### 17.4 Global base rules (`@layer base`)

`:root { color-scheme: dark }` / `[data-theme='light'] { color-scheme: light }`;
`body` — `margin:0`, `bg-base`, `text-primary`, `font-sans`, `text-body` size +
line‑height, `-webkit-font-smoothing: antialiased`, `text-rendering:
optimizeLegibility`.

### 17.5 What the redesign owns vs must not break

- **Owns (all fully restyleable):** every token *value*, the type scale numbers,
  radius numbers, shadow definitions, the featured gradient, spacing (if it wants
  to move off 4px — though rem‑based is an a11y asset).
- **Must not break:** the **dark‑default + light‑override** mechanism; the
  pre‑paint `index.html` script contract; the Tailwind‑v4 utility‑name coupling
  (renaming a token renames its utility across ~69 files); the `num` utility
  contract; the global `prefers-reduced-motion` reset; `theme.css` staying the
  *only* place raw values live.

## 18. AuthArtPanel / existing identity assessment (factual)

### 18.1 Current implementation (`AuthArtPanel.tsx`, 459 lines; `AuthLayout.tsx`, 72;
test `src/routes/__tests__/AuthArtPanel.test.tsx`, 129)

A decorative panel on the left of the auth split (right, as a top banner, on
tablet; absent on mobile). Structure:

- **`.authart`** — `background-color: var(--color-base)` + an off‑centre radial
  accent wash (`background-image`).
- **`.authart__decor`** (`aria-hidden`): `.authart__grid` (masked 44px line grid);
  `.authart__rings` (2 static concentric `<circle>`s, `non-scaling-stroke`);
  **3× `.authart__plane--{1,2,3}`** — `<motion.svg>` polygons, gradient‑filled,
  **each on its own Framer drift track** (`x`/`y`/`scale` keyframes,
  `repeatType:'mirror'`, `easeInOut`; front plane travels furthest →
  parallax); `.authart__grain` (SVG `feTurbulence` fractal noise, desaturated via
  `feColorMatrix`); `.authart::after` vignette settling edges into `bg-base`.
- **`.authart__content`** (real text, **outside** `aria-hidden`): `<Wordmark/>`
  top‑left + uppercase wide‑tracked eyebrow `<p>` + oversized headline `<p>`
  (props `eyebrow`, `headline`; defaults are the Login copy; `RegisterPage`
  overrides `panelHeadline`) + a short accent rule `<div aria-hidden>`.
- **Per‑theme tuning:** ~18 `--authart-*` custom properties, **defined locally in
  the component's `<style>`** (dark defaults on `.authart`, light overrides under
  `[data-theme='light'] .authart`) — deliberately *not* in `theme.css` because
  they are opacity/blur/blend values local to this one decorative component, not
  shared vocabulary. Several auto‑adapt (they reference `--color-accent-*` which
  flips at `:root`); the hardcoded‑opacity ones are re‑tuned in the light block.
- **Motion:** `useMediaQuery('(prefers-reduced-motion: reduce)')` → planes get
  `animate={undefined}` / `transition={undefined}` — **fully disabled, not
  slowed**. `data-motion="full"|"reduced"` on the root.
- A dedicated `@media (min-width:768px) and (max-width:1279.98px)` block
  re‑proportions the planes/rings and shrinks the headline for the tablet banner.

### 18.2 Documented rejection history (the reason UI‑03 must render, not just brief)

Traced to `docs/`:

1. **Rejected (pre‑C3b):** an abstract mascot, and isometric "tenant‑cell" cubes —
   "too small/cute".
2. **Rejected (C3b addendum 1 context):** a scrolling stack of stat cards
   ("Total Sales $527.8K", a testimonial with a photo) — rejected *in full*
   because the mechanism is "structurally built around fabricated metrics";
   removing the fake numbers "would leave empty rectangles endlessly cycling,
   which reads as broken". → replaced with abstract non‑numeric drifting shapes.
3. **C3b addendum 1:** "ghost UI" panels — abstract translucent rounded‑rect
   silhouettes ("the ghost of a UI element", not "a UI element with the content
   removed"), Framer drift, token‑only.
4. **C3b addendum 2:** filled the ghost panels with `Skeleton`‑style bars + a
   line‑and‑node "network" motif. **Rejected:** a literal binary‑digit texture
   ("a recognizable cliché that undercuts the premium goal").
5. **`authpanel-redesign-spec.md` (the current version):** removed the ghost
   panels **and** the network motif entirely; **typography‑driven** — oversized
   headline + eyebrow, layered translucent angular planes ("depth via layering
   and light, not literal 3D"), concentric rings, kept grid + grain. "Confirmed
   against a static mockup the user approved."
6. **Headline line‑break fix (`4c38e59`) — made then REVERTED (`595ef5d`) same
   day.** First attempt forced the headline into three explicit `\n`/`<br/>`
   lines to match `docs/login_desktop_redesign_concept.html`; the user clarified
   the wrapping was never the problem — only that the headline read *smaller*
   than the reference. Reverted; `--authart-headline-size` clamp was bumped
   (`44px` → `56px` cap) instead. **Lesson recorded in this project's memory:**
   when a visual complaint cites a mockup, don't assume which attribute (wrap
   vs. size vs. weight) is the gap; try the smallest change first.

### 18.3 What this means for the redesign

- **`AuthArtPanel` content is fully B** — everything visible is decorative +
  marketing copy, all token/prop driven. **The only A carve‑out** is the
  `aria-hidden` boundary (decor hidden, eyebrow/headline in the a11y tree) and
  the reduced‑motion disable.
- UI‑01 §7.3 named this "the strongest single opportunity in the corpus" and
  proposed replacing the abstract geometry with a *redacted real Tenora surface*.
  This audit confirms the panel is unencumbered by coupling — the redesign is
  free here — but the **rejection history is long and specific**, which is
  exactly why the redesign master spec §8 makes UI‑03 a *rendered* hard gate.
- `AuthLayout` breakpoints (`xl` split / `md` `h-[36vh]` banner / `< md` hidden)
  and "exactly one wordmark per breakpoint" are **A‑adjacent** — a structural
  contract the redesign can change but must do deliberately (a past bug: a 2‑row
  grid left `<main>` un‑stretched on mobile once the `display:none` panel dropped
  out of grid flow).

---

## 19. A/B/C/D master matrix (consolidated)

### 19.1 D — do not touch (strong coupling / security / fragile mechanism)

| Item | Specific risk |
|---|---|
| `lib/api-client.ts` | 401 refresh+retry loop; `X-Tenant-ID`/`Authorization` decision; `assertNoTenantInBody`; single point of failure for every request. |
| `lib/global-paths.ts` | Exact‑match mirror of a backend security control; drift → silent tenant‑header leak or missing header. |
| `lib/config.ts` | Every request URL + the global/no‑auth decision derive from `apiBasePath()`. |
| `lib/auth/token-store.ts` | Access‑token‑in‑memory / refresh‑in‑`sessionStorage` is a deliberate security tradeoff. |
| `lib/auth/refresh.ts` | `refreshOnce` coalescing prevents rotation from blacklisting the token under a burst of 401s. |
| `lib/auth/session.ts` | The non‑React → React "session over" seam; idempotency. |
| `lib/auth/logout.ts` | Raw fetch, `keepalive`, synchronous token read before `endSession`, fire‑and‑forget ordering. |
| `lib/auth/AuthProvider.tsx` | StrictMode‑hardened bootstrap (reset‑ref‑in‑cleanup); `clearIdentityState` on login + session‑end. |
| `lib/auth/auth-context.ts` | The `useAuth` contract; the `userEmail` "display convenience, never identity for a decision" rule. |
| `lib/tenant/current-tenant.ts` | Non‑React holder read by the api‑client on every tenant‑scoped call; "not authorization". |
| `lib/tenant/TenantProvider.tsx` | **Render‑time** `setCurrentTenantId` write; stale‑stored‑id‑is‑ignored resolution. |
| `lib/tenant/tenant-context.ts` | The `useTenant` contract. |
| `lib/query-keys.ts` | Structural tenant isolation — a bare key reintroduces leakage. |
| `routes/useRazorpayCheckout.ts` | External SDK; `window.Razorpay`; provider boundary (redesign master spec §25); once‑only settle guard. |
| `GoogleSignInButton.tsx` (integration only) | GIS CDN script; `window.google`; `initialize()`‑once; credential→token callback. |
| `lib/theme/*` (mechanism) | pre‑paint `index.html` script ↔ `theme-store` ↔ `<html data-theme>` ↔ `theme.css` selectors — a coordinated cross‑file system. Token *values* are B (§17); the plumbing is D. |
| `index.html` (both CDN `<script>`s + inline theme script) | GIS + Razorpay Checkout cannot be self‑hosted; the theme script must run before first paint. |

### 19.2 A — must remain functionally unchanged (behaviour frozen; presentation is B)

| Item | Frozen behaviour |
|---|---|
| `routes/ProtectedRoute.tsx` | loading‑gate‑**before**‑redirect ordering. |
| `lib/query-client.ts` | `retry: false` (api‑client depends on it); `staleTime: 30_000`; `.clear()` semantics. |
| `lib/api-error.ts` | the `ApiError` field contract every `catch` destructures. |
| `lib/format.ts` (money) | integer cents; `Intl`‑derived exponent; no hardcoded `$`. |
| `lib/tenant/types.ts` | `TenantMembership` shape mirrors the backend serializer. |
| `components/layout/use-current-user.ts` | `isStaff` default `false`; `isStaffResolving` ≠ `resolving`; unconditional `/users/me/`. |
| `components/layout/nav-items.tsx` | route `to` values; staff item separated from `NAV_ITEMS`. |
| `components/layout/use-disclosure.ts` / `use-focus-trap.ts` | Escape/outside‑close, focus trap + restore, opt‑in scroll‑lock; the deliberate copy‑not‑share from `Modal`. |
| `Badge` (the throw) | throws without a visible label — status never colour‑alone. |
| **Status → Badge variant map** (3 copies: `SubscriptionPage`, `OverviewPage`, `PlatformAdminPage`) | `ACTIVE→success, TRIALING→warning, PAST_DUE→danger, CANCELED→neutral` (+ `NONE→neutral` in Platform Admin). Redesign master spec §7 — restyle `Badge`, never remap; keep the copies in sync. |
| `LoginPage` credentials error | one generic message for `401`; never distinguish unknown‑email vs wrong‑password. |
| `RegisterPage` flow | no auto‑login after register; "email already registered" **is** disclosed (unlike Login). |
| `VerifyEmailPage` | single‑fire (`firedRef` + `mountedRef`); missing token → no request. |
| `SubscriptionPage` | global+tenant query mix (plans not refetched on switch); `404`→empty; `CANCELED` terminal (no reactivate control at all); `plan_id` vs `status` PATCH bodies. |
| `SubscriptionPage` checkout | ephemeral "processing" (never "active"); webhook is authoritative; honest "couldn't verify" copy. |
| `PlanGrid` | roving tabindex; arrow moves focus but does **not** select; read‑only `<ul>` vs radiogroup by `onSelect` presence. |
| `CancelSubscriptionModal` | type‑to‑confirm gate (trim‑both, else exact); `hasUnsavedChanges` backdrop guard; copy claims no refund/no access‑gating/no restart. |
| `MembersPage` | tenant‑scoped members key; empty‑list = error; OWNER‑gate is UX; no optimistic insert. |
| `AddMemberModal` | no role field; `404`→field error; `403`→form Alert. |
| `OverviewPage` | **no** combined pending/error boolean — per‑tile isolation is the contract; two tenant‑scoped queries refetch together; "Member since" ≠ "Workspace created". |
| `WorkspacePage` | reads `useTenant()` (no re‑fetch); `switchTenant` is the only active‑tenant setter; `pendingId` race handling; no single‑workspace auto‑select. |
| `CreateWorkspaceModal` | `POST /tenants/` (global, no tenant header); slug dup → inline field error, not a toast. |
| `PlatformAdminPage` | `isStaffResolving`‑gated redirect (not `resolving`); `enabled: isStaff`; global keys; per‑query isolation. |
| `TopNavbar` | RBAC nav append; multi‑signal active state; conditional render (not CSS‑hide) of nav vs mobile panel; < 1024px collapse. |
| `TenantSwitcher` | `switchTenant` + close + focus return; **blocking** error retry; skeleton/empty/ready states. |
| `AccountMenu` | genuine‑switch‑only menu close (`prevTenantId` guard). |
| `index.html` inline theme script | sets `data-theme` before first paint (no FOUC). |
| `index.html` CDN scripts | Google GIS + Razorpay Checkout — documented, cannot be self‑hosted. |
| `Alert` (`role` choice) | `assertive ?? variant === 'danger'` → `role="alert"` vs `"status"` — form errors must announce. |
| `Input` (ARIA wiring) | `aria-invalid`, `aria-describedby` → helper id, `<label htmlFor>` + `useId`. |
| `Skeleton` (`role="status"` + sr‑only label) | announces "Loading". |
| `Table` (mobile transform + `<caption class="sr-only">`) | < 768px stacked cards, never horizontal scroll. |
| `use-media-query` (`true` default) | decides SSR / old‑jsdom / no‑`matchMedia` layout. |
| `AuthArtPanel` (`aria-hidden` boundary + reduced‑motion disable) | decor hidden, eyebrow/headline in the a11y tree; motion fully off (not slowed) on `prefers-reduced-motion`. |
| `AuthLayout` (breakpoint structure + one‑wordmark‑per‑breakpoint) | changeable but deliberately (a past mobile‑stretch bug). |

### 19.3 B — visual implementation replaceable (functional contract unchanged)

Everything not in 19.1 / 19.2, specifically:

- **Every route page component** as a whole (`LoginPage`, `RegisterPage`,
  `VerifyEmailPage`, `WorkspacePage`, `MembersPage`, `SubscriptionPage`,
  `OverviewPage`, `PlatformAdminPage`) — the JSX composition, layout, spacing,
  typography, copy tone. The A behaviours listed in 19.2 sit underneath.
- **Every `components/index.ts` primitive** (`Alert`, `Badge`, `Button`, `Card`,
  `EmptyState`, `Input`, `Modal` shell, `Skeleton`, `Table`) — with the specific
  A carve‑outs in 19.2.
- **Layout chrome:** `AppShell` (the `max-w-[1400px] p-6` frame), `Wordmark` (the
  "B" glyph + "Billing Engine" text — current identity), `UserMenu`,
  `ThemeToggle`, `TopNavbar` chrome, `TenantSwitcher` overlay visuals,
  `AccountMenu` overlay visuals, `PlanGrid` card visuals, `PlatformBarChart` bar
  geometry/colour, `ChangePlanConfirmModal` / `CancelSubscriptionModal` /
  `AddMemberModal` / `CreateWorkspaceModal` body layout, `AuthArtPanel` content
  and `AuthLayout` composition.
- **All of `theme.css`'s token values** (§17.5).

### 19.4 C — safe to generalize / refactor (why safe; no new dependency)

| Item | Refactor | Why safe | New dependency? |
|---|---|---|---|
| `MembersPage.formatJoined` (D‑0.10) | delete it, use `format.formatDate` | byte‑equivalent behaviour; `format.ts`'s own header says it was *lifted from* this helper and the local copy should have gone. `MembersPage.test.tsx` asserts the rendered string, which is unchanged. | **No** — removes code. |
| Empty‑state rendering (D‑0.9) | route `OverviewPage`'s "No active subscription" and `PlatformAdminPage`'s "No tenants" through the existing `EmptyState` primitive | `EmptyState` already exists and is used by 2 pages; both hand‑rolled cases are a headline + description (± action) — the exact `EmptyState` shape. Tests assert on the text, which survives. **Caveat:** `MembersPage`'s empty case is deliberately an *error* `Alert`, not an empty state — leave it. | **No** — uses an existing primitive. |
| `use-disclosure` (`use-disclosure.ts`) | none needed — already a clean shared hook | it is already generalized (3 consumers). Listed only to record that it is *not* a refactor target. | n/a |
| `Table` dead code (D‑0.8) | **do not remove in this phase** | `sortable`/`onRowClick`/`selectedRowKey` are unused by pages **but `Table.test.tsx` exercises them** — removing the API means weakening a test, forbidden by audit spec §6 and the project's CLAUDE.md. A future stage that also owns the test file could prune it. | n/a |
| `format.ts` location | none — leave as `lib/format.ts` | it is already shared correctly; the only issue is the un‑deleted `MembersPage` copy (row 1). | n/a |

**No C classification here proposes a new library, a new framework, or a
composition pattern the codebase doesn't already use.** (Redesign master spec
§19; audit spec §4.1.)

### 19.5 Internal‑consistency cross‑check (§4 ↔ §12 ↔ §19)

- **§4 route table** classes: every page = **B + enumerated A carve‑outs**;
  `ProtectedRoute` = **A**. → Consistent with §19.2 (each page's A behaviours are
  listed) and §19.3 (each page appears as B). ✔
- **§12.A** components are all **D** or **A** → all appear in §19.1 or §19.2. ✔
  (`api-client`, `global-paths`, `config`, `auth/*`, `tenant/*`, `query-keys`,
  `useRazorpayCheckout`, `GoogleSignInButton` integration = D; `api-error`,
  `query-client`, `ProtectedRoute`, `use-current-user`, `nav-items`,
  `use-disclosure`, `use-focus-trap`, `format` money, `tenant/types` = A.)
- **§12.B** components are all **B** with named A carve‑outs → each B component is
  in §19.3, each carve‑out in §19.2. ✔
- **§12.C** (`use-disclosure` C‑note, `use-focus-trap` not‑C) → matches §19.4. ✔
- **The status→Badge map** appears as an **A** row in §19.2 and is referenced in
  §4 (`SubscriptionPage`/`OverviewPage`/`PlatformAdminPage` rows), §7.2, §9.1,
  §11.3, §21 — all say the same thing (3 copies, restyle not remap, keep in
  sync). ✔
- **No item is classified two ways.** `Modal` is "B shell + A mechanics" — a
  single item with an explicit split, listed once in §12.B and its mechanics once
  in §19.2. `TopNavbar`/`TenantSwitcher`/`AccountMenu` similarly. ✔
- **D‑0.1…D‑0.11** are referenced from every section they bear on; none is
  silently dropped. ✔

---

## 20. Safe refactoring opportunities

**All are optional, none is required for the redesign, and none introduces a
dependency.** They are separated here from the protected areas (§21) precisely so
a later stage can pick them up deliberately or skip them.

1. **Delete `MembersPage.formatJoined`; use `format.formatDate`** (D‑0.10).
   Zero behaviour change; `format.ts` was *created* to hold this. ~10 lines
   removed. Safe: `MembersPage.test.tsx` asserts the rendered date string, which
   is identical.
2. **Consolidate hand‑rolled empty states onto `EmptyState`** (D‑0.9) — for
   `OverviewPage` "No active subscription" and `PlatformAdminPage` "No tenants
   yet". Leave `MembersPage`'s (deliberately an error). Uses an existing
   primitive; tests assert on text. This is also a *redesign* opportunity (one
   consistent empty‑state treatment) — likely best folded into UI‑07/UI‑08 rather
   than done standalone.
3. **A shared `PageHeader` component** does **not** exist today — every page
   hand‑rolls `<h1 className="text-display"> + <p className="text-secondary">`.
   UI‑01 §6.3 proposes exactly this (the "editorial page‑header pattern"). Noted
   as the natural home for that work in UI‑05/UI‑07; not a pre‑req refactor.
4. **`use-focus-trap` ↔ `Modal` trap** — a future shared extraction is *possible*
   (they are near‑identical) but **explicitly out of scope for a re‑skin**:
   `navbar-redesign §4.2` chose the copy deliberately, `Modal` is a shipped
   tested primitive, and merging them risks a regression in dialog focus
   management for zero user‑visible benefit. Only revisit if a stage genuinely
   rebuilds both.
5. **The status→Badge map (×3)** — could become one shared `export`. **This is a
   decision for the redesign owner, not a safe unilateral refactor**: the three
   host files were frozen by their stages, and §7 requires the *values* preserved.
   If the freeze is lifted, a single `statusBadge.ts` in `lib/` (no dependency,
   matches the existing `format.ts` pattern) is the clean shape. Logged in §23.

---

## 21. Protected / high‑risk areas

Ranked. Every UI‑0x stage that touches these must trace the chain first.

1. **`lib/api-client.ts`** — small, maximally load‑bearing. The 401 loop, the
   header decisions, `assertNoTenantInBody`. **Do not touch** beyond nothing.
2. **The auth chain** (`token-store` / `refresh` / `session` / `logout` /
   `AuthProvider`) — token lifetime, rotation‑safe coalescing, the non‑React↔React
   seam, StrictMode bootstrap hardening, identity reset. Multiple documented
   past bugs.
3. **`lib/tenant/TenantProvider.tsx` render‑time header write** — the one place a
   "clean up this component" instinct would reintroduce the C4 "no `X-Tenant-ID`
   on first fetch" bug.
4. **`lib/query-keys.ts`** — a bare (non‑`tenantId`) key silently reintroduces
   cross‑tenant cache leakage. The isolation guarantee is *structural*, not
   enforced by any runtime check.
5. **`routes/useRazorpayCheckout.ts` + the checkout flow in `SubscriptionPage`** —
   external SDK, `window.Razorpay`, the provider boundary (redesign master
   spec §25). Any change to what the checkout UI reveals about the adapter needs
   sign‑off. `SubscriptionPage.test.tsx` (870 lines) is the contract.
6. **`components/layout/use-current-user.ts` `isStaffResolving` vs `resolving`** —
   collapsing them flashes a false "access denied" for a just‑logged‑in staff
   member. `/users/me/` fires unconditionally on shell mount.
7. **The status→Badge map, ×3 copies** — a restyle that "helpfully" imports one
   into the others would touch a frozen file; a restyle that remaps a status
   violates redesign master spec §7.
8. **`GoogleSignInButton`** — GIS renders static markup (no live theme swap), so
   it is re‑rendered on theme flip; `initialize()` must stay once‑only; the
   credential→token callback path is auth‑critical.
9. **`components/Modal.tsx` + `use-focus-trap.ts`** — a shipped, tested primitive
   and its deliberate copy. `navbar-redesign §4.2` explicitly forbids refactoring
   `Modal` to fit the anchored menus.
10. **`AppRoutes.tsx` catch‑all + `ProtectedRoute` nesting** — the `*` → `/` →
    `/overview` chain and the `Auth → Tenant → Shell` order; `/verify-email` is
    deliberately **outside** `ProtectedRoute`.
11. **`theme.css` token *names* ↔ Tailwind‑v4 utilities** — renaming a token
    (`--color-primary` → anything) renames its generated utility (`text-primary`)
    across ~69 files. The redesign will change token *values* freely; it must not
    rename them casually. The `--color-base` / `text-base` shadowing is a
    documented quirk to keep in mind.
12. **The `index.html` pre‑paint theme script** — deleting or breaking it
    reintroduces a flash‑of‑wrong‑theme on every load. It must stay in sync with
    `theme-store`'s resolution order (stored → OS → dark).
13. **`AuthLayout` breakpoint structure** — a past bug: a 2‑row grid left `<main>`
    un‑stretched on mobile once the `display:none` art panel dropped out of grid
    flow. The current `flex-col xl:grid` + `flex-1 <main>` is the fix; a redesign
    that rebuilds this layout must not regress it.
14. **`GoogleSignInButton` / `useRazorpayCheckout` unbounded 100ms polls**
    (D‑0.11) — low severity, but a stage touching either should consider adding a
    ceiling.

---

## 22. UI redesign sequencing implications

Maps each audited area to a stage. **Does not implement anything.** The A/D
constraint each stage inherits is stated so the stage's own "must not do" list
can be derived from this audit.

| Stage | Owns (from this audit) | Inherits (must not break) |
|---|---|---|
| **UI‑03** (prototype, hard gate) | Renders: `AppShell` + `TopNavbar`; one authenticated product page (Overview or Subscription — Subscription exercises the most state); one auth screen (`Login` + `AuthArtPanel` + `AuthLayout`); desktop + mobile; dark + light. The **redacted‑real‑surface** `AuthArtPanel` idea (UI‑01 §6.1) — using a *shipped* surface (subscription card / plan grid / members list / lifecycle), **not** reconciliation/webhooks/usage/proration (D‑0.2, §4.2). | All of §19.1 (D) untouched — a prototype is visual only. The status→Badge map values (§7). No new colour/font/dependency. No motion beyond the permitted feedback set. |
| **UI‑04** (design system, post‑UI‑03) | Formal token spec — replaces §17's values. Decides: the larger "edge" display step (UI‑01 §10 Q3); whether the top bar moves `bg-raised → bg-base` (Q2); the overline element; whether a 4th surface token is warranted (Q4). Documents the Tailwind‑v4 utility‑name coupling as a constraint. | The dark‑default + light‑override mechanism; rem‑based spacing (a11y); every measured contrast pair must be re‑measured, not assumed; `num` utility. |
| **UI‑05** (shell) | `AppShell` frame (`max-w-[1400px] p-6`), `TopNavbar` chrome, `Wordmark`, `TenantSwitcher` + `AccountMenu` **overlay visuals**, `UserMenu`, `ThemeToggle`. Natural home for a shared `PageHeader` (§20.3, UI‑01 §6.3). | §19.2: RBAC nav append; multi‑signal active state; **conditional render** (not CSS‑hide) of nav vs mobile panel; the `< 1024px` collapse; `TenantSwitcher` **blocking** error state; `AccountMenu` genuine‑switch‑close guard; `use-disclosure`/`use-focus-trap` behaviour; the always‑visible switcher + avatar. **Do not touch** `use-current-user` logic, `nav-items` `to` values, or anything in `lib/tenant/*`. |
| **UI‑06** (auth) | `LoginPage`, `RegisterPage`, `VerifyEmailPage` composition; `AuthLayout` structure; `AuthArtPanel` (fully B — §18.3); the divider/spacing around `GoogleSignInButton`. | §19.2: generic‑401 non‑disclosure; no auto‑login after register; "email already registered" disclosed; verify single‑fire; the `aria-hidden` decor boundary + reduced‑motion disable; `AuthLayout` one‑wordmark‑per‑breakpoint + the mobile‑stretch fix. **Do not touch** `AuthProvider`, `token-store`, `refresh`, `session`, `logout`, the `GoogleSignInButton` GIS integration (only its wrapper styling). |
| **UI‑07** (core) | `Overview`, `Subscription/PlanGrid`, `Members`, checkout‑related UI, cancellation UI, the 4 modals' body layout. Empty‑state consolidation (§20.2). Editorial copy tone (UI‑01 §4.5) on `STATUS_EXPLANATION`‑style strings. | §19.2: per‑tile isolation (Overview) — **no shared loading/error boolean**; global+tenant query mix (`plans` not refetched on switch); `404`→empty; `CANCELED` terminal — **no reactivate control**; `plan_id` vs `status` PATCH; ephemeral "processing"; `PlanGrid` roving‑tabindex + browse‑≠‑select; `CancelSubscriptionModal` type‑to‑confirm + backdrop guard; empty‑as‑error on Members; `AddMemberModal` no role field. **Do not touch** `useRazorpayCheckout` or what the checkout UI reveals about the provider (D‑0.6, §25 sign‑off); the status→Badge map values. |
| **UI‑08** (admin/settings) | `PlatformAdminPage` composition; `PlatformBarChart` bar visuals. **Settings/Profile/Tenant Settings: if the redesign owner decides to build these, that is new‑feature work with its own spec + backend endpoints (§10, §23 Q1) — not part of a re‑skin.** | §19.2: `isStaffResolving`‑gated redirect (not `resolving`); `enabled: isStaff`; global keys; per‑query isolation; `PlatformBarChart` label+value never colour‑only + `role="img"`. **Do not touch** `use-current-user`, the `IsPlatformStaff` boundary reality. |
| **UI‑09** (polish) | Motion (within the permitted feedback set — UI‑01 §8.11), responsive gap tuning (the `AppShell` 24px gutter, the missing `< 400px` handling — §15), loader‑idiom consolidation (§14 gap), `title=`/skip‑link a11y gaps (§16.2). | Every A behaviour above; `prefers-reduced-motion` honoured globally + the three components' full disable. |
| **UI‑10** (QA) | The full evidence set — see §24. | — |

**D5/D6/D8 frontend surfaces are in no stage** (§4.2, D‑0.2, redesign master
spec §12/§22). They remain absent.

## 23. Open questions / decisions (genuine only — none manufactured)

1. **Settings / Profile / Tenant Settings (D‑0.2).** The redesign master spec §11
   lists these as UI‑08 pages; **none exists and most have no backend endpoint.**
   *Question for the redesign owner:* is UI‑08 a re‑skin of Platform Admin only,
   or does it also scope *new* settings pages? If the latter, that needs its own
   spec (and backend work) and is not part of this redesign per §12/§22. This
   audit assumes the former and documents the void.
2. **The status→Badge map, ×3 copies.** Leave the freeze (three copies stay in
   sync by discipline) or lift it for one shared `lib/statusBadge.ts`? §7 requires
   the *values* preserved either way. A decision for the redesign owner — §20.5
   has the clean shape if the freeze is lifted.
3. **Empty‑state treatment.** `EmptyState` primitive (2 pages) vs hand‑rolled
   `Card` (2 pages) vs error‑`Alert` (Members, deliberately). The redesign will
   need one coherent story — but note Members' "empty = error" is a real
   business rule, not laziness, so "always use `EmptyState`" is wrong.
4. **Top‑bar background** (UI‑01 §10 Q2) — the audit confirms it is `bg-raised`
   today with only a hairline `border-b`. Moving it to `bg-base` is a pure token
   swap with no coupling; the open question (does the reduced separation hurt
   scroll orientation over a dense table) is a UI‑03 render call.
5. **The `AppShell` content frame** (`max-w-[1400px] p-6`). Every page *also*
   sets its own `max-w-*` (`3xl`/`5xl`/`560px`), so the 1400px is rarely the
   binding constraint. Is the double‑constraint intentional, or should the shell
   frame be the single source? A redesign‑time simplification, not a bug.
6. **`ChangePlanConfirmModal` friction.** A billing‑affecting change behind a
   plain confirm while cancel has type‑to‑confirm. Is that gradient right? (The
   rationale — reversible vs irreversible — is sound; flagging for a conscious
   redesign decision.)
7. **Two CDN scripts always load** (GIS + Razorpay) on **every** page including
   the auth pages and Overview, regardless of whether checkout or Google sign‑in
   is reachable there. Not a redesign concern per se, but a UI‑09 performance‑pass
   candidate (conditional injection) — noted, out of scope for the re‑skin.

## 24. UI‑02 acceptance evidence

Checked against `docs/ui-02-audit-spec.md` §7 (acceptance criteria):

| # | Criterion | Status |
|---|---|---|
| 1 | Every actual frontend route accounted for | ✔ §4 — 7 routes + 2 redirects, all traced to `AppRoutes.tsx`. |
| 2 | Major shared components inventoried, each with a traced coupling chain where relevant | ✔ §12.A/B/C — every consumer list grep‑verified, every D/A carve‑out traced to a file:line. |
| 3 | Every significant area carries an A/B/C/D classification with reasoning (C: why safe; D: what risk) | ✔ §19; C reasons + "no new dependency" in §19.4; D risks in §19.1 + §21. |
| 4 | Auth + tenant coupling documented, traced to code | ✔ §5, §6 (+ `tenant-isolation.test.tsx` read in full). |
| 5 | Subscription/billing coupling documented, traced to code | ✔ §7, §13. |
| 6 | API/data dependencies mapped | ✔ §13 — 20 endpoints + 2 external, with method / caller / key / header / gate. |
| 7 | Responsive behavior documented as it actually exists | ✔ §15. |
| 8 | Accessibility behavior documented as it actually exists | ✔ §16 (strengths + 7 gaps, none fixed). |
| 9 | Existing visual‑system mechanisms documented (not redesigned) | ✔ §17 — token families, mechanism, utilities, what the redesign owns vs must not break. |
| 10 | AuthArtPanel/existing identity documented factually | ✔ §18 — current impl + 6‑step rejection history. |
| 11 | New backend‑only frontend features explicitly confirmed excluded | ✔ §4.2 — usage/proration/reconciliation/webhook = none, none proposed. |
| 12 | Safe refactors separated from protected/high‑risk areas | ✔ §20 vs §21. |
| 13 | No source code modified — git status proves it | ✔ see "Pass 2 verification". |
| 14 | No API contract changed | ✔ read‑only. |
| 15 | No dependency added | ✔ read‑only; no C classification proposes one (§19.4). |
| 16 | No UI implementation performed | ✔. |
| 17 | Document internally consistent (§4 ↔ §12 ↔ §19) | ✔ explicit cross‑check in §19.5. |
| 18 | git status reported in full | ✔ "Pass 2 verification". |
| 19 | UI‑01 checkpoint commit `3807b0a` untouched | ✔ verified. |
| 20 | A reliable factual foundation for UI‑03, not aspirational | ✔ — every claim is file:line‑traced; the one unverifiable dependency (D‑0.1) is flagged. |
| 21 | Any inaccurate UI‑01 claim about the existing frontend flagged, not silently corrected | ✔ — D‑0.4 (motion), D‑0.7 (shadows). Both confirmed **incompleteness in a self‑declared "light read"**, not a substantive error; UI‑01's design *direction* is not re‑litigated. |
| 22 | `docs/frontend-audit.md` committed as its own checkpoint once approved | **pending** — this delivery stops before the commit, per the session directive. |

### UI‑01 claims independently verified as ACCURATE (audit spec §1 — "where this
audit confirms a UI‑01 claim, say so")

- §7.1 dark‑first cool near‑black, 3 surface planes + 2 border weights — ✔ (`theme.css`).
- Single purple accent + strict 4‑colour semantic set, always label‑paired — ✔
  (`theme.css` + `Badge` throw + 3 status maps).
- Geist Sans + Geist Mono, **bundled** (no font CDN) — ✔ (`main.tsx` `@fontsource`).
- Compact type scale display 32 / h1 24 / h2 18 / body 14 / label 13 / caption 12
  / mono 13, weight range 400–600 — ✔ exact (`theme.css`).
- 4px spacing base; radius 6/10/16 — ✔ exact.
- `prefers-reduced-motion` honoured globally — ✔ (`theme.css` `@media` block).
- Sticky hairline‑bordered chrome‑minimal top bar; wordmark → nav → **always‑visible**
  switcher → account; nav collapses to a panel below 1024px, switcher/account stay
  put — ✔ exact (`TopNavbar.tsx`).
- Tables → stacked cards on mobile (never horizontal scroll) — ✔ (`Table.tsx`,
  both consumers pass `renderMobileCard`).
- `text-muted` barred from content a user must read — ✔ (documented rule +
  `Input` uses `text-secondary`).
- Per‑tile query‑failure isolation on Overview — ✔ (no shared boolean).
- `404`‑as‑empty‑state on Subscription — ✔ (`ApiError.status === 404`).
- `PlanGrid` hand‑rolled ARIA‑radio with roving tabindex — ✔.
- `useRazorpayCheckout` / provider coupling exists — ✔ (D‑0.6 documents the full
  extent, which UI‑01 under‑stated but did not deny).

---

## Verification (Pass 1 + Pass 2)

### What was inspected

**Read in full (`frontend/src/`):** `App.tsx`, `main.tsx`, `index.html`,
`vite.config.ts`, `package.json` (deps).
`routes/`: `AppRoutes`, `ProtectedRoute`, `AuthLayout`, `LoginPage`,
`RegisterPage`, `VerifyEmailPage`, `GoogleSignInButton`, `SubscriptionPage`,
`PlanGrid`, `ChangePlanConfirmModal`, `CancelSubscriptionModal`,
`useRazorpayCheckout`, `MembersPage`, `AddMemberModal`, `WorkspacePage`,
`CreateWorkspaceModal`, `OverviewPage`, `PlatformAdminPage`, `PlatformBarChart`,
`AuthArtPanel`.
`lib/`: `config`, `api-client`, `api-error`, `global-paths`, `query-client`,
`query-keys`, `cn`, `format`, `auth/*` (all 7), `tenant/*` (all 5), `theme/*`
(all 4).
`components/`: `Alert`, `Badge`, `Button`, `Card`, `EmptyState`, `Input`, `Modal`,
`Skeleton`, `Table`, `use-media-query`, `index.ts`.
`components/layout/`: `AppShell`, `TopNavbar`, `TenantSwitcher`, `AccountMenu`,
`UserMenu`, `ThemeToggle`, `Wordmark`, `nav-items`, `use-current-user`,
`use-disclosure`, `use-focus-trap`, `index.ts`.
`styles/theme.css` (in full).

**Tests read as contract evidence:** `tenant-isolation.test.tsx` (in full);
targeted greps across `api-client.test.ts`, `global-paths.test.ts`,
`TopNavbar.test.tsx`.

**Grep sweeps (read‑only):** endpoint calls; `useMutation` (none); component
consumer maps (per primitive); `aria-*` / `role=` / `focus-visible` inventory;
breakpoint‑prefix counts; `useMediaQuery` call sites; `title=` usage; `featured`
usage; `Table` prop usage; `sortable`/`onRowClick` usage; `aria-current` source;
`NavLink` usage; settings/profile route search; `plans/archived` usage.

**Backend cross‑checks (read‑only, contract verification only):** `config/urls.py`;
`apps/users/{models,serializers,views}.py`; `apps/platform/{views,permissions}.py`;
`apps/billing/views.py`; `apps/tenants/permissions.py` (all via grep, not
full‑file).

**Auth‑panel history docs read:** `authpanel-redesign-spec.md` (head),
`stage-c3b-authpanel-addendum.md` / `-addendum-2.md` (heads); rejection sequence
cross‑referenced with this project's memory (`4c38e59` revert).

### Audit limitations / unresolved traces (retained + updated)

1. **D‑0.1 — the redesign master spec is not in the repo.** The in‑conversation
   "Tenora UI/UX Redesign — Master Specification (Revised)" text was used as
   authoritative (per the session directive; the file was **not** added). No
   trace is *blocked*, but every "redesign master spec §N" citation (concentrated
   in §2, §22, §23) is **not re‑verifiable by a reader without the conversation**.
   This is the single standing limitation of the audit.
2. **Backend verification was grep‑level, not full‑file** — sufficient to confirm
   endpoint existence, permission classes, and response‑shape docstrings, which
   is all the A/D classifications rest on. A deeper backend read is out of UI‑02
   scope (audit spec §3, redesign master spec §2).
3. **`src/test/fixtures.ts` (291) and the large page test files**
   (`SubscriptionPage.test.tsx` 870, `OverviewPage.test.tsx` 464,
   `MembersPage.test.tsx` 331, `RegisterPage.test.tsx` 270) were **not read
   line‑by‑line.** Their contracts were inferred from component code + docstrings
   + targeted reads. **No A/B/C/D classification depends on an unread test.** If a
   later stage needs a specific assertion pinned (e.g. the exact
   checkout‑success payload asserted, or the exact isolation‑test wording for a
   query key it wants to change), that file should be read at that point.
4. **No behaviour was executed** — `npm test` / `npm run build` / `npm run lint`
   were **not** run (read‑only audit). A green run of all three is **UI‑10**
   acceptance evidence, not UI‑02's. This audit therefore asserts *what the code
   says*, not *that the suite currently passes* (the memory records frontend
   285/285 at the last frontend‑touching stage, but that is not re‑verified here).
5. **`use-focus-trap.ts` line reference "`Modal.tsx:45‑96`"** is quoted from the
   component's own docstring; `Modal.tsx` was read in full and the mechanism
   matches, but the exact line numbers in that docstring were not re‑counted.
6. **Dynamic runtime behaviour not observed:** the exact tab‑order shift when
   `CancelSubscriptionModal` enables its danger button (§16.2 item 1), and the
   precise focus target after `TenantSwitcher` closes on select, are reasoned
   from the code, not seen in a browser. Flagged for UI‑10's a11y re‑verification.

### Required read‑only git checks

```
$ git status --porcelain
?? docs/design-references/
?? docs/frontend-audit.md
?? docs/ui-02-audit-spec.md

$ git diff --stat HEAD        # tracked-file changes
(empty)

$ git log --oneline -1
3807b0a docs(ui): add design reference analysis
```

### Full git status

```
On branch master
Your branch is ahead of 'origin/master' by 18 commits.

Untracked files:
  docs/design-references/      ← user-supplied (UI-01 reference corpus)
  docs/frontend-audit.md       ← THIS deliverable (UI-02, Pass 1 + Pass 2, complete, uncommitted)
  docs/ui-02-audit-spec.md     ← user-supplied (the UI-02 spec); NOT created or modified by this audit

nothing added to commit but untracked files present
```

- **No tracked file modified** — `git diff HEAD --stat` is empty.
- **No source, test, config, dependency, route, API, or theme file changed** —
  the only file this audit created is `docs/frontend-audit.md`.
- **No helper script was committed** — all trace commands were ad‑hoc `grep` /
  `ls` / `wc` / `cat`, discarded.
- **UI‑01 checkpoint commit `3807b0a` is untouched** — it is still `HEAD`; not
  amended, not rebased.
- **No `npm` / build / test command was run.**

### Remaining uncertainty / incomplete trace

Beyond the six limitations above, the audit is complete: every route, every
shared component, every A/B/C/D classification, the auth/tenant/billing coupling
chains, the API map, responsive behaviour, accessibility behaviour, the visual
system, and the AuthArtPanel identity are traced to code. The §19.5
internal‑consistency check passed. Eleven discrepancies (D‑0.1…D‑0.11) are flagged
and none is silently resolved.

---

## Status: UI‑02 complete — awaiting review

The full `docs/frontend-audit.md` (24 sections + §0 discrepancies + verification)
is written. **Not committed** — per the session directive, this stops for review;
the file will be committed as the UI‑02 checkpoint (mirroring UI‑01's `3807b0a`)
only after approval. **UI‑03 is not started.**

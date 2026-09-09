# Frontend — Multi-Tenant SaaS Billing Engine

React + TypeScript + Vite, styled with Tailwind v4 (CSS-first `@theme`). Dark and
light themes (Stage C3b) — one token set per theme, switched by a `data-theme`
attribute with zero component changes. This directory is the frontend for the Django
billing engine at the repo root; the two test suites are separate (`npm test` here,
`python manage.py test` there).

> Running the whole stack (frontend + backend + Postgres) with one command via
> Docker? See the **Run with Docker** section in the [root README](../README.md).
> The commands below (`npm run dev`, etc.) are for the manual workflow.

## Platform Admin dashboard

`/platform-admin` (`src/routes/PlatformAdminPage.tsx`) — a read-only, cross-tenant
view for platform operators. Reachable only when `useCurrentUser().isStaff` is
true (from `is_staff` on `GET /api/users/me/`); a non-staff user who types the URL
is redirected to `/overview`. **This is UX only — the real boundary is
`IsPlatformStaff` on `/api/platform/*` server-side**, same discipline as every
other client-side permission check here.

- The nav gets one extra entry (`PLATFORM_ADMIN_NAV_ITEM`, appended in `TopNavbar`)
  for staff only.
- The gate waits on `isStaffResolving` (the raw `/users/me/` pending flag), **not**
  `resolving` — the latter has an `AuthProvider.userEmail` fast path and would let
  a just-logged-in staff member flash "access denied".
- Two independent queries (`queryKeys.platformTenants()` / `platformStats()`, both
  `['global', …]`), each with its own loading/error branch — no combined gate, and
  a tenant switch never drops them.
- Charts are hand-rolled SVG (`src/routes/PlatformBarChart.tsx`), reused three
  times — no charting-library dependency. Every bar renders its label and numeric
  value as text (never colour-only); an all-zero / empty set shows an explicit
  message.
- The tenant list reuses the `Table` primitive and its mobile stacked-card
  transform.

## Stage C3b scope

C3b adds a light theme alongside the dark one, before C4–C6 build three more pages.

- **`src/styles/theme.css`** — the dark `@theme` block is unchanged and is the
  `:root` default. A parallel `[data-theme='light']` block overrides the same
  `--color-*` / `--shadow-*` / gradient variables, so every existing token utility
  (`bg-base`, `text-primary`, …) resolves to the right value with **no component
  markup change**. Light values were measured against WCAG AA and adjusted from the
  first-draft candidates where they failed (recorded, with ratios, in
  `docs/ui-design-specification.md` §C.1). `text-muted` still fails AA in light,
  exactly as in dark — the decorative-only rule carries over unchanged.
- **`index.html`** — a tiny inline script sets `data-theme` before first paint
  (stored choice → OS preference → dark), so there's no flash.
- **`src/lib/theme/`** — `theme-store.ts` (framework-free: owns the `<html>`
  attribute + `localStorage['billing.theme']`, follows the OS setting only while no
  explicit choice is stored, and syncs across tabs via `storage` events) and a thin
  `ThemeProvider` + `useTheme` on top. `useTheme` also works with no provider (unit
  renders) by reading the store directly.
- **`src/components/layout/ThemeToggle.tsx`** — in the sidebar user area: a real
  toggle button, keyboard-reachable, `aria-pressed` reports whether dark mode is on.
- **New tokens.** `--color-on-accent` (label on an accent-600 fill — `text-primary`
  flips to near-black in light and fails on the purple; dark value is byte-identical
  to the old `text-primary`). `--color-scrim` (modal / drawer backdrop — replaced a
  hardcoded `bg-black/60`, the one raw-colour value the §4.3 scan turned up).
- **`src/routes/AuthArtPanel.tsx`** — **fully redesigned**
  (`docs/authpanel-redesign-spec.md`), typography-driven: a real, non-`aria-hidden`
  eyebrow + oversized headline (marketing copy, no numeric claims) and the wordmark
  sit over layered translucent angular planes (gradient-filled, each on its own
  **`framer-motion`** drift track — the front plane travels furthest, reading as
  parallax), 1-2 static concentric depth rings, and the retained edge-masked grid +
  grain base texture. Motion is fully disabled, not slowed, under
  `prefers-reduced-motion` (`use-media-query`, not Framer's cached
  `useReducedMotion`; `data-motion` reflects the path). **This supersedes the two
  prior addenda below in full** — the ghost-panel and network-motif elements they
  describe were removed, not layered under the new content; they're kept here only
  as a record of what shipped and was later replaced.
  - Light theme is a re-tune, not a recolour: wash/plane/ring opacities and mix
    percentages are pulled back (a purple fill loud enough to read as depth on
    near-black reads as a lavender flood at the same strength on white), grid
    colour switches from `--color-strong` (too visible a grey on white) to
    `--color-subtle`, and grain switches `overlay` → `soft-light` (`overlay`
    darkens against light backgrounds like dirt) at a higher opacity to still read
    as texture. `--authart-plane-fill-a/b`, `--authart-eyebrow-color` and
    `--authart-rule-color` need no override — they reference `--color-accent-*`
    directly, which already flips per theme at `:root`.
  - Tablet (768–1279, the short wide banner) reuses the desktop plane geometry
    rather than a redraw: each plane's box is enlarged past 100% height with a
    negative top offset, and `.authart`'s `overflow: hidden` clips the bleed — the
    visible slice reads as a proportioned facet instead of the squashed sliver a
    straight reuse of the tall-box percentages produced. This is the breakpoint the
    redesign was meant to fix ("sparse tablet"); confirmed resolved in the
    session-2 screenshot pass.
  - Headline/eyebrow contrast (measured against the panel's vignette-settled
    `bg-base`, where the copy sits): dark ~17.96:1 headline / ~5.90:1 eyebrow,
    light ~17.6:1 headline / ~6.46:1 eyebrow — all comfortably PASS AA (4.5:1).
  - _Superseded — addendum 1_ (kept for history only): two abstract "ghost UI"
    panels (translucent rounded rects, `bg-overlay/N` + `border-subtle` +
    `shadow-card`), independent drift, above the washes / below the vignette.
  - _Superseded — addendum 2_ (kept for history only): a third ghost panel
    (lower-right, three total, hard cap) with 2-3 skeleton bars in `Skeleton`'s
    visual language, plus a low-weight line-and-node network motif
    (`--authart-net-*` tuning vars) with one very slow ~40s group drift. No
    text/numbers/labels anywhere; explicitly no binary-digit texture.

## Stage C3 scope

C3 builds the first real pages and retires C2's scaffolding.

- `src/routes/LoginPage.tsx` + `AuthLayout` + `AuthArtPanel` — the real §C.4
  Page 1: split panel (visual + form, collapsing per §C.7), generic-401 message
  preserved from C2, "New here? Create account" link. The visual panel is
  original CSS + one inline SVG noise filter — no images, tokens only.
- `src/routes/RegisterPage.tsx` — a minimal `/register` flow (email / password /
  confirm). `POST /api/auth/register/` then auto-login → `/workspace`. Backend
  field errors render inline; a register-ok / login-failed combination is
  surfaced, never a stuck spinner.
- `src/routes/WorkspacePage.tsx` + `CreateWorkspaceModal` — §C.4 Page 2. Lists
  `TenantProvider`'s existing `/api/tenants/me/` data (no second fetch); empty
  state; create via `POST /api/tenants/` with an inline duplicate-slug error.
  Selection always through `TenantProvider.switchTenant`.
- `UserMenu` now fetches `GET /api/users/me/` (`['global','user','me']`) so the
  signed-in email survives a reload; a skeleton covers the gap, a neutral label
  is the failure fallback.
- `AuthProvider.logout()` fires a best-effort `POST /api/auth/logout/` (new
  `src/lib/auth/logout.ts`, raw fetch like `refresh.ts`) before clearing local
  state — which it does unconditionally.
- The C1 dev showcase (`src/dev/`, `/dev/showcase`) is **removed**.

## Stage C2 scope

C2 builds the cross-cutting infrastructure every future page plugs into,
across two sessions.

**Session 2 (done) — tenant context, routing, app shell, minimal login:**

- **Server state: TanStack Query v5.** Chosen because its query-key cache model
  is what makes the tenant-isolation guarantee _structural_ rather than a
  discipline (spec §4.3). `src/lib/query-keys.ts` is the one place keys are
  built:
  - Tenant-scoped keys carry the tenant id as an explicit segment —
    `['tenant', tenantId, 'members']`. Mirrors the backend's
    `TenantScopedManager.for_tenant(tenant)` taking `tenant` explicitly.
  - When the active tenant changes the key changes, so the previous tenant's
    data becomes a different, inactive cache entry — there is no code path by
    which it renders under the new tenant. Isolation is _not_ "clear the cache
    on switch" (fragile; easy to forget for a query added in C4/C5).
  - Global data (`/api/tenants/me/`, `/api/plans/`) is namespaced
    `['global', …]` and is never tenant-scoped or dropped on a switch.
  - Verified by `src/lib/tenant/__tests__/tenant-isolation.test.tsx` — the §4.3
    signature test, named so it's individually identifiable in the run.
- `src/lib/tenant/` — `TenantProvider` fetches `/api/tenants/me/`, resolves the
  active tenant (last-selected id from `localStorage` if still valid, else the
  first tenant), writes it to the header accessor, and exposes
  `switchTenant`. The `localStorage` value is a resume convenience, **never
  authorization** — documented at the write site.
- `src/routes/` — `react-router-dom` v7. `ProtectedRoute` waits for the
  silent-refresh-on-load to resolve before redirecting, so a valid reload never
  flashes the login page. Route stubs for Overview/Members/Subscription name the
  stage that replaces them.
- `src/components/layout/` — `AppShell` composes the C1 primitives: `Sidebar`
  with the `TenantSwitcher` pinned top, nav in the middle, `UserMenu` (email +
  logout) pinned bottom. Desktop ≥768px shows the sidebar; below that it's a
  drawer opened from a top bar that keeps the tenant switcher always reachable.
  The tablet 64px icon-rail refinement (§C.7) is deferred visual polish — the
  shell is navigable end to end at every width, which is what this stage needs.
- `src/routes/LoginPage.tsx` — a minimal email+password form so the stage is
  verifiable end to end. A 401 renders one generic "Email or password is
  incorrect." (no user enumeration, spec §7). _Stage C3 replaces this with the
  real split-panel page (`AuthLayout` + `AuthArtPanel`), adds `RegisterPage`,
  and points post-login at `/workspace`._
- **New primitive: `Alert`** (`src/components/Alert.tsx`). It was on the
  C1-deferred list (Select / Alert / Nav); C2 needs it for the login error
  region and the blocking tenant-switcher error. Built token-driven like the C1
  eight — reported as a scope addition.

**Session 1 (done) — API client + auth:**

- `src/lib/api-client.ts` — the single fetch wrapper. Every request goes through
  it. Attaches `Authorization: Bearer` (except login/refresh/register) and
  `X-Tenant-ID` (except on `GLOBAL_PATHS`). On a 401 it does exactly one silent
  token refresh + one retry, then ends the session — never a loop. Normalizes
  every failure to an `ApiError { status, message, fieldErrors }`.
- `src/lib/global-paths.ts` — an **exact-match** mirror of the backend's
  `apps/tenants/authentication.py` `GLOBAL_PATHS`. Not a prefix test — same
  security reasoning as the backend (a prefix would silently exempt future
  sub-routes).
- `src/lib/auth/` — token storage + the auth React context.
  - **Access token: in memory only.** Never in `localStorage`/`sessionStorage`.
  - **Refresh token: `sessionStorage`.** Deliberate tradeoff, documented at the
    point of storage (`token-store.ts`): `sessionStorage` is as XSS-exposed as
    memory, but clears on tab close (unlike `localStorage`). The real fix is an
    HttpOnly refresh cookie, which needs a backend change — out of scope here.
  - On load, a stored refresh token is exchanged for a new access token _before_
    any authenticated UI renders.
  - SimpleJWT rotates refresh tokens (`ROTATE_REFRESH_TOKENS`), so every refresh
    response replaces the stored token.
- `src/lib/tenant/current-tenant.ts` — a plain holder for "which tenant id goes
  in the header." **Not authorization** — the server re-resolves membership every
  request. The real writer (`TenantProvider`) and the structural cache-isolation
  guarantee arrive in Session 2.
- Dev-server proxy (`vite.config.ts`): `/api/*` → `http://localhost:8000`, so the
  browser makes same-origin requests and no backend CORS config is needed.
- Tests use **MSW** (`src/test/msw/`) to intercept HTTP at the network layer.

### Known gaps reported in C2 — both closed in C3 §0

1. ~~No `POST /api/auth/logout/`~~ — **closed.** `logout()` now fires a
   best-effort call that blacklists the refresh token server-side (§4.6); local
   state still clears unconditionally.
2. ~~No endpoint returns the current user~~ — **closed.** `GET /api/users/me/`
   returns `{id, email}`; `UserMenu` fetches it so the email survives a reload.

## Stage C1 scope

C1 stands up the foundation only:

- The design tokens from `docs/ui-design-specification.md` §C.1, transcribed verbatim
  into `src/styles/theme.css` (the **only** place raw color/size/shadow values may
  appear).
- Eight component primitives in `src/components/`, exported through
  `src/components/index.ts`: `Button`, `Input`, `Table`, `Card`, `Badge`, `Modal`,
  `Skeleton`, `EmptyState`.
- A dev-only component showcase (`src/dev/`), removed in C3 once real pages
  proved the primitives.

No routing, no API client, no auth, no pages — those begin in C2.

## Commands

```
npm install          # once
npm run dev           # Vite dev server
npm run build          # tsc -b (type-check) then vite build
npm test               # Vitest run (jsdom + React Testing Library)
npm run test:watch     # Vitest watch mode
npm run lint           # ESLint
npm run format         # Prettier --write
```

`npm run build` type-checks first; a build that only passes because type-checking was
skipped is not a passing build.

## Notes

- Fonts are bundled via `@fontsource` — no font CDN `<link>`, so the app renders with
  no third-party network access. **Geist Sans** (weights 400/500/600 — the only ones
  the §C.1 type scale uses) for all UI text; **Geist Mono** (400) for IDs, slugs,
  idempotency keys and JSON payloads (the `font-mono` utility / `--text-mono` token).
  Swapped from Inter in the typography addendum — a token-level change
  (`--font-sans` / `--font-mono` in `theme.css`), Geist's metrics are close enough
  that no layout moved. The system stack stays as the per-face fallback.

### Colour tokens

Every colour comes from a token in `src/styles/theme.css` — no raw hex anywhere else.
The token utilities match the §C.1 token names exactly: `bg-base`, `bg-raised`,
`bg-overlay`, `border-subtle`, `border-strong`, `text-primary`, `text-secondary`,
`text-muted`, `bg-accent-600`, `text-success`, etc. (The CSS variables behind them drop
the redundant role word — `--color-primary`, not `--color-text-primary` — so Tailwind v4
generates `text-primary` rather than `text-text-primary`. Dark values are byte-identical
to §C.1.) One side effect: `text-base` is a **colour** utility here (the base surface
colour), not Tailwind's 1rem font-size default — use the type scale (`text-body`,
`text-h1`, …) for sizing; `text-sm`/`text-lg`/etc. are unaffected.

Two themes (C3b): the same utility resolves to a dark or light value depending on the
`data-theme` attribute on `<html>`. Components never branch on the theme. Two tokens
need care across themes:

- **`text-muted` is for decorative / de-emphasised text only** — it fails WCAG AA for
  body text in *both* themes (dark `#6B6B7B` ~3.5:1 on `bg-raised`; light `#8B8B98`
  ~3.4:1). Anything a user needs to read — timestamps, IDs, counts, values, meaningful
  helper text — uses **`text-secondary`** (7.6:1 dark, 8.7:1 light). Spec-owner
  decision; the same note is in `theme.css`.
- **`accent-600` / `accent-500` are roles, not a lightness ramp.** `-600` is the base
  accent, `-500` is emphasis (hover fill + accent text). In dark `-500` is *lighter*
  than `-600`; in light it's *darker* (a lighter light-mode purple fails AA as accent
  text on the tint). There's a prominent cross-theme note at the token definition.
- Tabular figures: use the `num` utility on money, counts, IDs and table numerics.
- `Table` is desktop-shaped only. The mobile stacked-card transform (§C.7) is deferred
  to Stage C4, the first page with a real table.

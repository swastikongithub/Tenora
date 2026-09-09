# Multi-Tenant SaaS Billing Engine — UI/UX Specification (Section C)

**Status:** Activates §C of the Project Master Specification, which was previously "not started." Derived from seven visual references provided by the user. Every element below maps to a real model, service, or endpoint from §B of the master spec, or is explicitly marked as Phase 2 / not-yet-buildable.

**Reference discipline:** These references informed layout, hierarchy, density, and visual language only. No logos, brand names, copy, illustrations, or proprietary assets are reproduced. Product identity is original.

\---

## C.0 Reference Analysis — What Was Taken, What Was Rejected

|Reference|Patterns adopted|Rejected, and why|
|-|-|-|
|Dark admin dashboard (purple)|Persistent left sidebar with grouped/collapsible nav; 4-across KPI stat row with one "featured" highlighted card; large chart panel + narrower ranked-list panel side by side; dense data table with status pills, avatars, and per-row overflow action|Total Income / Profit / Revenue / Conversion — no such data exists; Session by Country — no geo data collected; "upgrade to pro" sidebar promo — this app *is* the billing product, not a consumer of one|
|Light settings page|Horizontal tab bar within a settings shell; two-column form rows (label+helper left, inputs right); section dividers; billing-history table with sortable headers and status pills|Card Number / CVV / Name-on-card fields — **must never be built**; PANs are never touched by this app (Stripe Checkout/Elements owns this). "Add another card" — same reason. Billing history rows — Phase 2 (`Invoice` model doesn't exist yet)|
|Light analytics dashboard|Time-range segmented control (30/90/6mo/12mo); mixed card grid where one tile is visually dominant; donut chart paired with a ranked legend table|Total visits, pages/visit, avg visit duration, traffic sources, share of voice, "my competitors" — none of this is billing data or exists in any model|
|Invoice document|Document header/meta block; issuer-vs-recipient two-column block; line-item table (description / unit price / qty / total); right-aligned totals stack with emphasized final total; footer meta columns|Phase 2 only — `Invoice` and `InvoiceItem` exist as names in §B.4 with **no defined fields**. Tax/VAT and discount lines are invented requirements and are NOT adopted|
|Dark pricing page|Plan cards in a row with the middle card emphasized; per-card feature list with check icons; monthly/annual segmented toggle; feature-comparison matrix below|"Pay once, use forever" model conflicts with recurring subscriptions; testimonial/logo strip is marketing filler; annual toggle is **conditional** — only build if annual plans exist, and they currently don't (see §E additions)|
|Invoices dashboard|Master-detail split (list left, detail panel right) with the selected row highlighted; filter chip row with active-filter count; status-segmented list tabs (All / Draft / Unpaid)|Overdue/payout/"time to get paid" metrics — Phase 2 at the earliest; decorative photography in KPI cards; "Payout now" — this app doesn't move money out|
|Split login|Split-panel auth layout (visual left, form right); single-column form with clear labels; primary full-width submit; secondary link row|**Social login (Apple/Google) — explicitly out of scope per master spec §B.1.** "Create account" link — no signup endpoint is currently specified (see §E addition)|

\---

## C.1a Visual Refinement Addendum (post-C1 review)

Added after seeing the C1 showcase rendered. The base token system in §C.1 is confirmed
correct and unchanged — this addendum is additive, not a replacement, and resolves two
things: (1) the showcase read as visually flat with no hierarchy, and (2) the Ghost
button variant is a real defect — pale text with no border and no hover treatment
against a near-black background reads as barely interactive.

**Direction (decided against the Pinterest references):** closer to the dark admin
dashboard reference (gradient-filled "featured" cards, glowing accents on interactive
elements) — but applied narrowly, as an opt-in treatment for hero/primary elements
only, not a general redesign of every surface. Ordinary cards, tables, and panels stay
on the existing flat `bg-raised` treatment from §C.1 — ordinary surfaces should NOT
gain gradients or glow; that would defeat the point of reserving it for emphasis.

### New: `--gradient-featured` token

```
--gradient-featured: linear-gradient(135deg,
  color-mix(in srgb, var(--color-accent-600) 24%, var(--color-raised)),
  var(--color-raised) 70%);
```

A subtle accent-tinted gradient, not a saturated brand-color fill — it should read as
"this card matters," not as a marketing banner. Pairs with the already-defined
`--shadow-accent-glow` for the border/glow treatment.

### Card gets a `featured` variant

`<Card featured>` (or equivalent prop) applies `--gradient-featured` as the background
and `--shadow-accent-glow` as the shadow, in place of the plain `bg-raised` +
`shadow-card` combination. Everything else about Card (radius, padding, header slot)
is unchanged.

**Usage rule — reserve `featured` for genuinely primary content only:** the single
"this is the headline number" KPI tile on a dashboard (e.g. subscription status), not
every card in a grid. If more than one card on a page is `featured`, none of them are
— the whole point is contrast against an otherwise calm surface. This mirrors the
Pinterest admin-dashboard reference, where exactly one stat card in the row carried the
gradient treatment and the rest stayed flat.

### Interactive elements get more consistent glow, not more surfaces get gradient

`--shadow-accent-glow` was defined in §C.1 but underused. Apply it to:

* Primary button `:focus-visible` (in addition to the existing ring)
* The active/selected item in navigation (once nav exists, C2+)
* A table row's selected state may use it as an alternative to the flat
`accent-subtle` background — implementer's call, document which was chosen

This is about interactive/active state feedback, not decoration — it should never
appear on a static, non-interactive element.

### Ghost button — fix, not a variant change

The Ghost button is a real defect from the C1 showcase, not a stylistic choice to
revisit later. It must have:

* A visible `border-subtle` border by default (currently borderless and unreadable
against `bg-base`)
* A `bg-overlay` (or similar) background on hover, so it has an unambiguous
interactive affordance
* The same `focus-visible` ring as every other button variant

### Surface hierarchy — a small, targeted adjustment, not a token rewrite

The gap between `bg-base` (#0B0B0F) and `bg-raised` (#141419) reads as too subtle in
practice. Do not invent new values freely — first try increasing `border-subtle`'s
visual presence (e.g. verify it's actually 1px and fully opaque where used, not lost
under `bg-raised`'s own near-black tone) before touching either color value. If a
color value must change to fix real hierarchy, keep the change minimal (a few percent
lightness) and report the before/after exactly — this is the same "report, don't
silently redefine" rule that applied to `text-muted`'s contrast issue.

**This is deliberately a small, targeted addendum — not a general visual overhaul.**
Ordinary components (Table, Input, plain Card, Badge, Skeleton, EmptyState) are
unchanged from §C.1. Only: the new `featured` Card variant, more consistent glow on
already-interactive elements, the Ghost button fix, and a possible small hierarchy
adjustment.

### Visual direction

Dark-first, purple-accented, data-dense. Chosen over the light references because: it matches the majority of provided references, it suits a developer/infrastructure-facing product, and it lets the operationally-focused screens (webhook log, usage metering, reconciliation) read as deliberate rather than empty.

Light mode was deferred at C1 and **built in Stage C3b** (`docs/stage-c3b-spec.md`): a parallel token set under `[data-theme='light']`, a `ThemeProvider` + sidebar toggle, system-preference default with an explicit choice persisted. The dark values below are unchanged; the light values and their measured contrast ratios are recorded after them.

### Color

```
Surface
  bg-base          #0B0B0F   page background
  bg-raised        #141419   cards, panels
  bg-overlay       #1C1C24   modals, dropdowns, hover
  border-subtle    #24242E   card borders, dividers
  border-strong    #33333F   input borders, focused dividers

Text
  text-primary     #F4F4F6
  text-secondary   #A0A0AE   labels, helper text
  text-muted       #6B6B7B   timestamps, disabled

Accent (primary)
  accent-600       #7C5CFF   primary buttons, active nav, focus rings
  accent-500       #9277FF   hover
  accent-subtle    rgba(124,92,255,0.12)   active nav bg, selected row

Status  (used for subscription status, webhook status, membership role)
  success          #34D399   ACTIVE, processed, reconciled
  warning          #FBBF24   TRIALING, pending, retrying
  danger           #F87171   PAST\_DUE, failed, mismatch
  neutral          #8B8B9B   CANCELED, terminal
```

Status color must never be the only signal — always pair with a text label (accessibility, §C.8).

**Light theme (Stage C3b).** Active under `[data-theme='light']`. Ratios are WCAG 2.1
against the real rendered surface (status rows composite the 12%-alpha tint first);
AA bar 4.5:1 body text, 3:1 large text / UI.

```
Surface
  bg-base          #FAFAFA   text-primary 17.6:1 · text-secondary 8.3:1
  bg-raised        #FFFFFF   text-primary 18.3:1 · text-secondary 8.7:1
  bg-overlay       #F4F4F6   text-primary 16.7:1 · text-secondary 7.9:1
  border-subtle    #E4E4EA   hairline divider — ~1.2:1, not a sole boundary (as dark's #24242E)
  border-strong    #8E8E9E   input boundary — 3.09:1 / 3.22:1 (base / raised); ~#909090 is the 3.0 floor
                             (darkened from the first-draft #CBCBD3, which was 1.6:1)

Text
  text-primary     #14141B
  text-secondary   #4A4A57   labels, helper text
  text-muted       #8B8B98   3.06–3.36:1 — FAILS AA; decorative / de-emphasised ONLY,
                             exactly as dark's #6B6B7B. Readable text uses text-secondary.

Accent (primary)     see the cross-theme note — -600/-500 are ROLES, not a light→dark ramp
  accent-600       #6D4FEF   base accent. As text: 5.0 / 5.2 / 4.8:1 (base/raised/overlay).
                             White label on the fill: 5.2:1
  accent-500       #5A3FD6   emphasis (hover fill + accent text). DARKER than -600 here
                             (dark has it lighter): as text on the accent-subtle tint 5.9:1
  accent-subtle    rgba(109,79,239,0.10)
  on-accent        #FFFFFF   label on an accent-600 fill (new token; dark = #F4F4F6)

Status  (as Badge text on the matching 12%-alpha tint, over bg-raised / bg-base)
  success          #046A46   5.5 / 5.3:1
  warning          #92400E   5.9 / 5.7:1
  danger           #C01C1C   5.0 / 4.8:1   (also the danger-button fill: base label 5.9:1)
  neutral          #63636F   5.0 / 4.8:1

Elevation / misc
  shadow-card      0 1px 2px rgba(17,17,34,.09)
  shadow-overlay   0 8px 32px rgba(17,17,34,.16)
  shadow-accent-glow  0 0 0 1px accent-600, 0 4px 20px rgba(109,79,239,.22)
  gradient-featured   linear-gradient(135deg, color-mix(accent-600 14%, raised), raised 72%)
  scrim            rgba(15,15,24,.45)   modal / drawer backdrop (new token; dark = rgba(0,0,0,.6),
                                        replacing a hardcoded bg-black/60)
```

`accent-500` being darker than `accent-600` in light is forced: `accent-500` is also a
text colour (accent Badge, active-nav label, `Alert variant="info"`) and on a light tint
a lighter-than-600 purple only reaches ~3.5:1. Treat the `-600`/`-500` suffixes as roles
(base / emphasis), not as a consistent lightness ramp across themes.

### Typography

```
Font    Inter (or system-ui fallback stack). One family only.
Numeric Tabular figures (font-variant-numeric: tabular-nums) on ALL money,
        counts, IDs, and table numerics — non-negotiable for a billing UI.

display   32px / 40   600    page titles
h1        24px / 32   600    panel titles
h2        18px / 26   600    section headings
body      14px / 22   400    default
label     13px / 18   500    form labels, table headers
caption   12px / 16   400    helper text, timestamps
mono      13px        400    IDs, event IDs, idempotency keys, JSON payloads
```

### Spacing, radius, elevation

```
Spacing scale (4px base): 4, 8, 12, 16, 24, 32, 48, 64
Radius:  sm 6px (inputs, badges) · md 10px (buttons, cards) · lg 16px (panels, modals)
Shadow:  card    0 1px 2px rgba(0,0,0,.4)
         overlay 0 8px 32px rgba(0,0,0,.6)
Glow (accent only, sparingly): 0 0 0 1px accent-600, 0 4px 24px rgba(124,92,255,.2)
```

### Components

* **Button** — primary (accent-600 fill), secondary (bg-overlay + border-strong), ghost (transparent, text-secondary), danger (danger fill, destructive only). Sizes sm 32px / md 40px. States: default, hover, active, focus-visible (2px accent ring, 2px offset), disabled (50% opacity, no pointer), **loading (spinner replaces label, button stays same width — no layout shift)**.
* **Input / Select** — 40px, bg-base, border-strong, radius sm. Label above (label style), helper below (caption). Error: danger border + danger helper text + `aria-invalid` + `aria-describedby`.
* **Table** — header row bg-raised, label style, sortable columns show direction affordance. Rows 52px, hover bg-overlay, `border-subtle` bottom. Right-align all numerics. Per-row overflow menu at the right edge. Selected row: accent-subtle bg + 2px accent left border.
* **Card / Panel** — bg-raised, border-subtle, radius lg, padding 24. Optional header row: h2 title left, actions right.
* **Badge / Status pill** — 22px, radius sm, 12px text, colored text on 12%-alpha background of the same hue. Always contains a word, never color alone.
* **Alert** — full-width bar, radius md, left icon, colored left border, text-primary body. Variants: info/success/warning/danger.
* **Modal** — bg-overlay, radius lg, max-width 480 (forms) or 640 (detail). Focus trapped, Escape closes, focus returns to the invoking element, backdrop click closes only if no unsaved input.
* **Nav (sidebar)** — 240px, bg-raised, grouped sections with caption-style group labels. Active item: accent-subtle bg + accent text. **Tenant switcher pinned at top** (see C.2). User menu pinned at bottom.
* **Chart** — accent-600 primary series, monochrome purple ramp for additional series. No gradient fills heavier than 15% alpha. Always render an accessible data table alternative or `aria-label` summary.
* **Pagination** — page-size select (25/50/100) + prev/next + "showing X–Y of Z". Server-driven; do not fetch-all-and-slice-client-side.
* **Empty state** — icon, one-line headline, one-line explanation, primary action if one exists. Never a blank panel.
* **Loading state** — skeleton blocks matching final layout dimensions (not spinners) for tables/cards; inline spinner only for button actions.
* **Error state** — inline panel with what failed, and a retry action. Never a bare "Something went wrong."

\---

## C.2 The Tenant Switcher (app-specific, not from any reference)

This is the single most important UI element in the product and appears in **none** of the references — because none of them are multi-tenant apps. It must be designed deliberately.

```
UI component   → Tenant switcher (sidebar top, persistent, all authenticated pages)
required data  → list of tenants the user belongs to, with role per tenant
model/service  → Membership (select\_related tenant)
endpoint       → GET /api/tenants/me/
auth           → authenticated (global endpoint, no X-Tenant-ID)
authorization  → any authenticated user
tenant scope   → n/a — this is the control that SETS tenant scope
loading        → skeleton pill in sidebar header
empty          → "No workspaces yet" + Create workspace action
error          → inline retry in the switcher; the rest of the app is unusable
                  without tenant context, so this failure is blocking
```

Behavior requirements:

* The currently selected tenant is what the frontend sends as `X-Tenant-ID` on every tenant-scoped request. **This is a client-held value; it is never trusted by the backend** — the server re-resolves `Membership` on every request regardless (master spec §A.1). The UI must not imply otherwise.
* Switching tenant must clear all tenant-scoped cached data and refetch. Stale data from the previous tenant appearing after a switch would be a visible isolation failure, even if the server behaved correctly.
* The switcher shows the user's role in each tenant, so `OWNER`-only actions elsewhere are predictable rather than surprising.

\---

## C.3 Page Inventory

Built strictly from endpoints that exist or are specified in master spec §B.7. Ordered by build priority.

|#|Page|Backing endpoints|Status|
|-|-|-|-|
|1|Login|`POST /api/auth/login/`|Buildable now|
|2|Workspace selection / creation|`GET /api/tenants/me/`, `POST /api/tenants/`|Endpoints pending review|
|3|Members|`GET /api/memberships/`, `POST /api/memberships/`|Endpoints pending review|
|4|Subscription \& Plans|`GET /api/plans/`, `GET/POST/PATCH /api/subscriptions/current/`|Endpoints not yet built|
|5|Overview dashboard|composite of the above|Buildable after 2–4|
|6|Webhook event log|Phase 2 (`WebhookEvent`)|**Do not build yet**|
|7|Usage metering|Phase 2 (`UsageRecord`)|**Do not build yet**|
|8|Invoices|Phase 2 (`Invoice`, fields undefined)|**Do not build yet**|
|9|Reconciliation|Phase 2|**Do not build yet**|

\---

## C.4 Page Specifications (Buildable Now)

### Page 1 — Login

**Purpose:** Authenticate and obtain a JWT pair.
**Role:** Unauthenticated visitor.
**Layout:** Split panel, 50/50 desktop. Left: abstract generative/geometric visual on bg-base (original artwork or CSS gradient mesh — **not** a stock photo, not the reference's floral image). Right: centered form, max-width 400.
**Components:** Wordmark, display-size heading, caption subheading, email input, password input, primary full-width submit, error alert region above the form.

*Implementation note (AuthArtPanel redesign, `docs/authpanel-redesign-spec.md`) — supersedes the C3b addendum-1/addendum-2 ghost-panel + network-motif visual (that work shipped and is superseded, not deleted from history; see `frontend/README.md` for what it looked like). The panel is now typography-driven: the wordmark (top-left), a small uppercase accent eyebrow, and an oversized headline ("Billing that scales with every tenant." — Register uses its own signup-oriented headline) are real page text, not `aria-hidden` — outside the decorative layer entirely, per §7. The decorative layer keeps the grid + grain base texture from C3b and adds 2-3 overlapping gradient-filled angular planes plus 1-2 static concentric rings; each plane drifts on its own `framer-motion` track (front plane travels furthest → parallax), fully disabled under `prefers-reduced-motion`.*

*Light theme is a re-tune of every opacity/mix-percentage token, not a recolour — a wash/plane strength that reads as depth on near-black floods as lavender at the same strength on white. Grid colour switches `--color-strong` → `--color-subtle` (the former is a visible mid-grey on white); grain switches blend mode `overlay` → `soft-light` at higher opacity (`overlay` darkens against a light ground). The plane fill and eyebrow/rule colours need no override — they reference `--color-accent-500/600` directly, which already flip per theme. Headline/eyebrow contrast, measured against the panel's vignette-settled `bg-base` (where the copy sits in both breakpoint compositions): dark ≈ 17.96:1 headline / 5.90:1 eyebrow, light ≈ 17.6:1 headline / 6.46:1 eyebrow — both themes clear AA's 4.5:1 with wide margin.*

*Tablet (768–1279, the `36vh` banner from the C3b mobile-layout fix) reuses the desktop plane geometry rather than a redraw: each plane's box is sized past 100% of the banner's height with a negative top offset, and the panel's own `overflow: hidden` clips the bleed — the visible slice reads as a proportioned facet, not the squashed sliver a literal reuse of the tall-box percentages produced. This was the breakpoint the redesign specifically set out to fix ("sparse tablet"); confirmed resolved by direct screenshot.*

```
UI component   → Login form
required data  → email, password (input only)
model/service  → User (via SimpleJWT TokenObtainPairView)
endpoint       → POST /api/auth/login/
auth           → none (global path)
authorization  → none
tenant scope   → none — tenant context does not exist until after login
loading        → submit button spinner, inputs disabled
empty          → n/a
error          → 401 → "Email or password is incorrect" (do NOT distinguish which —
                  distinguishing enables user enumeration)
                  network/500 → retryable alert
success        → store tokens, redirect to workspace selection (page 2)
```

**Explicitly not built:** social sign-in (out of scope per master spec §B.1), "Remember me" (no decided semantics), "Forgot password" (no reset endpoint exists). *"Create account" — since built (C3 §4.2): `/api/auth/register/` existed from B1, and C3 added a "New here? Create account" link to a minimal `/register` page. The §E note below is resolved.*

**Responsive:** Tablet (768–1279) — visual panel collapses to a top banner. Mobile (<768) — visual panel removed entirely, form full-width with 16px gutters. *Implementation note (C3b addendum-2 follow-up): the layout is a flex column below `xl` and only becomes the 2-col grid at `xl` — a 2-row grid left `<main>` in the `auto` row once the `display:none` panel dropped out of grid flow, so the form clamped to the top of the viewport on phones. The tablet banner is `36vh`, not a literal 160px: the fixed strip read as an arbitrary crop with the form marooned in ~240px of dead space; a viewport-relative banner shows a coherent slice and keeps the remaining space proportionate.*
**Accessibility:** `<form>` with real submit; labels bound via `for`/`id`; error alert `role="alert"`; password field `autocomplete="current-password"`; email `autocomplete="username"`; visible focus ring on every control.

\---

### Page 2 — Workspace Selection \& Creation

**Purpose:** Choose which tenant to operate as, or create one. This page exists because tenant context is a first-class concept — it is the bridge between "authenticated" and "authenticated within a tenant."
**Role:** Any authenticated user.
**Layout:** Centered single column, max-width 560. Heading, then a card list of workspaces, then a secondary "Create workspace" action.

```
UI component   → Workspace list
required data  → tenant name, slug, user's role in it
model/service  → Membership → Tenant
endpoint       → GET /api/tenants/me/
auth           → authenticated (global path, no X-Tenant-ID)
authorization  → any authenticated user
tenant scope   → n/a
loading        → 3 skeleton rows
empty          → "You're not a member of any workspace yet" + Create workspace
error          → inline retry panel

UI component   → Create workspace form (modal)
required data  → name, slug
model/service  → TenantService.create\_tenant (atomic: Tenant + OWNER Membership)
endpoint       → POST /api/tenants/
auth           → authenticated
authorization  → any authenticated user
tenant scope   → n/a — no tenant exists yet
loading        → submit spinner
error          → 400 duplicate slug → inline field error on slug, not a toast
success        → close modal, select the new workspace, go to Overview
```

Each row shows tenant name, slug (mono), and a role badge (`OWNER` accent / `MEMBER` neutral). *Implementation note (C3): the slug uses `text-secondary`, not `text-muted` — `text-muted` fails WCAG AA for readable content and the C1 usage rule (theme.css, §C.8) reserves it for decoration; `TenantSwitcher` already set this precedent.*
**Responsive:** Single column at all breakpoints; card padding 24 → 16 on mobile.
**Accessibility:** List is a real `<ul>`; each row is a button or link, keyboard-reachable; slug field has an explicit format hint bound via `aria-describedby`.

\---

### Page 3 — Members

**Purpose:** View and manage who belongs to the current tenant. This is the page that makes RBAC visible.
**Role:** OWNER (full) and MEMBER (read-only).
**Layout:** Standard app shell (sidebar + content). Page header with title and — for OWNER only — an "Add member" primary button. Below: members table.

```
UI component   → Members table
required data  → member email, role, joined date
model/service  → Membership.objects.for\_tenant(request.tenant)
endpoint       → GET /api/memberships/
auth           → authenticated + X-Tenant-ID
authorization  → IsTenantMember (OWNER and MEMBER both allowed)
tenant scope   → strictly current tenant only
loading        → 5 skeleton rows
empty          → cannot be truly empty (the creating OWNER always exists);
                 if it renders empty, surface it as an error, not an empty state
error          → inline retry panel

UI component   → Add member (modal, OWNER only)
required data  → email of an EXISTING user
model/service  → membership-creation service
endpoint       → POST /api/memberships/
auth           → authenticated + X-Tenant-ID
authorization  → IsTenantOwner — button is hidden for MEMBER, and the server
                 enforces it regardless (client-side hiding is UX, not security)
tenant scope   → tenant comes from X-Tenant-ID only; the form must NOT contain
                 a tenant field, and must NOT contain a role field
loading        → submit spinner
error          → duplicate member → inline field error "Already a member"
                 unknown email → inline field error (exact status undecided, §E)
success        → close modal, optimistic row insert or refetch
```

**Critical UI constraint:** the add-member form has **no role selector**. The endpoint only ever assigns `MEMBER` (master spec §A.4.15). Rendering a role dropdown would imply a capability the API deliberately does not have. Similarly, no invite/resend/pending-invitation UI — this is not an invitation system.

**Responsive:** Desktop/tablet — table. Mobile — table converts to stacked cards (email as card title, role badge and joined date as metadata rows), not a horizontally scrolling table.
**Accessibility:** Real `<table>` with `<th scope="col">`; role badges include text; the add-member modal traps focus and returns it to the trigger on close.

\---

### Page 4 — Subscription \& Plans

**Purpose:** Show the tenant's current subscription state and allow an OWNER to start or change a plan. This is where the billing state machine becomes visible.
**Role:** OWNER (manage), MEMBER (view).
**Layout:** Two sections. Top: current subscription panel. Below: available plans as a card row (pattern from the pricing reference, adapted — cards are *selectable*, not marketing CTAs).

```
UI component   → Current subscription panel
required data  → plan name/code, price + currency, status, period start/end
model/service  → Subscription.objects.for\_tenant(tenant), select\_related plan
endpoint       → GET /api/subscriptions/current/
auth           → authenticated + X-Tenant-ID
authorization  → IsTenantMember
tenant scope   → current tenant
loading        → skeleton panel
empty          → no subscription yet → "No active subscription" + (OWNER only)
                 "Choose a plan"; MEMBER sees the message without the action
error          → inline retry

UI component   → Status badge
required data  → Subscription.status
mapping        → ACTIVE success · TRIALING warning · PAST\_DUE danger · CANCELED neutral
note           → CANCELED is terminal in Phase 1: when status is CANCELED, no
                 reactivate affordance may be shown, because no such transition
                 legally exists (master spec §B.5)

UI component   → Plan cards
required data  → plan name, code, price\_cents, currency, is\_active
model/service  → Plan (global, default manager — NOT tenant-scoped)
endpoint       → GET /api/plans/
auth           → authenticated (global path)
authorization  → any authenticated user
tenant scope   → none — plans are global
loading        → 3 skeleton cards
empty          → "No plans available" (an operational problem, phrase it as such)
error          → inline retry

UI component   → Select / change plan action (OWNER only)
model/service  → SubscriptionService.create\_subscription / change\_plan
endpoint       → POST /api/subscriptions/current/ · PATCH /api/subscriptions/current/
                 (§B.7 corrected at Stage B2 — there is no `POST /api/subscriptions/`
                 route; create and change-plan both go through `/current/`,
                 distinguished by the service call, not the URL)
authorization  → IsTenantOwner
tenant scope   → tenant from X-Tenant-ID only; never a body field
confirm        → plan change opens a confirmation modal stating the current plan,
                 the target plan, and that billing-period effects apply
error          → IllegalStateTransition → show the rejection reason plainly;
                 do not offer a retry that would repeat the same illegal action
```

Money rendering: format from `price\_cents` + `currency` — never hardcode `$`, never divide-and-round in a way that loses cents. Tabular numerics.

**Explicitly not built now:** monthly/annual toggle (no annual plans exist in the `Plan` model — see §E addition), feature-comparison matrix (`Plan` has no feature list field), payment-method form (Stripe owns this in Phase 2 — see security note below).

**Responsive:** Plan cards 3-across desktop → 2 tablet → 1 mobile stacked. Current-subscription panel becomes a stacked definition list on mobile.
**Accessibility:** Plan cards are radio-semantics (`role="radiogroup"` with selectable cards) rather than a set of unrelated buttons; the selected plan is announced; confirmation modal describes the consequence in text, not only visually.

\---

### Page 5 — Overview Dashboard

**Purpose:** A tenant-scoped summary. Adopts the KPI-row-plus-panels layout from the dashboard references, but **every tile is backed by real data**.
**Role:** Any tenant member.
**Layout:** App shell. KPI row (featured card + supporting cards, per the reference pattern). Below: two panels side by side.

**KPI tiles — Phase 1 (real data only):**

```
Subscription status   ← Subscription.status         (featured, accent-highlighted card)
Current plan          ← Subscription.plan.name + formatted price
Renewal date          ← Subscription.current\_period\_end
Team size             ← count of Membership for tenant
```

**Panels — Phase 1:**

```
Members (compact)     ← GET /api/memberships/, top 5 + "View all"
Plan summary          ← current plan detail + upgrade action (OWNER only)
```

**Phase 2 additions to this page (do not build now, reserve layout space):** usage-vs-quota chart (`UsageRecord`), recent webhook events (`WebhookEvent`), reconciliation status. The chart panel from the reference is *intended* for the usage chart — until `UsageRecord` exists, do not render a placeholder chart with fabricated data. Omit the panel entirely.

```
tenant scope   → every tile and panel on this page is tenant-scoped via
                 X-Tenant-ID; switching tenant must refetch all of them
loading        → skeleton KPI cards + skeleton panels
empty          → no subscription → KPI row collapses to a single
                 "Get started: choose a plan" card (OWNER) / informational (MEMBER)
error          → per-tile error state; one failed tile must not blank the page
```

\---

## C.5 Phase 2 Pages — Reserved, Not Specified

These are named so the information architecture accounts for them, but they are **not specified and must not be built**, because their backing models have no defined fields yet (master spec §E).

* **Webhook event log** — the master-detail split pattern from the invoices reference is the right fit: event list left (status-segmented: all / processed / failed / duplicate), payload + processing timeline right. This page is the primary visual proof of the idempotency work and is worth building well when `WebhookEvent` exists.
* **Usage metering** — time-range control + usage-vs-quota chart + ingestion log with idempotency keys.
* **Invoices** — list plus a document detail view; the invoice-document reference is a good template for the detail/print view once `Invoice`/`InvoiceItem` fields are decided. Tax/VAT and discount lines from that reference are **not** adopted as requirements.
* **Reconciliation** — local-vs-Stripe diff view with mismatch flags.

\---

## C.6 Security Constraints on the UI

Restating, because two references would lead an implementer directly into violations:

1. **Never build a card-number, CVV, or expiry input.** Payment details are collected by Stripe Checkout or Stripe Elements in Phase 2. This application must never receive, display, or store a PAN. The settings reference showing card fields is not adoptable.
2. **Hiding an action from a MEMBER is UX, not authorization.** Every OWNER-only action must be enforced server-side (`IsTenantOwner`) regardless of whether the button rendered.
3. **The client-held tenant selection is not a security boundary.** The server re-resolves `Membership` on every request. UI must never present tenant selection as if it grants access.
4. **Never render another tenant's data, even transiently.** Cached data from a previous tenant must be cleared on switch.
5. **Login errors must not distinguish "unknown email" from "wrong password."**

\---

## C.7 Responsive Rules (global)

```
Desktop  ≥1280   sidebar expanded (240px), tables full, KPI row 4-across
Tablet   768–1279 sidebar collapses to 64px icon rail with tooltips;
                  KPI row 2×2; tables keep horizontal structure but drop
                  lower-priority columns (joined date, secondary IDs)
Mobile   <768     sidebar becomes a bottom-anchored drawer via hamburger;
                  tenant switcher moves into the top bar (it must remain
                  reachable at all times — it defines what the user is seeing);
                  KPI row 1-across stacked; tables become stacked cards;
                  modals become full-screen sheets; primary actions move to a
                  sticky bottom bar in forms
```

Tables never become horizontally-scrolling shrunken desktop tables on mobile — they convert to card lists.

## C.8 Accessibility Requirements (global)

* Semantic HTML: `<nav>`, `<main>`, `<table>`, real `<form>` with submit handling, headings in order without skipping levels.
* Every interactive element keyboard-reachable, with a visible `:focus-visible` ring (2px accent-600, 2px offset). Never remove outlines without a replacement.
* Form errors: `aria-invalid` on the field, message bound via `aria-describedby`, error summary region `role="alert"`.
* Status conveyed by color must always include a text label.
* Contrast: text-primary on bg-base and bg-raised must meet WCAG AA (4.5:1 body, 3:1 large). Verify `text-muted` specifically — muted grays on dark backgrounds are the most common failure.
* Modals: focus trapped, Escape closes, focus returns to trigger, `aria-modal` + labelled title.
* Charts: paired with an accessible summary or data table; never color-only encoding.
* Respect `prefers-reduced-motion` — no non-essential transitions when set.

\---

## C.9 Additions to §E (Explicitly Undecided) Arising From This Spec

These surfaced while mapping references to real functionality and are genuinely undecided — not invented requirements:

* **User signup/registration** — *(Resolved — B1 shipped `POST /api/auth/register/`; C3 §4.2 builds the UI. Email verification added by `docs/email-verification-spec.md`: registering leaves the account unverified — no login until the emailed link is used; "check your email" replaces C3's auto-login success path; `/verify-email` is the new landing route. Activation and password reset remain out of scope — deliberately minimal beyond verification.)* Users can be created from the running app (email + password). The login page's "Create account" link points at `/register`. The add-member flow is unchanged and correct: it adds an *existing* user by email.
* **Password reset** — no endpoint; the login reference's "Forgot password" link has nothing to point at.
* **Billing interval on `Plan`** — the pricing reference's monthly/annual toggle has no backing field. `Plan` has `price\_cents` and `currency` but no interval. If plans are implicitly monthly, that should be stated; if annual plans are wanted, `Plan` needs an interval field.
* **Plan feature list** — the comparison-matrix pattern needs per-plan feature data that `Plan` does not model.
* **Light mode** — *(Resolved — built in Stage C3b. Full parallel token set under `[data-theme='light']`, `ThemeProvider` + sidebar toggle, system-preference default with an explicit choice persisted. Values + contrast ratios recorded in §C.1.)*
* **Frontend stack** — not decided anywhere in the master spec. The backend is DRF (API-only), so a separate SPA is implied, but framework, build tooling, and whether it lives in the same repo are all open.


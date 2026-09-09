# Claude Code Implementation Specification — Stage C1

**Scope:** stand up the `frontend/` foundation — Vite + React + TypeScript + Tailwind v4
scaffold, the design tokens from UI spec §C.1, and the eight component primitives named
in `docs/execution-plan.md` §Stage C1: **Button, Input, Table, Card, Badge, Modal,
Skeleton, EmptyState**.

**Not in scope:** C2 (API client, auth, token storage, tenant switcher, app shell),
C3–C6 (any real page), and all of Stage D / Phase 2. No backend change of any kind.

---

## 1. Objective

Establish the visual and structural foundation every later frontend session builds on,
and get the design tokens right *once* so no page ever hardcodes a hex value. This is
deliberately the least interesting stage of the frontend — its whole value is that
C2–C6 inherit a correct, accessible, token-driven component set instead of each
reinventing a button.

Two things make this stage more than boilerplate:

- **The tokens are a contract, not a starting point.** UI spec §C.1 fixes the entire
  palette, type scale, spacing, radius, and shadow values. They are transcribed
  literally. A "close enough" purple or an invented gray is a defect.
- **Several primitives encode real product constraints.** `Badge` must never convey
  status by color alone (§C.8). `Button` must not shift layout when it enters its
  loading state (§C.1). `Modal` must trap focus and return it to the trigger (§C.8).
  These are the requirements that get skipped when a component library is thrown
  together quickly, and they are the reason this stage is specified rather than
  improvised.

This stage has no backing endpoints and touches no tenant data, so it is the one
frontend stage with no isolation surface — that begins in C2.

## 2. Inspect Before Implementing

Read these first. Repository is ground truth.

```
CLAUDE.md
docs/execution-plan.md               — Part 1 decisions #2/#3/#5; Part 2 Stage C (C1 scope)
docs/ui-design-specification.md      — §C.1 tokens + component specs (THE source for this stage)
                                        §C.6 security constraints on the UI
                                        §C.7 responsive rules
                                        §C.8 accessibility requirements
docs/project-master-spec.md          — §C status (stale — see §4.5); §E open questions
                                        (light mode is deferred)
.gitignore                           — needs frontend entries added
```

Current state: no `frontend/` directory exists. The repository is backend-only —
Django project at the root (`manage.py`, `apps/`, `config/`), Phase 1 test suite green
at 57/57 as of commit `dace7ef`. Node 22 / npm 11 are available.

## 3. Existing Functionality That Must Not Change

- **No backend file may be modified.** Not `config/settings.py`, not `config/urls.py`,
  not any app. This stage adds a frontend directory and nothing else. CORS, static-file
  serving, and any dev-proxy wiring belong to C2 when there is an actual API call to
  make — do not add them speculatively here.
- `python manage.py test` must still report **57/57** afterwards. Adding a frontend must
  not perturb Django's test discovery (a stray `frontend/` package importable by Django
  would be a defect).
- `docs/ui-design-specification.md` is the design authority — do not "improve" its token
  values, rename its tokens, or substitute a Tailwind default palette for them.

## 4. Required Changes

### 4.1 Scaffold

- Vite + React + TypeScript, in `frontend/` at the repository root (execution plan
  decision #3 — same repo, one clone for a reviewer).
- **Tailwind v4** via the `@tailwindcss/vite` plugin, CSS-first configuration
  (`@import "tailwindcss";` + `@theme { … }`). Do **not** create a JS
  `tailwind.config.js` v3-style config — v4's CSS-first `@theme` is the decided
  approach, and it maps the §C.1 tokens to CSS custom properties directly.
- **Inter via `@fontsource/inter`** (bundled with the app), not a Google Fonts `<link>`.
  The app must render correctly with no network access to third-party hosts.
- **ESLint + Prettier**, configured now rather than retrofitted across six sessions of
  code. Vite's React-TS template ships an ESLint config; add Prettier alongside it and
  make sure the two do not fight over formatting rules.
- Scripts: `dev`, `build` (type-check **then** build), `test`, `lint`, `format`.
- `frontend/README.md` — how to run dev/test/build/lint, and the showcase-route note
  from §4.4.
- Root `.gitignore`: add `frontend/node_modules/`, `frontend/dist/`, `frontend/coverage/`.

### 4.2 Design tokens

Transcribe **verbatim** from UI spec §C.1 into `@theme` in a single stylesheet. No
invented values, no rounding, no additions:

- **Surface** — `bg-base #0B0B0F`, `bg-raised #141419`, `bg-overlay #1C1C24`,
  `border-subtle #24242E`, `border-strong #33333F`
- **Text** — `text-primary #F4F4F6`, `text-secondary #A0A0AE`, `text-muted #6B6B7B`
- **Accent** — `accent-600 #7C5CFF`, `accent-500 #9277FF`,
  `accent-subtle rgba(124,92,255,0.12)`
- **Status** — `success #34D399`, `warning #FBBF24`, `danger #F87171`,
  `neutral #8B8B9B`
- **Type scale** — display 32/40/600, h1 24/32/600, h2 18/26/600, body 14/22/400,
  label 13/18/500, caption 12/16/400, mono 13/400
- **Spacing** 4-base: 4, 8, 12, 16, 24, 32, 48, 64
- **Radius** sm 6 / md 10 / lg 16
- **Shadow** card `0 1px 2px rgba(0,0,0,.4)`, overlay `0 8px 32px rgba(0,0,0,.6)`,
  accent glow `0 0 0 1px accent-600, 0 4px 24px rgba(124,92,255,.2)`

Plus two global rules:

- A `tabular-nums` utility, applied to **all money, counts, IDs, and table numerics**
  (§C.1 calls this non-negotiable for a billing UI).
- `prefers-reduced-motion` respected globally — no non-essential transitions when set
  (§C.8).

**Dark theme only.** Do not build a light theme or a theme toggle — UI spec §C.1
defers light mode explicitly, and a toggle is forbidden until the dark theme is
complete.

### 4.3 The eight primitives

Exactly the eight named in execution plan §C1. Each implements the states its §C.1
entry specifies — the listed requirements are the acceptance surface, not suggestions:

| Component | Requirements from §C.1 / §C.8 |
|---|---|
| **Button** | Variants primary (accent-600 fill) / secondary (bg-overlay + border-strong) / ghost / danger. Sizes sm 32px, md 40px. States: default, hover, active, `focus-visible` (2px accent ring, 2px offset), disabled (50% opacity, no pointer events), **loading — spinner replaces the label and the button keeps its width; no layout shift** |
| **Input** | 40px, bg-base, border-strong, radius sm. Label above (label style), helper below (caption). Error state: danger border + danger helper + `aria-invalid` + `aria-describedby` |
| **Table** | Header row bg-raised + label style; rows 52px; hover bg-overlay; `border-subtle` bottom; **numerics right-aligned**; selected row = accent-subtle bg + 2px accent left border; sortable columns show a direction affordance. Real `<table>` with `<th scope="col">` |
| **Card** | bg-raised, border-subtle, radius lg, padding 24. Optional header row: h2 title left, actions right |
| **Badge** | 22px, radius sm, 12px text, colored text on a 12%-alpha background of the same hue. **Always renders a text label — status must never be conveyed by color alone.** Variants cover the status palette (success/warning/danger/neutral) and the accent role used for `OWNER` |
| **Modal** | bg-overlay, radius lg, max-width 480 (forms) / 640 (detail). **Focus trapped; Escape closes; focus returns to the invoking element**; `aria-modal` + labelled title; backdrop click closes **only when there is no unsaved input** |
| **Skeleton** | Blocks matching final layout dimensions — **not** spinners (spinners are for button actions only). Respects `prefers-reduced-motion` |
| **EmptyState** | Icon, one-line headline, one-line explanation, optional primary action. Never renders as a blank panel |

Export via a single barrel (`src/components/index.ts`) so later stages import from one
place.

Components that appear in §C.1 but are **out of scope for C1** — build them when the
page that needs them is built: Select, Alert, Nav/sidebar, Chart, Pagination, and the
Loading/Error *page-level* states.

### 4.4 Showcase route — temporary scaffolding, must be flagged as such

There are no real pages until C3, so the primitives need a surface to be seen on. Build
a single showcase view rendering every primitive in every variant and state. This is
the visual acceptance surface for this stage.

**It is scaffolding, not product, and the spec requires it be unmistakable as such:**

- It must live under a clearly non-product path (e.g. `src/dev/`) and mount only when
  `import.meta.env.DEV` is true, so it **cannot ship in a production build**.
- It must carry a visible in-page banner stating it is development scaffolding.
- `frontend/README.md` must record that it is temporary and name C3 as the point at
  which it is removed or permanently gated.
- It must be recorded as a tracked item in `docs/project-master-spec.md` §C (see §4.5),
  the same way B3's known limitation was recorded in §B.17/§F.1 — so someone reading
  only the master spec still learns the showcase is scaffolding with a removal point.
- The C3 spec, when written, inherits the obligation to remove or gate it. Anyone
  reading this file later should not have to guess whether the showcase was meant to
  stay.

Do not add a router to serve it — C1 has no routing (§12). Mounting it as the dev-only
root of the app is sufficient and correct for this stage.

### 4.5 Correct the stale §C in `docs/project-master-spec.md`

`docs/project-master-spec.md` §C currently reads **"Status: not started"** and invites
the reader to supply a visual reference, even though `docs/ui-design-specification.md`
already exists and its own header states that it activates §C. The master spec is
therefore wrong about the current state of the project — exactly the spec/repo drift
CLAUDE.md's working agreement says to report rather than leave in place.

C1 is the first stage to touch the UI, so it corrects it. Two edits, both small:

1. Replace §C's "not started" status with a pointer to `docs/ui-design-specification.md`
   as the activated design authority, preserving the three constraints already listed
   there (every element maps to a real model/service/endpoint; expose the engineering
   concepts; no page built purely because it looks good).
2. Add the tracked showcase note: a dev-only component showcase exists from C1, is not
   part of the product, and is removed or permanently gated at C3.

Do not rewrite the rest of §C, and do not copy the UI spec's contents into it — a
pointer plus the tracked item is the whole change.

## 5. Files Likely Affected

```
new:      frontend/  (package.json, vite.config.ts, tsconfig*.json, index.html,
                      src/main.tsx, src/styles/theme.css,
                      src/components/{Button,Input,Table,Card,Badge,Modal,
                                      Skeleton,EmptyState}.tsx + index.ts,
                      src/dev/Showcase.tsx,
                      src/components/__tests__/*.test.tsx,
                      eslint/prettier config, README.md)
modified: .gitignore
          docs/project-master-spec.md   (§C only — see §4.5)
```

**No backend file, and no file outside `frontend/` other than `.gitignore` and
`docs/project-master-spec.md` §C.** If you find you need to change Django settings,
`config/urls.py`, or any app to complete this stage, **stop and report why** — that
would mean C1's scope was drawn wrong, and CORS or proxy wiring is C2's problem, not
C1's.

## 6. Design-System Rules

- **No hardcoded hex values outside the token stylesheet.** Every color in every
  component comes from a token. A raw `#7C5CFF` in a component is a defect.
- Money and other numerics always render with tabular figures. Never hardcode a `$` —
  currency comes from data (this binds from C5 onward, but the utility exists now).
- One font family (Inter). No secondary display face.
- Status color always accompanies a text label; color is never the only signal.
- Skeletons for content loading; inline spinners only for button actions.

## 7. Security & Accessibility Constraints

From UI spec §C.6 and §C.8. Two of these bind even at the primitive level:

1. **Never build a card-number, CVV, or expiry input** — not as a component, not as a
   showcase example, not as a "just to demo the Input" placeholder. Stripe owns payment
   collection (master spec; CLAUDE.md). This app must never have such a field in it.
2. **`Badge` may not convey meaning by color alone** (§C.8) — enforced in the component
   API, not left to the caller's discretion.
3. Every interactive element keyboard-reachable with a visible `:focus-visible` ring
   (2px accent-600, 2px offset). Outlines are never removed without a replacement.
4. Semantic HTML: real `<table>`, real `<button>`, real `<form>` where applicable;
   headings in order.
5. Form errors: `aria-invalid` on the field, message bound via `aria-describedby`.
6. Modals: focus trapped, Escape closes, focus returns to trigger, `aria-modal` +
   labelled title.
7. Contrast must meet WCAG AA (4.5:1 body, 3:1 large). **Verify `text-muted` #6B6B7B
   specifically** — §C.8 names muted gray on dark as the most common failure, and it is
   worth measuring rather than assuming.

## 8. Responsive Requirements

C1 has no pages, so §C.7's breakpoint behavior is mostly C3+ work. What binds now:

- Primitives must not assume a fixed viewport or a desktop-only container width.
- `Modal` becomes a full-screen sheet below 768px (§C.7).
- **`Table`'s mobile behavior is deferred to C4.** §C.7 requires tables to convert to
  stacked cards (never a horizontally-scrolling shrunken desktop table) on mobile —
  but building that transform in C1, against no real columns and no real content, would
  be speculative. C4 (the Members page) is the first real table and is where the
  stacked-card behavior gets built and verified against actual data. C1's `Table` is
  desktop-shaped only; the C4 spec inherits the obligation to add the mobile transform.
  C1 must not ship a horizontally-scrolling mobile table as a stopgap — it ships no
  mobile table behavior at all, and says so.

## 9. Edge Cases / Things to Verify

- `Button` in loading state: measure that the rendered width is unchanged from its
  resting state. This is the layout-shift requirement and it should be asserted, not
  eyeballed.
- `Modal`: Escape closes; Tab cycles within the modal and does not escape to the page
  behind; focus returns to the element that opened it.
- `Modal` backdrop click with unsaved input present must **not** close.
- `Badge` with no children / no label — the component must make this impossible or fail
  loudly, rather than rendering a bare colored pill.
- `Input` error state wires both `aria-invalid` and `aria-describedby` to the actual
  helper element's id.
- `prefers-reduced-motion: reduce` — skeleton shimmer and transitions suppressed.
- `npm run build` must type-check cleanly; a build that only succeeds because
  type-checking was skipped does not count.

## 10. Tests Required

Vitest + React Testing Library + jsdom, in `frontend/`. Behavior-focused — do not
snapshot-test styling, and do not write assertions that merely restate the JSX.

- **Button** — loading keeps width and hides the label; disabled does not fire onClick;
  each variant renders.
- **Modal** — focus trapped; Escape closes; focus returns to trigger; backdrop click
  blocked when unsaved input is present.
- **Input** — error state sets `aria-invalid` and `aria-describedby` pointing at the
  helper text.
- **Badge** — always exposes an accessible text label.
- **Table** — numeric column right-aligned; selected row gets its distinguishing
  treatment; header cells are `<th scope="col">`.
- **Skeleton / EmptyState** — render contract; EmptyState shows its action only when
  one is provided.

Frontend tests run via `npm test` in `frontend/`. They are **not** wired into
`python manage.py test` — the two suites stay separate, and both must be reported.

## 11. Acceptance Criteria

1. `npm run build` in `frontend/` completes with type-checking, no errors.
2. `npm test` — all tests pass. **Report the exact count**, not "tests pass".
3. `npm run lint` passes clean.
4. `python manage.py test` still reports **57/57** — the backend is untouched.
5. `npm run dev` serves the showcase and every primitive renders in every documented
   state. Provide a screenshot.
6. Every §C.1 token value present and matching the spec exactly. Report any value you
   could not represent in Tailwind v4's `@theme` and how you handled it.
7. `text-muted` (#6B6B7B) contrast measured against `bg-base` and `bg-raised`, with the
   actual ratios reported. If it fails AA, **report it — do not silently change the
   token**; that is a design decision for the spec owner, not an implementation fix.
8. The showcase is DEV-gated, banner-marked, documented in `frontend/README.md` as
   temporary with C3 named as its removal point, **and** recorded as a tracked item in
   `docs/project-master-spec.md` §C.
9. `docs/project-master-spec.md` §C no longer says "not started" and points to
   `docs/ui-design-specification.md` (§4.5).
10. No file outside `frontend/` modified except `.gitignore` and
    `docs/project-master-spec.md` §C.
11. Report any place the UI spec was ambiguous enough to require a judgment call.

## 12. Must NOT Do

- Do not add **react-router**, **TanStack Query**, an API client, auth handling, token
  storage, a tenant switcher, or an app shell. All of that is C2 — building it here
  would make C2's highest-risk work (cache clearing on tenant switch) someone's
  afterthought.
- Do not build any of pages 1–6 from UI spec §C.3.
- Do not build a light theme or a theme toggle.
- Do not build Select, Alert, Nav, Chart, or Pagination — they arrive with the pages
  that need them.
- Do not build the `Table` mobile stacked-card transform — deferred to C4 (§8).
- Do not build a card-number, CVV, or expiry input, in any form, anywhere.
- Do not modify any backend file, or add CORS / dev-proxy config (C2).
- Do not rewrite `docs/ui-design-specification.md`, or expand the §4.5 master-spec edit
  beyond a pointer plus the tracked showcase item.
- Do not substitute Tailwind's default palette, spacing, or radius scale for the §C.1
  values.
- Do not add Storybook — the showcase route is the decided approach.
- Do not leave the showcase reachable in a production build.
- Do not start C2, even though it is the natural next step.

---

## Workflow

Produce a plan first and wait for approval before writing code. This spec is the last
stage of "foundation" work — if the plan it produces is long, that is a signal the
scope has drifted past the eight primitives and the token file.

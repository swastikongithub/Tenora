# Claude Code Implementation Specification — Stage C3b (Light Mode)

**Scope:** add a full light theme alongside the existing dark theme — a second token
set, a theme-switching mechanism, a toggle control, and verification that every
existing component/page (C1, C1a, C2, C3) renders correctly in both themes.

**Not in scope:** Members/Subscription/Overview (C4–C6), any new page, any backend
change, Stage D.

**Timing rationale:** doing this now, before C4–C6 build three more real pages, is
cheaper than retrofitting after. This mirrors the C1a decision to push visual polish
before C2 rather than after.

---

## 1. Objective

The design system was built dark-only, with light mode explicitly deferred (UI spec
§C.1: "confirm that's acceptable" — it's no longer acceptable, this stage builds it).
Because every component was required to consume colors only through tokens (§C.1's
"raw hex outside the token file is a defect" rule, enforced since C1), light mode
should be achievable primarily by defining a second set of token values and a
mechanism to switch between them — not by touching every component's internals. This
stage is the test of whether that discipline actually held.

**What "done" looks like:** every page and component built so far — Login, Register,
Workspace, the app shell/sidebar, every C1/C1a primitive, Modal, Alert — renders
correctly, with passing contrast, in both dark and light themes, switchable via a
control in the UI, with the choice persisted across reloads.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/ui-design-specification.md §C.1, §C.1a  — the dark token system this stage extends
frontend/src/styles/theme.css                — every existing token, verbatim source
frontend/src/components/*.tsx                — confirm token-only color usage; any raw
                                                 hex found is a pre-existing defect to
                                                 report and fix as part of this stage
frontend/src/routes/*.tsx                     — Login, Register, Workspace — the real
                                                 pages this stage must verify
frontend/src/components/layout/*.tsx          — Sidebar, AppShell, TenantSwitcher,
                                                 UserMenu — where the toggle likely lives
```

Current state: Stage C3 committed, 125/125 frontend tests, 70/70 backend. Dark-only.

## 3. Existing Functionality That Must Not Change

- Every dark-mode token value stays exactly as it is — this stage adds a parallel
  light set, it does not modify or "improve" any existing dark value.
- No component's structure, props, or behavior changes — only which token values
  resolve at render time, based on active theme.
- All 125 frontend and 70 backend tests must still pass; new tests are additive.
- The `featured` Card variant (C1a) and the `AuthArtPanel` (C3) both need light-mode
  treatments — see §4.4 and §4.5 — but their *mechanisms* (gradient + glow; layered
  gradient mesh + grain + grid) stay conceptually the same, adapted for a light
  surface, not replaced with something unrelated.

## 4. Required Changes

### 4.1 Theme mechanism

- A `data-theme="dark" | "light"` attribute on the root element (`<html>` or a
  top-level wrapper), driving which token values are active via CSS scoping —
  e.g. dark values under `:root` / `[data-theme="dark"]`, light values under
  `[data-theme="light"]`, so Tailwind's existing token-based utility classes
  (`bg-base`, `text-primary`, etc.) resolve to the correct value automatically
  with **zero changes to component markup**.
- A `ThemeProvider` (React context), providing the current theme and a `setTheme`
  function. On first load: respect `prefers-color-scheme` (system setting) as the
  default; after that, an explicit user choice overrides it and is persisted (
  `localStorage` is appropriate — this is a UI preference, not authorization-relevant
  data, unlike the tenant-selection value from C2, which had a stricter "never trust
  this" caveat that doesn't apply here).
- A toggle control in `Sidebar`/`UserMenu` area (near the existing user
  email/logout — the original Pinterest admin-dashboard reference had exactly this
  placement, a dark-mode toggle at the bottom of the sidebar).

### 4.2 Light token values

Full parallel set to every token in UI spec §C.1. Candidate starting values below —
**verify actual contrast ratios for every text/background pairing that mattered in
dark mode (§C.1's `text-muted` check established this discipline) and report them,
adjusting values as needed rather than assuming these are correct.** This is the same
"report, don't silently pick a number and move on" rule §C.1's contrast work already
established.

```
Surfaces
  bg-base       #FAFAFA
  bg-raised     #FFFFFF
  bg-overlay    #F4F4F6
  border-subtle #E4E4EA
  border-strong #CBCBD3

Text
  text-primary   #14141B
  text-secondary #4A4A57
  text-muted     #8B8B98   (verify — light-mode muted grays have their own,
                             different contrast failure modes than dark-mode ones;
                             don't assume the dark-mode lesson transfers unchanged)

Accent — verify these pass AA on white; a purple tuned for a near-black background
often reads as under-saturated/washed out on white and may need to be measurably
darker for the same contrast guarantee, not just reused as-is
  accent-600    (candidate, verify) #6D4FEF
  accent-500    (candidate, verify) #8266F5
  accent-subtle rgba(109,79,239,0.10)

Status — same caution as accent; verify each against a white/near-white background
  success  (verify, likely needs darkening from #34D399)
  warning  (verify, likely needs darkening from #FBBF24)
  danger   (verify, likely needs darkening from #F87171)
  neutral  (verify)
```

Shadows need their own light-mode values too — a shadow tuned for a near-black
background (`rgba(0,0,0,.4)` etc.) may read as too heavy or too light against white;
verify visually, don't assume the dark values transfer.

### 4.3 Retrofit any raw-hex violations found

Per §2, scan every existing component for hardcoded color values that bypassed the
token system. If C1's discipline held (it was tested and enforced repeatedly), this
should turn up nothing or very little — but verify rather than assume, and fix
anything found as part of this stage (it would have been a defect in the original
stage regardless of light mode).

### 4.4 `featured` Card variant — light-mode treatment

C1a's `--gradient-featured` and `--shadow-accent-glow` were designed for a dark
surface. Define light-mode equivalents that preserve the same *purpose* (this card
matters, use sparingly) without simply inverting values blindly — a gradient that
looked subtle-but-present on near-black may look either invisible or garish on white
at the same alpha values. Verify visually against both a plain light Card and confirm
the "reserve for one hero element" usage rule (C1a) still reads correctly.

### 4.5 `AuthArtPanel` — fix dark, build light, add Framer Motion for both

**4.5.0 — First, fix the dark panel against its own original spec.** The C3
implementation under-delivered against what was actually specified: the shipped
result is one soft blob and a barely-visible grid, not the three-layer depth (large
soft base, mid accent bloom, small sharp highlight), ~4% grain overlay, and
edge-masked grid that C3's spec called for. Before building a light-mode equivalent,
bring the dark panel up to its own original bar. Screenshot the corrected dark panel
and confirm all four elements (three gradient layers at genuinely different
sizes/softness, visible grain, masked grid, drift) are actually present and visible —
not just implemented in code but invisible in practice.

**4.5.1 — Add Framer Motion, justified.** `framer-motion` is approved as a new
dependency specifically for this panel's blob motion, in both themes. Rationale: it's
small, React-native, and — critically — since it animates via React state/props
rather than baked assets, it reads the same CSS custom-property color tokens as
everything else, so it repaints correctly when the theme switches with no duplicated
per-theme animation files (unlike Lottie/Rive, which bake in fixed colors and would
require maintaining two separate exported assets kept manually in sync forever — do
not use those instead). Do not add GSAP or Three.js — GSAP's timeline/orchestration
model is unneeded for independent ambient blob drift, and Three.js is a 3D/WebGL
engine wildly disproportionate to a 2D decorative background.

Use Framer Motion to drive more organic, independent motion per gradient blob
(varying paths/timing per layer, not one uniform CSS keyframe loop) — this is the
concrete improvement over the original CSS-only drift, and the actual reason the
dependency is justified rather than decorative.

**4.5.2 — Build the light-mode equivalent.** Same structural approach as the
(now-fixed) dark version — layered gradients for depth, grain to avoid banding, a
masked grid, organic Framer-driven drift — re-tuned for a light surface, not a flat
recolor. Verify text contrast on the form side still holds (same check as C1a's
"Card featured header on gradient" precedent).

**4.5.3 — Both themes, motion must respect `prefers-reduced-motion`.** Framer
Motion's animations must be fully disabled (not just slowed) when reduced motion is
requested, same requirement as the original CSS drift — verify this still holds with
the new animation approach, don't assume it carries over automatically.

**4.5.4 — Report before/after.** Screenshot the original under-delivered dark panel
alongside the corrected version, and both new light and dark Framer-driven final
versions, so the improvement is visible and reviewable, not just asserted.

### 4.6 Verify every existing page and primitive in both themes

Login, Register, Workspace (list/empty/modal states), the app shell (Sidebar,
TenantSwitcher, UserMenu), and all 9 primitives (Button, Input, Table, Card, Badge,
Modal, Skeleton, EmptyState, Alert) — each needs a visual check in both themes, not
just a token-swap assumption. Screenshot both themes for each.

## 5. Files Likely Affected

```
new:      frontend/src/lib/theme/ (ThemeProvider, useTheme, persistence)
          frontend/src/components/layout/ThemeToggle.tsx (or co-located in UserMenu)
          tests for the above
modified: frontend/src/styles/theme.css (light token set added)
          frontend/src/components/*.tsx (only if raw-hex violations found, §4.3)
          frontend/src/routes/AuthArtPanel.tsx (dark panel fixed to match its
          original spec, light variant added, both Framer-Motion-driven — §4.5)
          frontend/src/components/Card.tsx (light featured treatment, §4.4, if the
          existing implementation needs adjustment beyond token values)
          frontend/src/components/layout/Sidebar.tsx or UserMenu.tsx (toggle placement)
          frontend/README.md
          docs/ui-design-specification.md §C.1 (record the light token values once
          verified — same pattern as recording a hierarchy fix in C1a)
```

No backend file.

## 6. Business Rules

- Theme choice is a client-side UI preference only — never sent to the backend,
  never affects any API request.
- System-preference detection is the default; explicit user choice always wins once
  made.

## 7. Accessibility Requirements

- Every text/background pairing in the light theme must meet the same WCAG AA bar
  already enforced for dark (4.5:1 body text, 3:1 large text/UI). Report actual
  measured ratios for every token pairing that carries real content — same rigor as
  C1's `text-muted` check.
- The theme toggle itself must be keyboard-reachable with a visible focus state, and
  must announce its current state (e.g. `aria-pressed` or equivalent) to assistive
  tech.
- Respect `prefers-reduced-motion` in both themes' animated elements (the art panel
  drift, any skeleton shimmer).

## 8. Edge Cases

- First visit, system in light mode → app opens in light, no flash of dark-then-light.
- First visit, system in dark mode → app opens in dark (current default behavior,
  unchanged).
- User manually picks a theme, then changes their OS-level system theme → the manual
  choice persists and does not get silently overridden.
- Theme persists across a full page reload and across login/logout.
- Switching theme while a Modal is open → the modal itself re-themes correctly, not
  just the page behind it.

## 9. Tests Required

- `ThemeProvider`: defaults to system preference on first load; explicit choice
  persists and overrides system preference on subsequent loads; toggle updates the
  `data-theme` attribute correctly.
- Toggle control: keyboard-operable, correct `aria-pressed`/equivalent state.
- At least one rendering test per primitive confirming it doesn't crash or lose
  required content under `data-theme="light"` (a full visual regression suite isn't
  required, but a basic render-without-error check across the theme switch is).

## 10. Acceptance Criteria

1. `npm run build` clean.
2. `npm test` — all previous tests pass plus new ones, exact count reported.
3. `npm run lint` clean.
4. `.venv/Scripts/python.exe manage.py test` — still 70/70, unaffected.
5. Every token pairing's contrast ratio reported for the light theme, same rigor as
   C1's `text-muted` report — pass/fail stated plainly, not glossed over.
6. Screenshots of Login, Register, Workspace, and the app shell, each in both themes,
   side by side.
7. Confirm zero raw-hex violations found (or report and fix what was found, per §4.3).
8. `git status` — no file outside `frontend/` and the single `docs/ui-design-specification.md`
   token-recording edit.

## 11. Must NOT Do

- Do not modify any dark-mode token value.
- Do not change any component's props, structure, or behavior beyond what's needed
  to fix a raw-hex violation.
- Do not build Members, Subscription, or Overview — C4/C5/C6.
- Do not touch the backend.
- Do not silently pick light-theme color values without reporting their contrast
  ratios — this is the one place in this stage where "looks fine to me" is not an
  acceptable substitute for a measured number, per the established precedent.

---

## Workflow

Produce a plan first and wait for approval before writing code. Given the size
(token system, provider, toggle, plus verification across every existing page and
primitive in both themes), propose a split into sessions if that makes sense — e.g.
token system + provider + primitives first, then page-level verification and the
two bespoke gradient treatments (§4.4, §4.5) second.

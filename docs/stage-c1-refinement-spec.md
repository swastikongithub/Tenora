# Claude Code Implementation Specification — C1 Visual Refinement Addendum

**Scope:** a small, targeted enhancement to the C1 token system and two components,
based on user review of the rendered showcase. This is NOT a redesign and NOT the
start of C2 — it amends what C1 already built, before C2 builds on top of it.

**Not in scope:** anything from C2 (router, API client, auth, tenant switcher, app
shell), any real page, any component beyond Card and Button.

---

## 1. Objective

The C1 showcase, once actually rendered, revealed two real problems:
1. The Ghost button variant is a genuine defect — no border, no hover background,
   pale text on near-black. It doesn't read as interactive.
2. The overall surface hierarchy is flatter than intended, and there's no treatment
   available yet for "this is the one thing on this page that matters" (a hero KPI
   tile, a primary status card) — every card looks the same as every other card.

Fixing both now costs one small session. Fixing them after C2–C6 have built dozens of
components on top of the current tokens would cost much more. This addendum exists to
prevent that retrofit cost.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/ui-design-specification.md §C.1a  — THE spec for this addendum (read this fully;
                                          it explains what NOT to do as much as what to do)
docs/stage-c1-spec.md                  — original C1 spec, for context on what exists
frontend/src/styles/theme.css          — current token definitions
frontend/src/components/Button.tsx     — current Ghost variant
frontend/src/components/Card.tsx       — current Card implementation
frontend/src/dev/Showcase.tsx          — where the new featured Card variant should
                                          be demonstrated
```

Current state: Stage C1 committed (`3346c44`), 31/31 frontend tests, 57/57 backend
tests, all green. This addendum should not break any of that.

## 3. Existing Functionality That Must Not Change

- Every §C.1 base token value (colors, type scale, radius, shadows, spacing) —
  unchanged, unless the hierarchy adjustment in §C.1a genuinely requires a small,
  reported color tweak. Do not touch anything not explicitly named in §C.1a.
- Every other component (Table, Input, Badge, Modal, Skeleton, EmptyState) — **not
  touched by this addendum.** If you find yourself wanting to add glow or gradient to
  one of these, stop — §C.1a is explicit that ordinary surfaces stay flat.
- All 31 existing frontend tests and 57 backend tests must still pass.
- The `text-muted` usage rule from the C1 session (decorative-only, `text-secondary`
  for anything readable) — unaffected by this addendum, do not revisit it.

## 4. Required Changes

### 4.1 `--gradient-featured` token — `theme.css`

Add exactly as specified in UI spec §C.1a:
```css
--gradient-featured: linear-gradient(135deg,
  color-mix(in srgb, var(--color-accent-600) 24%, var(--color-raised)),
  var(--color-raised) 70%);
```
Verify `color-mix()` is supported in the project's target browsers (it's broadly
supported in current evergreen browsers as of 2025; flag if there's a concern for this
project's stated browser support, if any is documented — if none is documented,
proceed).

### 4.2 Card `featured` variant

Add a `featured?: boolean` prop to `Card`. When true:
- Background: `--gradient-featured` instead of `--color-raised`.
- Shadow: `--shadow-accent-glow` instead of `--shadow-card`.
- Everything else (radius, padding, header slot behavior) unchanged.

Update the Showcase to include one example of `<Card featured>` alongside the existing
plain Card examples, so the contrast between them is visible. Label it clearly in the
showcase so it's obvious this is the "use sparingly" variant, per §C.1a's usage rule.

### 4.3 Ghost button fix

Per §C.1a, the Ghost variant must have, by default (not just on hover):
- A visible `border-subtle` border.
- A background transition to something like `bg-overlay` on hover.
- The same `focus-visible` ring treatment every other Button variant already has —
  verify this was actually missing or just visually hard to see; report which.

This is a fix, not a new variant — same `variant="ghost"` API, corrected implementation.

### 4.4 Glow on interactive states

Apply `--shadow-accent-glow` to:
- Primary button `:focus-visible` state, in addition to its existing focus ring (both
  together, not one replacing the other — report how they compose visually).
- Leave the nav/active-item and table-row-selected applications as **out of scope for
  this addendum** — nav doesn't exist until C2, and Table's selected-row treatment
  already has a working flat `accent-subtle` implementation from C1 that doesn't need
  to change right now. Only touch Button in this stage.

### 4.5 Surface hierarchy

Per §C.1a: try increasing `border-subtle`'s effective visual presence first (confirm
it's rendering as intended — full opacity, visible 1px, not accidentally faint) before
changing any color value. If that alone doesn't resolve the flatness, a small, reported
adjustment to `bg-raised` (a few percent lightness, not a hue or saturation change) is
acceptable — report the exact before/after hex and get it into the response, don't
silently commit a changed value without saying so.

## 5. Files Likely Affected

```
modified: frontend/src/styles/theme.css
          frontend/src/components/Card.tsx
          frontend/src/components/Button.tsx
          frontend/src/dev/Showcase.tsx
          docs/ui-design-specification.md (§C.1a already written — no further edit
                                            needed unless the hierarchy fix requires
                                            recording an actual value change, in which
                                            case append it under §C.1a, don't rewrite)
```

No other file. No backend change. No new dependency.

## 6. Edge Cases / Things to Verify

- `Card featured` still respects the header slot (title left / actions right) — the
  gradient background must not visually interfere with header text contrast. Verify
  `text-primary` still reads clearly against `--gradient-featured` at both ends of the
  gradient (near the accent-tinted corner and near the plain-raised corner).
- Ghost button's new border/hover must still pass the same contrast bar as other
  button variants — don't fix invisibility by introducing a different accessibility
  problem.
- The `color-mix()` CSS function — confirm it actually renders in the dev build, not
  just type-checks.

## 7. Tests Required

- Card: `featured` prop applies the gradient background and glow shadow; default
  (non-featured) Card is visually and functionally unchanged — add a test asserting
  the class/style difference between featured and non-featured render output.
- Button: Ghost variant has a border class present by default (not just on
  hover) — assertable via the rendered class list, not a visual-only check.
- All existing Card and Button tests must still pass unmodified.

## 8. Acceptance Criteria

1. `npm run build` clean.
2. `npm test` — all previous 31 tests still pass, plus new tests for §7. Report exact
   count.
3. `npm run lint` clean.
4. `.venv/Scripts/python.exe manage.py test` — still 57/57 (nothing here should touch
   the backend, but verify anyway, same discipline as every prior stage).
5. Screenshot of the updated showcase, specifically showing the featured Card next to
   a plain Card, and the corrected Ghost button, for visual confirmation.
6. Report whether the hierarchy fix (§4.5) was resolved via `border-subtle` alone or
   required a `bg-raised` value change — and if the latter, the exact before/after hex.
7. Confirm no component outside Card and Button was touched.

## 9. Must NOT Do

- Do not add gradient or glow treatment to Table, Input, Badge, Modal, Skeleton, or
  EmptyState in this stage.
- Do not make `featured` the default for Card, or apply it anywhere in the Showcase
  beyond the one labeled example.
- Do not start C2 — no router, no API client, no auth, no tenant switcher, no app
  shell.
- Do not redesign the color palette. Any color value change must be minimal, targeted
  to the specific hierarchy problem in §4.5, and explicitly reported.
- Do not touch the backend.

---

## Workflow

Produce a plan first and wait for approval before writing code. This should be a short
plan — two components and one token addition. If it grows larger than that, scope has
drifted and it's worth stopping to check why.

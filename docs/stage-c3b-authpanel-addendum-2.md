# Addendum — AuthArtPanel: Skeleton-Bar Ghost Panels + Network Motif

**Context:** the ghost panels shipped in the previous addendum (Stage C3b session 2)
are empty translucent rectangles, and a third card was requested to balance the
composition. Empty panels read as unfinished rather than intentionally abstract.
This addendum fills them with non-numeric, non-claiming content, and adds a subtle
background motif that fits the product's actual identity (multi-tenant, distributed)
rather than a generic "tech" cliché.

**Explicitly rejected:** literal binary-digit texture (rows of 0s/1s) — a recognizable
cliché that undercuts the "premium, sophisticated" goal rather than supporting it.
Do not implement this.

---

## Required changes

### 1. A third ghost panel

Add one more abstract floating panel (same construction as the existing two:
`bg-overlay` + opacity modifier, `border-subtle`, `shadow-card`, independent Framer
Motion drift with its own timing/path/rotation — not a clone of an existing one's
motion track). Position it to balance the composition and fill the currently-empty
space — use judgment on exact placement, report the choice. Cap at three total; do
not add a fourth.

### 2. Skeleton-bar content inside all three panels

Each panel gets 2-3 horizontal bars of varying width, styled identically to the
existing `Skeleton` primitive's visual language (same border-radius, same tone
relationship to the panel's own background — i.e. reuse `Skeleton`'s actual token
values/component if practical, don't invent a new visual style for "looks like
loading content"). This reads as "a real UI panel, content abstracted" rather than
"empty placeholder." No real text, no numbers, no labels — purely the bar shapes.

Vary bar count/width slightly panel-to-panel so they don't look like three identical
copies.

### 3. Background network/node motif

A subtle line-and-node motif — small circles ("nodes") connected by thin lines —
rendered as SVG, sitting behind the ghost panels and gradient washes (or wherever it
reads best in the existing layer stack — use judgment, report the z-order chosen).

- Token-driven stroke/fill colors (e.g. `border-subtle` or `accent-500` at low
  opacity — verify visually which reads better in each theme, they may differ).
- Low visual weight — this is atmospheric texture, not a diagram someone is meant to
  read or interpret as literal. Should not compete with the ghost panels or the form
  side for attention.
- Static or very subtle motion is fine — if animated, same `prefers-reduced-motion`
  rule as everything else in this panel (fully disabled, not slowed).
- Must work in both themes — a network motif that reads clearly on the dark wash may
  need different opacity/color on the light one; verify both, don't assume.

## Must NOT do

- No literal binary/code-digit texture.
- No text, numbers, or labels anywhere in the ghost panels or the network motif.
- No more than three ghost panels total.
- Don't let the network motif overpower the gradient/grain/grid work already done —
  it's an additional subtle layer, not a redesign of the panel.

## Verification

- Screenshot the final panel in both themes, showing all three ghost panels with
  skeleton content and the network motif visible.
- `npm test` / `npm run lint` / `npm run build` — confirm nothing regressed.
- Confirm `prefers-reduced-motion` still fully disables all motion in the panel,
  including whatever's added here.

---

## Workflow

Small, additive change to the already-completed `AuthArtPanel`. Produce a short plan
and wait for approval before implementing.

# Claude Code Implementation Specification — AuthArtPanel Full Redesign

**Scope:** replace the current AuthArtPanel content entirely - the ghost panels
(skeleton-bar cards) and the network/node motif from the two prior addenda are
removed, not layered on top of. This is a full visual redesign of the Login and
Register art panel, in both dark and light themes, at desktop, tablet, and mobile
breakpoints. Confirmed against a static mockup the user approved.

**Supersedes:** docs/stage-c3b-authpanel-addendum-2.md (the ghost-panel + network
motif work). That addendum's output is being replaced, not extended - note this
explicitly in the docs update (section 5) so a future reader isn't confused about
which version is authoritative.

**Not in scope:** the form side of Login/Register (inputs, validation, submit
logic) - unchanged. Any other page. Any backend file. Stage C5/C6.

---

## 1. Objective

Replace the current gradient-mesh-plus-ghost-panels art panel with a bolder,
typography-driven design: an oversized confident headline, a small uppercase
eyebrow label, layered translucent geometric planes (angular, overlapping,
gradient-filled - evoking depth via layering and light, not literal 3D rendering)
as background art, concentric depth rings, and the existing grid/grain techniques
retained as base texture. The wordmark moves into the art panel itself (top-left)
rather than only appearing on the form side.

This came from an explicit design process: initial concepts (abstract mascot,
isometric tenant-cell cubes) were tried and rejected as too small/cute; a
typography-driven direction combined with bold layered geometric planes was
confirmed as the right one via a static mockup, at both a stacked (tablet/mobile)
and split (desktop) layout.

## 2. Inspect Before Implementing

```
CLAUDE.md
frontend/src/routes/AuthArtPanel.tsx     - current implementation (ghost panels,
                                            network motif, grid, grain, gradient
                                            washes) - being substantially rewritten
frontend/src/routes/AuthLayout.tsx       - split/stacked layout logic, breakpoint
                                            values (verify these are still what was
                                            set during the recent mobile-layout fix
                                            - don't assume, check the real values)
frontend/src/styles/theme.css            - existing --authart-* token pattern (dark
                                            defaults on .authart, light overrides
                                            under [data-theme='light'] .authart) -
                                            follow this established convention for
                                            any new tokens
docs/stage-c3b-spec.md,
docs/stage-c3b-authpanel-addendum-2.md   - what's being replaced; read for context
                                            on what techniques (grid, grain) are
                                            worth keeping vs. what's being removed
                                            (ghost panels, network nodes)
frontend/src/components/__tests__/       - existing AuthArtPanel tests, to be
                                            substantially rewritten since the
                                            elements they assert on are being removed
```

Current state: navbar redesign + C4 (Members) committed, most recent frontend work
being the mobile AuthLayout breakpoint fix. Confirm exact commit/test counts by
running git log --oneline -5 and the test suites before starting - don't assume a
stale baseline.

## 3. Existing Functionality That Must Not Change

- The form side of Login/Register (inputs, submit handlers, error rendering,
  messageFor() non-disclosure logic) - untouched.
- AuthProvider, TenantProvider, ThemeProvider, routing - untouched.
- The grid-line and grain-texture techniques (banding prevention, subtle
  structural texture) are proven and should be retained as the base layer beneath
  the new geometric planes - this is a redesign of the content layered on top, not
  a rejection of every existing technique.
- prefers-reduced-motion handling - the existing pattern (fully disabled, not
  slowed, using the media-query hook rather than Framer's cached
  useReducedMotion) carries forward to whatever's newly animated here.

## 4. Required Changes

### 4.1 Remove

- The three ghost panels (.authart__ghost--a/b/c) and their skeleton-bar content.
- The network/node SVG motif (.authart__net) and its associated tokens/CSS.
- Any test assertions specific to the removed elements.

### 4.2 New content - both breakpoint layouts

Desktop (split, art panel roughly 1.1-1.2fr vs. form's 1fr):
- Wordmark (existing Wordmark component, top-left of the art panel).
- Near the lower portion of the panel: a small uppercase eyebrow label (e.g.
  "Multi-tenant infrastructure", letter-spaced, accent-colored) above an oversized,
  bold, multi-line headline (e.g. "Billing that scales with every tenant." - treat
  this exact copy as provisional; report if you land on different wording, but
  keep it short, confident, and non-fabricated - it's a tagline, not a claim about
  specific metrics, which is fine per the project's no-fabricated-data rule since
  no numbers are involved).
- A short accent-colored underline/rule beneath the headline as a small
  typographic flourish.
- Background: retained grid + grain, plus 2-3 layered translucent angular planes
  (gradient-filled, varying opacity/stroke) positioned to one side, creating a
  sense of depth without being a literal 3D render - angular/faceted, not rounded
  blobs. Optionally 1-2 concentric rings for additional depth, low opacity.

Tablet/mobile (stacked, art panel as a shorter block above the form):
- Same content (wordmark, eyebrow, headline, planes) recomposed to fit a shorter,
  wider block rather than a tall side panel. The headline may need to shrink
  (smaller font-size token) and the planes' composition will need re-proportioning
  - don't just scale the desktop SVG viewBox and hope it still reads well; verify
  visually.
- Reuse whatever breakpoint values the recent AuthLayout mobile fix established -
  verify these in the code rather than reintroducing new ones.

### 4.3 Motion (Framer Motion - already a dependency, no new package)

- Each geometric plane drifts independently - its own path/amplitude/period, not a
  shared loop (same principle as every other multi-element motion in this
  project).
- A subtle sense of parallax/depth as the planes move is a plus if it reads well;
  don't force it if it looks gimmicky at this composition's scale - use judgment,
  report what was tried.
- Concentric rings, if kept, may have a very slow, near-imperceptible rotation or
  opacity pulse - genuinely optional, drop it if it reads as busy.
- Full prefers-reduced-motion compliance: fully disabled, not slowed, using the
  existing media-query-hook pattern already established in this file (not Framer's
  useReducedMotion, which caches for the tab's lifetime - this was a deliberate,
  documented choice in the current code; carry it forward).

### 4.4 Both themes

- Dark: essentially as confirmed in the mockup - deep purple-tinted radial
  background, bright accent-purple plane fills/strokes, light near-white headline
  text.
- Light: re-tuned, not a flat recolor. Follow the established precedent from the
  previous AuthArtPanel light variant (washes pushed up since purple-on-white has
  less contrast headroom; verify text contrast explicitly). The planes' fill
  gradients, grid opacity, and grain blend mode will likely all need independent
  tuning for a light surface - verify visually in both themes before finalizing,
  and report the final token values (same discipline as every prior
  contrast-sensitive decision in this project - measure, don't guess).
- Headline text contrast is the critical check here: verify text-primary reads
  cleanly against the art panel's background in both themes, especially where it
  may overlap or sit near a geometric plane - this is the same category of check
  as C1a's "featured Card header on gradient" verification.

### 4.5 Register page

Decide whether Register reuses the same headline/eyebrow copy as Login or gets its
own (e.g. a signup-oriented variant) - either is fine, report which and why. The
visual treatment (planes, motion, grid/grain, both themes) is identical structure
either way.

## 5. Files Likely Affected

```
modified: frontend/src/routes/AuthArtPanel.tsx (substantial rewrite)
          frontend/src/routes/AuthLayout.tsx (if the art-panel/form proportion or
                                               content placement needs layout
                                               changes beyond what AuthArtPanel
                                               itself owns)
          frontend/src/styles/theme.css (new --authart-* tokens for the plane
                                          gradients/opacities, both themes;
                                          removal of now-unused ghost/network
                                          tokens)
          frontend/src/components/__tests__/AuthArtPanel.test.tsx (substantially
                                          rewritten - old element assertions
                                          replaced with new ones)
          frontend/README.md (update the Stage C3b section to note this redesign
                               supersedes the ghost-panel/network addendum)
          docs/ui-design-specification.md (note the supersession, same pattern as
                                            other recorded design decisions)
```

No backend file.

## 6. Business Rules

- The headline/tagline copy is marketing-style text, not a data claim - no
  specific numbers, percentages, or metrics may be introduced anywhere in this
  redesign. If the copy is later changed, the same rule applies to any
  replacement wording.

## 7. Accessibility Requirements

- Headline and eyebrow text: real, accessible text content (not an image or SVG
  <text> masquerading as unreadable decoration) - screen readers should encounter
  it normally as page content, not as part of the "purely decorative" background
  layer the geometric planes belong to.
- The geometric planes/grid/grain/rings remain aria-hidden/decorative, consistent
  with how the previous version's background elements were marked.
- WCAG AA contrast for the headline/eyebrow text against the art panel
  background, in both themes - measured, not assumed.
- prefers-reduced-motion fully respected, per section 4.3.

## 8. Edge Cases

- Very long headline text at narrow desktop widths (not yet mobile) - verify
  wrapping looks intentional, not awkward.
- Tablet breakpoint specifically - this is the size that previously looked sparse
  and prompted the redesign; verify it now looks genuinely resolved, not just
  different. Screenshot it explicitly, don't skip straight to mobile/desktop.
- Theme switch while on the login/register page - the art panel must re-theme
  correctly (same class of check as the Modal/AccountMenu theme-switch
  verification from earlier stages).

## 9. Tests Required

- New/rewritten AuthArtPanel tests: headline and eyebrow text render as real
  accessible content; decorative elements (planes, grid, grain, rings) are
  aria-hidden; no leftover assertions on the removed ghost-panel/network
  elements.
- Reduced-motion: all animated elements (planes, any ring motion) stop under
  prefers-reduced-motion.
- Both themes render without error (a basic smoke test per theme is sufficient
  alongside the visual verification).

## 10. Acceptance Criteria

1. npm run build clean.
2. npm test - report exact count; old ghost-panel/network tests removed, new
   ones added, no net loss of meaningful coverage.
3. npm run lint clean.
4. .venv/Scripts/python.exe manage.py test - unaffected, confirm anyway.
5. Screenshot verification, both themes, all three breakpoints (desktop, tablet,
   mobile) - six screenshots total, labeled. This is the actual acceptance bar,
   given how much this feature has gone through visual iteration already.
6. Headline text contrast ratios reported for both themes.
7. Confirm the tablet breakpoint specifically looks resolved (section 8).
8. git status - frontend + the two doc updates in section 5, nothing else.

## 11. Must NOT Do

- Do not leave any remnant of the ghost-panel or network-motif code/tokens/tests
  - full removal, not a fallback path.
- Do not touch the form side of Login/Register.
- Do not introduce any fabricated numeric claim in the headline/eyebrow copy.
- Do not skip the light-theme tuning - a flat recolor of the dark version's exact
  values will not pass the contrast bar, per precedent.
- Do not add a new animation dependency - Framer Motion only.
- Do not start C5/C6.

---

## Workflow

Produce a plan first and wait for approval before writing code. Given the scope
(full rewrite of one file, theme tokens for both modes, three breakpoints, new
tests), propose a session split if it makes sense - e.g. desktop dark-mode
structure first, then tablet/mobile + light theme + motion polish + final
screenshot verification second.

---

## Ready-to-paste prompt for Claude Code

Read docs/authpanel-redesign-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.

# Claude Code Implementation Specification — UI-03: Visual Prototype (Hard Gate)

**Scope:** produce an actually-rendered, reviewable visual prototype of the
proposed Tenora direction - the application shell, one representative
authenticated product page, and one auth screen, in both themes and both
desktop/mobile - that becomes the binding visual baseline for UI-04 onward
once you explicitly approve it. Written token values alone do not
satisfy this stage.

**Not in scope:** the formal design system/token specification (UI-04),
any other page, any production route change, any removal of currently-
shipped code (the existing shell/pages stay live and unaffected until a
later stage formally replaces them), any Settings/Account/Tenant-Settings
UI (per UI-02's D-0.2 - these pages don't exist and mostly have no backend
either; building them now would be new-feature work disguised as a
prototype).

---

## 0. Prerequisites — resolve before starting

1. Confirm docs/tenora-redesign-master-spec.md exists in the repo
   (UI-02's D-0.1 flagged it as missing - it should have been added
   since). If it's still absent, stop and report - every citation back
   to "master spec section N" in this spec and in UI-01/UI-02 depends on
   it actually being there for a future reader to verify.
2. Read docs/frontend-audit.md (UI-02) in full, not just its summary -
   this stage's page/component choices are grounded in what UI-02 found,
   not re-derived from scratch.

## 1. Objective

This stage must produce real, running, screenshot-able code - not a
static mockup, not a Visualizer-style sketch, not a description. The
reasoning is architectural, not stylistic: per the master spec, the
approved prototype becomes the literal baseline UI-04 (design system)
and every later stage build on. If UI-03 were a throwaway static image,
UI-04 would have to reimplement everything as real tokens/components
from scratch anyway - duplicating work and risking drift between "what
was approved" and "what got built." Build it as real code the first
time, so approval means "this is what we build on," not "this is what
we should aim for."

This is also the stage this whole redesign program exists to protect
against a real, already-proven failure mode. UI-02's own audit (section
18) documented AuthArtPanel's actual history: a cartoon mascot, an
isometric cube grid, ghost panels, a network motif, typography-planes,
and a reverted line-break fix - six real iterations, each one a
technically competent implementation of a reasonable-sounding written
idea that simply didn't look right until it was rendered and looked at.
Do not repeat that pattern at design-system scale. Render early, look at
it honestly, iterate before committing to UI-04.

## 2. Inspect Before Implementing

```
docs/tenora-redesign-master-spec.md    - section 8/9's exact prototype
                                          requirements; the binding-
                                          baseline rule
docs/design-reference-analysis.md sec 9 - the 11-item "must demonstrate"
                                          checklist and the explicit
                                          "must not" list - both
                                          reproduced below, but verify
                                          against the source
docs/frontend-audit.md                 - section 12 (component inventory),
                                          section 17 (existing visual system
                                          - what this prototype extends,
                                          not replaces from scratch),
                                          section 18 (AuthArtPanel history)
frontend/src/styles/theme.css          - the current token system this
                                          prototype proposes evolving,
                                          not discarding
```

## 3. Existing Functionality That Must Not Change

- Every current production route, page, and component continues working
  exactly as it does today. This prototype is additive and isolated -
  see section 4.1 for the isolation mechanism.
- All existing tests pass, unmodified.
- No dependency added (master spec section 19 - non-negotiable, and
  especially relevant here given the temptation a prototyping stage
  creates).

## 4. Required Changes

### 4.1 Isolation mechanism — investigate and propose

This prototype must be real, running code, but must not be reachable
from production navigation or affect any existing page. Propose the
cleanest mechanism (e.g. a dev-only route not linked from any nav, a
separate isolated entry point) - report which approach and why. The
constraint: someone using the real app today sees no change; someone
deliberately navigating to the prototype sees the new direction, fully
rendered, theme-togglable.

### 4.2 What must be built — exactly the master spec's minimum

- The application shell (top bar, nav, tenant switcher, account menu).
- One representative authenticated product page: Overview.
  Recommended specifically because it's read-only, has no Razorpay-
  adjacent UI (avoiding UI-02's D-0.6 provider-coupling concern
  prematurely) and no missing-backend entanglement (avoiding D-0.2) -
  it's the cleanest, most self-contained real page to prototype. If you
  find a stronger justified reason to choose differently, propose it
  and report the reasoning; don't default away from this without cause.
- One auth screen: Login, including the evolved AuthArtPanel
  composition per design-reference-analysis.md section 6.1 - a
  statically composed, fully tokenized rendering of a shipped surface
  only (subscription card, plan grid, members list, or a lifecycle
  timeline) with obviously synthetic values. Never reconciliation,
  webhooks, usage, or proration - those have no frontend surface today
  and must not appear here.

### 4.3 The 11-item demonstration checklist (from the reference analysis section 9)

The prototype must demonstrate:
1. The two type registers side by side (Overview's dense register, the
   auth page's composed register).
2. The evolved auth panel (section 4.2 above) - real components,
   synthetic values, both themes, a narrow viewport.
3. The overline/eyebrow element in at least three contexts (a page
   header, a KPI caption, a card category label).
4. The system-pulse strip on Overview's header - 2-3 items built only
   from subscription + membership data already consumed today (Plan,
   Status, Renews, Team) - no reconciliation/webhook/usage item, per
   master spec section 12/22.
5. The editorial page-header pattern, applied to the prototyped pages.
6. A dense data table with the reserved selection rail, and its
   stacked-card mobile form.
7. A KPI row with exactly one featured tile, the rest flat.
8. An empty state and an error state, written in "principle ->
   consequence" voice.
9. The sticky hairline top bar, including its mobile-collapsed state
   with the tenant switcher still visible.
10. A reduced-motion pass of every prototyped screen - proving nothing
    essential is lost with motion off.
11. Both themes, for every screen.

### 4.4 Explicit constraints — the "must not" list

The prototype must not: introduce a new color or a second accent;
change or add a font; use any motion beyond the permitted feedback set
(short color/opacity transitions, a skeleton pulse, a modal appearing);
add gradient/glow to more than one element per view; use fluid,
viewport-locked type. Any of these would be a new design decision
smuggled into a "prototype," not a demonstration of the already-analyzed
direction.

## 5. Files Likely Affected

```
new:      the isolated prototype route/entry point (section 4.1)
          any new component variants needed for the demonstrated
          patterns (overline, system-pulse strip, evolved AuthArtPanel
          composition) - built as real, reusable components, not
          one-off markup, since UI-04+ will formalize and reuse them
modified: frontend/src/styles/theme.css - only if genuinely needed for
          the prototype's proposed token candidates (report exactly
          what changed and why; this is a proposal, not yet the locked
          UI-04 system)
```

No backend file. No removal of any existing production file.

## 6. Business Rules

No fabricated data anywhere in the prototype - the evolved AuthArtPanel
composition uses obviously synthetic values specifically so it can never
be mistaken for real data (per the reference analysis section 6.1).

## 7. Security Requirements

No change - this stage touches presentation only, and is isolated from
production per section 4.1.

## 8. Edge Cases

- The evolved auth panel reading as "a calm demonstration" vs. "a broken
  app" - this is design-reference-analysis.md's own named risk (section
  10 Q1). If it reads as broken during your review, the documented
  fallback (a lifecycle timeline instead of a data-table composition)
  should be tried before iterating further on the data-table version.
- Reduced-motion pass - verify nothing essential (not just decoration)
  is lost when motion is disabled, on every prototyped screen.

## 9. Tests Required

This is a visual stage - the primary evidence is screenshots, not unit
tests. If any new reusable component is built (the overline, the
system-pulse strip), it should get the same basic test coverage this
project already requires for any new shared primitive (renders, themes
correctly, accessible). No behavioral/business-logic tests are expected
since nothing behavioral changed.

## 10. Acceptance Criteria

1. A real, running prototype reachable via the isolation mechanism
   (section 4.1), confirmed by you opening it in a browser - not just a
   description of what it would look like.
2. Screenshot evidence covering: shell (both themes), Overview (both
   themes, desktop + mobile), Login/AuthArtPanel (both themes, desktop
   + mobile) - minimum 8 screenshots, more if a specific checklist item
   (section 4.3) needs its own shot to verify.
3. Explicit confirmation, item by item, of the 11-point checklist
   (section 4.3) and the "must not" list (section 4.4) - not just
   "looks right."
4. npm run build/lint clean; no existing test broken.
5. Report: the isolation mechanism chosen and why, the page-choice
   reasoning (Overview, or your justified alternative), and any token
   values proposed as candidates (explicitly flagged as proposals, not
   yet locked - that's UI-04's job).
6. git status - confirm nothing outside the intended new/modified files.

## 11. Must NOT Do

- Do not build Settings/Account/Tenant-Settings UI (D-0.2 - out of
  scope, no existing pages or backend to redesign).
- Do not build or touch anything Razorpay/checkout-adjacent (avoids
  D-0.6's provider-coupling concern prematurely - Overview was chosen
  specifically to sidestep this).
- Do not add a new dependency.
- Do not introduce a second accent color, a new font, or motion beyond
  the permitted feedback set.
- Do not remove, replace, or affect any currently-shipped production
  route or page.
- Do not proceed to UI-04 - this stage ends at your explicit approval
  of the rendered prototype.
- Do not treat this as a formal design-system definition - token values
  proposed here are candidates, not locked.

---

## Workflow

Produce a plan first - including your proposed isolation mechanism and
confirmation of the Overview/Login page choice - and wait for approval
before building anything. Given this stage's real complexity (real
components, two pages, two themes, two breakpoints, eleven checklist
items), propose a session split if warranted, same discipline as every
sizable stage in this project.

---

## Ready-to-paste prompt for Claude Code

Read docs/ui-03-prototype-spec.md, docs/tenora-redesign-master-spec.md,
and docs/frontend-audit.md, then inspect the repository.
Produce a plan - including your proposed isolation mechanism and
confirmation of the page choices - and wait for my approval before
building anything.

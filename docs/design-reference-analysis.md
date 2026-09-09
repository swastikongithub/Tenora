# Tenora Design Reference Analysis

**Stage:** UI‑01 — Reference Synthesis (first stage of the ten‑stage Tenora UI/UX redesign
program: UI‑01 → UI‑02 audit → **UI‑03 prototype, hard gate** → UI‑04 design system →
UI‑05 shell → UI‑06 auth → UI‑07 core → UI‑08 admin/settings → UI‑09 polish → UI‑10 QA).
**Status of this document:** analysis only, reconciled to the finalised redesign master
specification (see §1.5). No frontend or backend source was changed. No design system,
tokens, components, or prototypes were produced. D1–D8 (commit `dc87ec0`) are complete and
closed; this redesign is a UI/UX phase, not D9, and touches no backend architecture,
billing logic, tenancy, auth, webhooks, metering, proration, Celery, or reconciliation.

---

## 1. Purpose and scope

### 1.1 What UI‑01 is

Two external web pages were supplied under `docs/design-references/` as design research.
This document extracts **principles, patterns, hierarchies, compositional ideas,
interaction ideas, and design‑system insights** from them and synthesises an **original,
proposed Tenora visual language** — expressed in Tenora's own terms — that can guide the
later stages of the redesign.

### 1.2 What UI‑01 is not

- Not a redesign. No page, component, route, token, config, or dependency was touched.
- Not the UI‑02 frontend audit. Section 7 records a *light* read of the current frontend
  only far enough to judge how reference patterns would land; there is no A/B/C/D
  inventory here.
- Not a visual prototype. Section 9 lists what the UI‑03 prototype must demonstrate; it
  does not build it.
- Not a token specification. UI‑04 defines the formal design system *after* the prototype
  is approved. Section 8 deliberately stops at character and principle and does not
  prescribe final values.

### 1.3 Reference‑handling constraints observed

Both references are saved "complete webpage" captures (HTML + a `_files/` asset folder).
They were treated as a **research corpus only**: local HTML and local CSS text were read
for structural and compositional understanding; no embedded script was executed, no
reference site was opened or run, no network request was made, and no CSS class name,
colour value, SVG path, image, font, logo, brand name, or proprietary copy has been
carried into Tenora or into this document. Distinctive reference copy is paraphrased,
never quoted. The final Tenora design must be original; this document is written to keep
it that way.

### 1.4 Relationship to the existing UI spec

`docs/ui-design-specification.md` (§C) was itself derived from **seven earlier visual
references** — all of them *product/dashboard* screens (a dark admin dashboard, a light
settings page, a light analytics dashboard, an invoice, a dark pricing page, an invoices
dashboard, a split login). That corpus already gave Tenora strong guidance on
**dashboard mechanics**: sidebar/navbar structure, KPI rows, dense tables with status
pills, master‑detail splits, form row composition.

The two new references are a **different genre** — polished *marketing / brand* sites for
AI companies. They contribute almost nothing new about table density or form layout.
Their value is at the **edges of the product** (the auth screens, the first impression,
the "does this feel like a serious, premium tool" judgement) and in **brand character**:
type personality, spatial confidence, restraint, motion posture, how a dark surface is
made to read as *precise* rather than *heavy*. This analysis is scoped accordingly — it
does not re‑derive the dashboard patterns the existing spec already nails.

### 1.5 Relationship to the finalised redesign master specification

This document was first drafted before the redesign master specification was finalised,
and has been reconciled to it. The master spec locks a **ten‑stage sequence**
(UI‑01 reference synthesis → UI‑02 frontend audit → **UI‑03 visual prototype, a hard
gate** → UI‑04 design system → UI‑05 shell → UI‑06 auth → UI‑07 core pages → UI‑08
admin/settings → UI‑09 responsive/interaction polish → UI‑10 final QA). This is UI‑01;
nothing here begins UI‑02, and no stage proceeds without the prior stage's explicit
approval.

Two master‑spec rules bear directly on the recommendations below and have been applied
throughout §4–§10:

- **§7 (status mapping is preserved, not reinvented):** the
  `TRIALING / ACTIVE / PAST_DUE / CANCELED` → `warning / success / danger / neutral` Badge
  mapping already proven across the app is **restyled, never remapped**. Recommendations
  that touch status treat this as fixed.
- **§12 / §22 (no new frontend surface for backend‑only capabilities):** usage metering
  (D5), proration audit records (D6), and reconciliation discrepancies (D8) — and, as an
  internal‑only mechanism, webhook processing state (D1–D4) — have **no tenant‑facing
  frontend surface today and none is built in this phase.** Any recommendation below that
  could tempt such a surface is explicitly bounded to data the tenant frontend *already*
  consumes (`/subscriptions/current/`, `/memberships/`, `/tenants/me/`, `/users/me/`) and
  flags the richer version as a candidate for a **later, separate product‑expansion
  phase**, never this redesign.

---

## 2. Reference corpus

Two references. Neutral handles are used below; both are public marketing pages for
venture‑backed AI companies, captured mid‑2026.

### 2.1 Reference A — "AI‑builder product site"

*(a design/website‑builder company's marketing site for its AI agent product; the site
is itself built on that company's platform.)*

**Visual character.** Confident, dark, engineered. Near‑black page ground with a small
family of near‑black surface planes stacked on it, separated almost entirely by
**1px light hairline borders** (low‑alpha white) rather than by shadow. One cool brand
accent, plus a green and a blue used strictly for semantic/status meaning. A neutral
grotesk for body text and a slightly more characterful grotesk for large display text.
**Monospace is a deliberate texture**, not a fallback — terminal panels, code snippets,
CLI transcripts and technical identifiers are all set in mono and treated as a first‑class
part of the visual language. The type scale is **tight and closed**: roughly a dozen
steps from ~11px to ~54px with no dramatic jumps, tight negative tracking on the largest
sizes, slight positive tracking on the smallest all‑caps labels. Corners are **medium‑soft**
(cards noticeably rounded, small controls near‑pill). Motion is **fast and small** —
sub‑300ms colour/opacity transitions on an ease‑in‑out curve; nothing scroll‑driven that
was observable in the static capture.

**Strongest ideas.**

1. **"Show the product doing the work."** The hero and section visuals are not abstract
   art — they are *carefully composed, non‑interactive slices of real‑looking product UI*:
   a content table mid‑edit, a CLI transcript importing data, a canvas laying out layout
   variations. The message is "this tool is real and it is working," communicated by
   showing the tool, calmly, rather than by decoration.
2. **Live confidence signals rendered plainly.** Real metrics (a web‑vitals readout: a
   status word plus three labelled millisecond/score figures; a "#N this week, N‑billion
   units" ticker) are shown as **label + tabular figure + status word**, with no chart
   chrome. Small, quiet, and more persuasive than a testimonial.
3. **Hairline‑border surface discipline.** Depth is created by *light* — a hairline and a
   hair of elevation — not by heavy drop shadows. This is what makes the dark UI read as
   "instrument," not "night mode."
4. **Semantic colour scarcity.** Exactly one brand accent; green/blue/red appear *only*
   where they carry state. Colour is rationed, so where it appears it means something.
5. **Monospace as intentional voice‑of‑the‑machine.** Not just `<code>` — a whole
   register for technical content.
6. **A quiet, thin, sticky top bar** (wordmark left, primary nav centre‑left, actions
   right) with only a hairline bottom border — the chrome recedes and the content is the
   product.

**Weaknesses / cautions.**

- The marketing feature grid runs to nine‑plus equal‑weight tiles (Performance, CMS, SEO,
  Collaboration, Localization, Hosting, Security, Analytics, A/B testing…). As a *layout
  idea for app content* this is a wall of undifferentiated cards — the opposite of a KPI
  row that says "look here first."
- Heavy marketing chrome around the useful parts: logo walls, "trusted by" strips,
  showcase carousels, an app‑download push. None of it is relevant to Tenora, which *is*
  the product and has no marketing surface in scope.
- The characterful display face and the medium‑soft radius push slightly toward "friendly
  startup." Tenora's direction is cooler and more exact than that.

**Useful lessons for Tenora.**

- Validate and *keep* the near‑black + hairline‑border surface language Tenora already
  uses; it scales.
- Replace Tenora's current abstract auth artwork with a **product‑truthful** composition
  (see §6.1).
- Add a **"system pulse"** confidence motif to Tenora built from label + tabular figure +
  status word (see §6.2).
- Lean *into* Geist Mono as a register for identifiers, timestamps, event names and
  payloads — not as an afterthought.
- Keep KPI rows to 3–4 meaningful tiles with exactly one emphasised; never a feature wall.

### 2.2 Reference B — "autonomous‑enterprise brand site"

*(an enterprise‑AI consultancy's brand site; built on a hosted site builder, with a
smooth‑scroll library, a WebGL hero, and page‑transition effects.)*

**Visual character.** Editorial and cinematic. Very dark ground (near‑pure‑black), but a
**warm** accent palette — a magenta, a pale lime, a cream/beige. Hierarchy is carried
almost entirely by **size, letter‑spacing and colour, not weight** — body and display are
essentially the same single weight; the largest headlines use tight negative tracking,
and small labels are **uppercase with very wide letter‑spacing** ("eyebrows" / section
kickers). Type is **fluid and viewport‑proportional** — sizes are computed as a fraction
of viewport width locked to specific design widths (390 / 768 / 1440). Corners are mostly
**sharp** (small radius or none), with occasional pills. Layout gives a **single strong
idea a full screen of breathing room** — a pull‑quote with attribution, one sentence per
section, generous vertical rhythm. There is a heavy **motion investment**: smooth‑scroll
hijacking, a 3D hero, scroll‑triggered reveals, marquee lists, and full‑page "wipe"
transitions between routes.

**Strongest ideas.**

1. **Hierarchy without weight.** Proving that size + tracking + colour alone can carry a
   clear hierarchy is a useful discipline — it argues against reaching for 700/800 weights
   to shout.
2. **The eyebrow / overline as a recurring system element.** A short, wide‑tracked,
   uppercase micro‑label above a heading, used consistently, becomes a quiet signature.
3. **Editorial section rhythm.** One clear sentence, real space around it, then the
   content. Sections feel *composed* rather than stacked.
4. **"Anti‑pattern list" content shape.** A scannable list of *short principle → one‑line
   consequence* ("do X, because otherwise Y"). A genuinely good pattern for explaining
   states, risks and trade‑offs in plain language.
5. **Numbered primitives.** Naming the parts of a system `01 / 02 / 03` gives a multi‑part
   concept a spine.

**Weaknesses / cautions.**

- The **motion stack is disqualifying** for Tenora: smooth‑scroll hijacking, WebGL,
  scroll reveals, marquees and page wipes are exactly the "non‑essential motion" Tenora's
  spec forbids, and they fight the operator's expectation that a data tool sits still.
- **Fluid viewport‑locked type** ignores the user's font‑size and zoom settings and breaks
  at viewport extremes. It is an accessibility regression relative to Tenora's rem‑based
  scale.
- The **single‑weight extreme** removes weight as a hierarchy tool, which a dense data UI
  needs (table headers, active nav, labels).
- The **warm palette** (magenta / lime / cream) is the wrong temperature for "quiet
  premium tech," and a lime would collide perceptually with a success‑green.
- The capture contains unfinished artefacts (placeholder "lorem ipsum" body copy, leftover
  build comments). A reminder that these are a research corpus, not a quality bar.

**Useful lessons for Tenora.**

- Adopt the **eyebrow/overline** as a real, reusable Tenora element.
- Give Tenora **page headers editorial breathing room** — an overline, a one‑sentence
  title, real space before content — instead of the current terse header.
- Use the **principle → consequence** shape for Tenora's status explanations, empty
  states, and error copy (Tenora already does a light version of this on Overview).
- Consider a **numbered‑step** language for Tenora's multi‑step flows (checkout, plan
  change, cancellation).
- Take the *restraint* in weight range (cap at 600), reject the monotone.

---

## 3. Cross‑reference pattern synthesis

Where the two references **agree**, the signal is strong. Where they **conflict**, the
conflict itself is informative for Tenora's direction.

### Typography

- **Agreement:** both use a **neutral grotesk** as the workhorse and both keep the
  **weight range narrow** (A: ~400–600; B: effectively one weight). Neither uses a serif
  for UI. Both track the **largest display sizes tighter** (negative letter‑spacing) and
  the **smallest labels looser** (positive tracking, often uppercase).
- **Agreement:** both treat a **small uppercase wide‑tracked label** ("eyebrow") as a
  distinct type role, separate from headings and body.
- **Conflict:** **scale mechanism.** A uses a fixed, rem‑like step scale; B uses fluid
  viewport‑proportional sizing. → Tenora keeps **rem‑based steps** (accessibility), and
  takes from B only the *idea* of a more expressive top end, not the technique.
- **Conflict:** **hierarchy tool.** A leans on size *and* weight; B on size *and* tracking
  *and* colour. → Tenora keeps weight as a tool (it needs it in tables and nav) but should
  lean harder on **size, tracking and colour** for the calmer, edge surfaces.
- **A‑only, worth taking:** **monospace as a register**, not a one‑off.

### Layout

- **Agreement:** **one primary column**, left‑aligned, with a comfortable max width;
  content is not stretched to the full viewport.
- **Agreement:** a **sticky, thin top bar** with wordmark‑left / nav / actions‑right.
- **Agreement:** **generous vertical rhythm between sections** — sections are composed
  units with air around them, not a continuous scroll of stacked blocks.
- **Conflict:** **density.** A's *feature grid* is a dense wall; B's *content* is almost
  luxuriously sparse. → Tenora's answer is **two densities in one system**: dense *inside*
  a working surface (tables, KPI detail), sparse *around* it (page headers, empty states,
  auth). The contrast between the two is a deliberate premium signal, not an
  inconsistency.

### Color

- **Agreement:** **very dark ground**; a small number of surface planes on it.
- **Agreement:** **one identity accent** carries brand + interaction.
- **Conflict:** **temperature.** A is cool (matches Tenora); B is warm. → Tenora stays
  **cool** — near‑black with a blue‑violet cast, single cool‑purple accent.
- **A‑only, worth taking:** **strict semantic separation** — green/blue/red appear *only*
  as state, never as decoration. Tenora already does this; the reference confirms it as
  correct rather than cautious.

### Surfaces

- **Agreement:** **depth from light, not shadow.** Both separate planes with a hairline
  and at most a hair of elevation. Heavy drop shadows are absent from both dark designs.
- **Agreement:** **flat by default.** Neither applies gradient or glow to ordinary
  containers; emphasis treatments are reserved for a hero element.
- **Divergence in degree:** A (a product marketing page) uses gradient/glow more freely on
  its *marketing* hero than Tenora should ever use in‑app. → Tenora holds its existing
  rule (emphasis is opt‑in, one per view) and does **not** read the reference as licence
  to loosen it.

### Navigation

- **Agreement:** **horizontal top navigation**, sticky, hairline‑bottom‑bordered, chrome
  kept minimal so the page reads as "the product," not "an app frame."
- **Agreement:** primary account/identity controls sit at the **right end**, visually
  separated from the primary nav.
- **Neither reference has a tenant switcher** (neither is multi‑tenant) — Tenora's
  requirement to keep the switcher *always visible and never folded into the account menu*
  is Tenora‑specific and correct; the references don't challenge it.
- **Active state:** A shows a clearly distinct, multi‑signal active nav item (background +
  colour). → Tenora's existing active treatment (accent‑subtle background + weight + glow)
  is consistent with this and should stay multi‑signal, never colour‑only.

### Components

- **Buttons:** both keep **one confident primary** and everything else quiet. Small
  controls trend toward pill‑ish in A, rectangular in B. → Tenora stays with its calm
  rounded‑rectangle button and single primary.
- **Cards:** flat frames in both; A rounds them more. → Tenora keeps its flat frame; the
  radius question is minor and deferred.
- **Tables:** neither reference has a genuine dense operational data table — this is where
  Tenora's *original* seven‑reference corpus remains the authority. The new references add
  nothing here and must not be over‑applied to tables.
- **Badges / status:** A pairs a status word with its colour every time. → Confirms
  Tenora's rule that a badge without a text label is a defect.
- **Loading:** neither shows much; A's product mockups imply structural placeholders. →
  Tenora keeps skeletons that match the real layout, not spinners‑everywhere.
- **Empty states / feedback:** B's "principle → consequence" list shape is the transferable
  idea — explain the state, then one plain line of what it means.
- **Dialogs / menus / tabs:** nothing in the references improves on what Tenora already
  has.

### Motion

- **Conflict, and it is the sharpest one.** A: fast, tiny, feedback‑only, nothing
  scroll‑driven. B: heavy — smooth‑scroll hijack, WebGL, scroll reveals, marquees, page
  wipes.
- → Tenora sits firmly at **A's end and further**: motion is *feedback only* (hover/focus
  colour change, skeleton pulse, a modal appearing), everything is disabled — not slowed —
  under `prefers-reduced-motion`, and there is **no scroll‑driven motion of any kind**.
  For a billing engine, stillness under the operator's hands *is* the premium signal. B is
  a worked example of what to reject.

### Responsive behaviour

- **A (rem‑like steps):** degrades predictably; the user's zoom and font size are
  respected.
- **B (viewport‑locked fluid type):** visually tuned per breakpoint but brittle at
  extremes and indifferent to user text settings.
- → Tenora keeps **rem‑based, user‑setting‑respecting** sizing. Reference‑agnostic rules
  Tenora already has and should keep: tables become **stacked cards** below the tablet
  breakpoint (never horizontal scroll); the auth **split becomes a short banner + form**;
  nav **collapses to a panel** while the tenant switcher and account control stay put;
  nothing is *hidden*, everything *reflows*.

### Accessibility

- **A:** semantic status words always accompany status colour; nav active state is
  multi‑signal; motion is minimal by default.
- **B:** the warm‑on‑black combinations and the wide‑tracked tiny uppercase labels are a
  contrast/legibility risk; fluid type fights user font settings; the motion stack is
  hostile to vestibular sensitivity and has an inconsistent reduced‑motion story.
- → The references *reinforce* the parts of Tenora's accessibility posture that are already
  ahead (every token pair WCAG‑measured; status never colour‑alone; a visible 2px
  offset focus ring; `prefers-reduced-motion` honoured globally) and provide, in B, a
  clear catalogue of what **not** to do. The redesign must not regress any of it.

---

## 4. Patterns Tenora SHOULD adopt

Each with the reference it comes from and *why it strengthens Tenora specifically*.

1. **Product‑truthful visuals instead of abstract artwork (from A).**
   *Why:* Tenora's current auth panel is generative geometry (layered translucent
   planes, a grid, grain). It is well‑built but says nothing about what Tenora *is*.
   Reference A's approach — a calm, non‑interactive slice of the real product — is more
   honest, more distinctive, and more on‑theme for "quiet premium *tech*." The composed
   surface must depict a **shipped, tenant‑facing frontend surface** (a subscription
   card, a plan grid, a members list, an Overview tile) with obviously synthetic values —
   never a concept that has no UI today (reconciliation, webhooks, usage, proration), so
   it can't imply a feature that doesn't exist (master spec §12/§13). See §6.1 for the
   transformation into an original pattern.

2. **A "system pulse" confidence motif (from A's live‑metric chips), scoped to existing
   data.**
   *Why:* Tenora's engineering thesis is honesty about state; a recurring, quiet strip of
   *overline label + tabular figure + status word* expresses that. **But the master spec
   (§12/§22) forbids a new frontend surface for backend‑only capabilities**, so the strip
   is built strictly from data the tenant frontend already consumes — subscription status,
   `current_period_end` ("renews in 12 days"), plan, member count. The richer version
   (reconciliation freshness, webhook backlog, last‑charge time) is a **candidate for a
   later product‑expansion phase, explicitly out of scope here** and needs new backend
   endpoints that don't exist. See §6.2 for the bounded pattern.

3. **A real, reusable eyebrow/overline element (from B, and already latent in Tenora).**
   *Why:* Tenora's auth panel already has exactly one hand‑rolled instance
   (small, uppercase, wide‑tracked, accent‑coloured). Promoting it to a named element and
   using it consistently — section headers, KPI captions, card category labels — gives
   Tenora a cheap, quiet signature that reads as "considered."

4. **Editorial breathing room on page headers (from B).**
   *Why:* Tenora pages currently open with a terse `h1` + one muted line, then straight
   into content. Giving the header an overline + a one‑sentence title + real vertical
   space before the content costs nothing, calms every page, and sets up the
   dense‑inside / sparse‑around contrast that is the core of the proposed character.

5. **"Principle → consequence" copy shape for states and help (from B).**
   *Why:* Tenora already does a light version (`STATUS_EXPLANATION` on Overview: a status,
   then one plain line of what it means). Deepening this across empty states, error
   alerts, and confirmation modals makes the product feel like it is *explaining itself*
   rather than *reporting errors* — a premium, trustworthy tone for a tool that moves
   money.

6. **Monospace as a deliberate register, not a fallback (from A).**
   *Why:* Tenora has Geist Mono wired up and already uses it for the tenant slug and for
   IDs/JSON in dev tooling. The reference argues for treating every machine‑generated
   string that *legitimately appears in the tenant UI* — the slug, an ID or external
   reference where one is genuinely shown, a technical timestamp — as *intentionally*
   monospaced and tabular, a consistent voice‑of‑the‑machine. This is a treatment rule for
   strings that already surface, **not** a licence to surface new backend identifiers
   (webhook/reconciliation/idempotency data has no tenant UI — §12/§22). It reinforces the
   "instrument" character and makes technical data scannable.

7. **Keep the thin, hairline‑bordered, chrome‑minimal sticky top bar (from both).**
   *Why:* Tenora's `TopNavbar` already matches this. Both references confirm the pattern;
   the only open refinement is whether to lighten the bar's background toward the page
   ground (§10, Q2).

8. **Depth from light, flat by default (from both).**
   *Why:* Confirms Tenora's existing three‑plane + hairline‑border system and its rule
   that gradient/glow is opt‑in emphasis, not a default. The redesign should *not* add
   ambient shadow or gradient to ordinary surfaces.

9. **Semantic colour scarcity (from A).**
   *Why:* Confirms Tenora's single‑accent + four‑semantic‑colour discipline. The
   actionable form of "adopt": **do not introduce a second brand colour** during the
   redesign, however tempting a "secondary accent" feels.

10. **One larger display step for the product's edges (from A's closed‑but‑expressive
    scale).**
    *Why:* Tenora's in‑app scale correctly tops out around 32px — right for a dashboard.
    The auth screen, marketing‑adjacent surfaces, and major empty states could carry one
    more confident step (see §10, Q3 for the value question) without disturbing the dense
    in‑app scale. Two registers, one system.

---

## 5. Patterns Tenora SHOULD reject

Each with the reference and *why it is wrong for Tenora*.

1. **The full motion stack — smooth‑scroll hijacking, WebGL hero, scroll‑reveal
   animations, marquees, page‑transition wipes (from B).**
   *Why:* Tenora's spec mandates `prefers-reduced-motion`‑first and "no non‑essential
   motion." An operator reconciling a billing discrepancy needs the page to hold still and
   respond instantly. Every item on this list adds latency, jank risk, and vestibular
   load, and none of it communicates anything a billing operator needs. This is the single
   clearest "do not" in the corpus.

2. **Fluid, viewport‑proportional type (`calc(vw × n / design-width)`) (from B).**
   *Why:* It ignores the user's browser font‑size and zoom settings — an accessibility
   regression — and it breaks at viewport extremes. Tenora's rem‑based step scale is an
   accessibility asset and must stay.

3. **Hierarchy on a single font weight (from B).**
   *Why:* A dense data UI needs weight as a distinguishing tool for table headers, active
   nav, and field labels. Take B's *restraint* (cap at ~600, never 700/800) but not its
   monotone.

4. **The warm accent palette — magenta, lime, cream (from B).**
   *Why:* Wrong temperature for "quiet premium tech," which reads cooler and more exact. A
   lime would also be perceptually confusable with a success‑green in a status context,
   weakening the semantic system.

5. **Marketing chrome — logo walls, "trusted by" strips, testimonial rows, app‑download
   pushes, cookie‑consent theatre (from both).**
   *Why:* Tenora *is* the product. It has no marketing site in scope and no external
   audience to persuade on a landing page. These patterns are noise here.

6. **The many‑tile equal‑weight feature grid as an app layout (from A).**
   *Why:* Nine‑plus undifferentiated cards is the opposite of "look here first." Tenora's
   KPI rows must stay at 3–4 meaningful tiles with exactly one emphasised.

7. **Reading A's marketing hero as licence for gradient/glow on ordinary surfaces (from
   A).**
   *Why:* Tenora already litigated this (spec §C.1a): emphasis treatment is opt‑in and
   one‑per‑view. A marketing page's freedom with gradient is not a dashboard's. Ordinary
   cards, tables and rows stay flat.

8. **Medium‑soft "friendly startup" radius and a characterful display face (from A).**
   *Why:* Tenora's direction is cooler and more precise than "approachable." Keep the
   existing modest radius scale and the neutral Geist family; do not warm the geometry.

9. **Treating the references as a quality bar (from B's placeholder copy and leftover
   build comments).**
   *Why:* They are a research corpus. Tenora's own execution standard (measured contrast,
   tested components, honest copy) is higher than what shipped on at least one of these
   pages.

10. **Reading A's "show the product working" as a reason to surface *more* of the engine
    (both references' instinct to put the impressive internals on screen).**
    *Why:* Reference A can show any part of its product because all of it has a UI. Tenora
    cannot: reconciliation, webhook processing, usage metering and proration are
    **backend‑only** and master spec §12/§22 forbids building frontend for them in this
    phase. Every "show the product" idea below is bounded to surfaces that already ship;
    the richer versions are logged for a later product‑expansion phase, not smuggled in as
    decoration or a "pulse."

---

## 6. Patterns that should be adapted rather than copied

Three patterns are worth taking but only after transformation into something that is
Tenora's own.

### 6.1 "Show the product working" → **the redacted‑surface auth panel**

**What the reference does:** Reference A puts a composed, non‑interactive slice of its own
real product UI where a marketing site would normally put a photo or an illustration.

**Why copying it directly is wrong:** A screenshot of Tenora's dashboard would (a) age
instantly, (b) risk implying data or features that aren't there, (c) be indistinguishable
from a broken/blank screen if it renders wrong, and (d) not survive the light theme or a
narrow viewport.

**The Tenora transformation:** the auth panel becomes a **statically composed, fully
tokenised, non‑interactive rendering of a surface Tenora already ships** — a subscription
card with its status badge, a two‑ or three‑plan grid, a short members list, or an
Overview KPI tile — or a **subscription lifecycle timeline** (created → activated →
charged → renews), whose states are all real `Subscription.Status` transitions the app
already shows. It must **not** depict reconciliation ledgers, webhook event streams,
usage meters, or proration records: those have no frontend surface today, so showing them
on the product's front door would imply a feature that doesn't exist (master spec
§12/§13). It is built from the *actual* design‑system components and tokens (so it themes
and reflows for free), uses **obviously synthetic placeholder values** (round numbers,
`tenant_demo`, dashes where an ID would be) so it can never be mistaken for real data, and
carries the eyebrow + one‑sentence headline over it. It says "this is what Tenora does,
and it does it calmly" without a single line of marketing puffery. Original because the
subject is *Tenora's own shipped surfaces*, not a generic canvas.

### 6.2 Live metric chips → the **"system pulse" strip**

**What the reference does:** shows real performance numbers as bare `label + figure +
status word`, no chart.

**The Tenora transformation:** a horizontal strip of 2–3 **pulse items**, each a stacked
*overline label* + *tabular value* + a small *status dot with a word* (never a dot alone —
§C.8). **Scope is bounded by master spec §12/§22 — the items are drawn only from data the
tenant frontend already consumes:** `Plan · Pro`, `Status · Active`, `Renews · in 12
days` (from `/subscriptions/current/`), `Team · 4 members` (from `/memberships/`). This
is a *recomposition* of data Overview already shows, not a new surface. It appears in the
Overview page header, sits below the editorial header block, is **not a KPI row** (no big
numbers, no featured card) and **not a chart** — it is a quiet instrument reading.

**Explicitly out of scope for this redesign:** a richer pulse that surfaces
reconciliation freshness, webhook backlog, last‑charge time, usage figures, or proration
history. Those are backend‑only capabilities with no tenant endpoint today; building UI
for them is exactly what §12/§22 forbid. Logged as a candidate for a **later, separate
product‑expansion phase** (which would also need new backend contracts). Original because
even the bounded version expresses *Tenora's own honesty framing* as a recurring element.

### 6.3 Editorial section rhythm + eyebrow → the **Tenora page‑header pattern**

**What the references do:** B gives one idea a screen of room with an overline above it; A
keeps section headers terse but distinct.

**The Tenora transformation:** a single documented **page‑header block** used on every
in‑app page: `overline` (uppercase, wide‑tracked, the page's domain area, e.g.
"BILLING") → `h1` (one plain sentence, e.g. "Subscription & plan") → optional one‑line
`lede` in secondary text → a fixed, generous space before content begins. This is *less*
sparse than B (a dashboard can't spend a full screen on a header) but *more* composed than
Tenora's current terse header. It is the mechanism that creates the
dense‑content / calm‑frame contrast the proposed character depends on.

---

## 7. Existing Tenora identity assessment

A light read of the current frontend (`frontend/src/styles/theme.css`, the component
primitives, `TopNavbar`, `AuthArtPanel`, and a representative page). **This is not the
UI‑02 audit** — it is only deep enough to judge how the reference patterns would land.

### 7.1 What the current identity already is

- **Dark‑first, cool near‑black.** Three surface planes (page / raised / overlay) plus two
  border weights (subtle hairline / strong), all cool‑toned. A full **light theme** ships
  in parallel with **every token pair contrast‑measured** against WCAG.
- **One cool purple accent** (base + hover + a 12%‑alpha subtle tint) for identity,
  interaction, active nav, and focus rings. A strict **four‑colour semantic set**
  (success / warning / danger / neutral) that only ever appears as status and is always
  paired with a text label (the `Badge` primitive literally throws if given no label).
- **Geist Sans + Geist Mono**, both bundled locally (no font CDN at runtime). A
  **compact type scale**: display 32 / h1 24 / h2 18 / body 14 / label 13 / caption 12,
  mono 13 — genuinely dense, weight range 400–600 only.
- **4px spacing base**; radius scale 6 / 10 / 16; restrained shadows plus one opt‑in
  accent glow.
- **`prefers-reduced-motion` honoured globally** (a global rule near‑zeroes all
  animation/transition durations); the only standing motion is short colour transitions,
  a skeleton pulse, and a modal appearing. `AuthArtPanel` is the one place with ambient
  motion and it is *fully disabled* — not slowed — under reduced‑motion.
- A **sticky, hairline‑bordered, chrome‑minimal top bar**: wordmark → primary nav →
  tenant switcher (always visible) → account menu; nav collapses to a panel below 1024px
  while the switcher and account stay put.
- Strong functional patterns: per‑tile query‑failure isolation, structural skeletons,
  tables that become stacked cards on mobile, `text-muted` explicitly barred from
  content a user must read, tabular figures for all money/counts/IDs.
- A **token architecture** where `theme.css` is the single place raw values may appear and
  every component consumes them through utilities.

### 7.2 What should remain (do not re‑litigate)

- Dark‑first **and** a shipped light theme.
- The **cool near‑black** surface family and the **hairline‑border** discipline.
- The **single purple accent** and the **strict semantic status set**, always label‑paired.
- **The status‑to‑variant mapping is fixed (master spec §7):**
  `TRIALING → warning`, `ACTIVE → success`, `PAST_DUE → danger`, `CANCELED → neutral`,
  and the `Badge`‑throws‑without‑a‑label contract. The redesign **restyles the Badge, it
  does not remap it** — and every place that currently duplicates this map
  (`SubscriptionPage`, `OverviewPage`) keeps the same values.
- **Geist Sans + Geist Mono**, bundled locally.
- The **4px spacing base** and the **compact in‑app type scale**.
- **`prefers-reduced-motion`‑first, near‑zero motion.**
- **Every token pair contrast‑measured**; the `text-muted` usage rule; tabular figures.
- The **`theme.css` single‑source token architecture** and thin, spec‑driven components.
- The **sticky minimal top bar** and the **always‑visible tenant switcher**.
- The **previously rejected "gradient/glow on every surface" direction stays rejected** —
  the new references do not justify reopening it.

### 7.3 What should evolve

- **`AuthArtPanel`:** from abstract generative geometry → a **product‑truthful composed
  surface** (§6.1). The strongest single opportunity in the corpus.
- **Page headers:** from terse `h1` + muted line → the **editorial header pattern** with a
  reusable **overline** element (§6.3).
- **A "system pulse" motif:** new, small, recurring — a *recomposition* of subscription
  and membership data Overview already shows, **not** a new surface for reconciliation /
  webhook / usage / proration state (master spec §12/§22). See §6.2 for the bound.
- **Type registers:** keep the dense in‑app scale; add **one larger display step** for the
  product's edges (auth, major empty states) — value TBD (§10, Q3).
- **Monospace:** from "used for IDs and JSON" → a **deliberate register** for all
  machine‑generated strings and technical timestamps.
- **Top bar background:** consider moving from the raised plane toward the page ground +
  hairline, for a less "boxed" frame (§10, Q2).
- **Confirmation / empty / error copy:** deepen the existing "state + one plain line"
  toward a consistent **principle → consequence** voice across the app.

### 7.4 How this is an evolution, not a replacement

Every "evolve" item above is **additive or a swap within the existing token system**: the
palette, the fonts, the spacing base, the motion posture, the accessibility bar, and the
component contracts are all unchanged. The redesign changes *what the product shows of
itself* (a real surface instead of abstract art; a pulse strip; roomier headers) and
*how confidently it composes the calm frame around dense content* — not the underlying
material. A user who knows today's Tenora should recognise the evolved Tenora immediately
and read it as "the same tool, more sure of itself."

---

## 8. Proposed Tenora visual language

**This is the core deliverable.** It defines the intended character in Tenora's own terms.
It deliberately does **not** prescribe final token values — UI‑04 does that, after the
UI‑03 prototype is approved.

### 8.1 One‑line direction

**Tenora is an instrument, not a brochure.** It should feel like a precisely machined tool
that happens to be beautiful — the confidence comes from exactness, restraint, and the
fact that every number on screen is real and every state is stated honestly.

### 8.2 Overall visual character

- **Quiet.** The UI never raises its voice. Emphasis is a rationed resource — one
  featured element per view, one primary action, colour only where it means something.
  Nothing is decorative by default.
- **Premium.** Premium here is *precision*, not ornament: impeccable alignment, honest
  typesetting, tabular numbers, hairline borders that are actually 1px, a dark surface
  that reads as depth rather than weight.
- **Tech.** The product does not hide that it is a billing *engine*. Where a
  machine‑generated identifier or a technical timestamp *does* appear, it is shown plainly
  and set in monospace — not buried, not dressed up. (This is a treatment rule, not a
  mandate to surface more backend internals — §12/§22 hold.)
- **Honest.** Within what the tenant frontend already exposes, the design states the real
  situation — a subscription that is `PAST_DUE`, a period that has ended, a 404 that means
  "no subscription yet" — rather than papering over it. This is the visual expression of
  the project's engineering thesis, applied to the surfaces that exist.

### 8.3 Typography personality

- **Family:** Geist Sans (workhorse) + Geist Mono (voice of the machine). Unchanged.
- **Two registers, one scale:**
  - **Utility register (in‑app):** dense, information‑first. Small body, tight line rhythm,
    weight (up to ~600) doing real hierarchy work in tables, nav and labels.
  - **Composed register (product edges):** auth, major empty states, page headers — one
    larger display step, tighter display tracking, more air, hierarchy carried more by
    size/tracking/colour than by weight.
- **The eyebrow/overline is a first‑class role:** short, uppercase, wide‑tracked,
  secondary or accent colour; sits above headings and labels KPI captions and card
  categories.
- **Monospace is a register, not an exception:** every ID, key, external reference, event
  name and technical timestamp, always tabular.
- **Weight ceiling:** ~600. Never 700/800. Shouting is done with size and space, not
  weight.

### 8.4 Spatial rhythm

- **4px base, unchanged.**
- **Inside a working surface:** tight — small gaps between related rows, moderate padding,
  section breaks that are felt but not large.
- **Around a working surface:** generous — real space between the page header and the
  content, between major sections, around the auth composition.
- **The contrast between the two is the premium signal.** A calm, spacious frame around
  dense, exact content is the whole idea.

### 8.5 Layout philosophy

- **One primary column**, left‑aligned, comfortable max width (roughly 1024–1150px for
  content‑heavy pages).
- **Content‑out, not chrome‑in:** the top bar is a hairline, the page *is* the product.
- **KPI rows:** 3–4 meaningful tiles, exactly one emphasised, never a wall.
- **Master‑detail and dense tables** remain governed by the existing seven‑reference
  dashboard guidance — the new references do not change them.

### 8.6 Surface philosophy

- **Three near‑black planes** (page / raised / overlay), separated by **light** — hairline
  borders plus at most a hair of elevation. **No heavy shadow.**
- **Flat by default.** Gradient and glow are an **opt‑in emphasis treatment**, reserved for
  a single genuinely‑primary or interactive element per view.
- **Elevation is structural, not atmospheric** — it separates layers, it doesn't add mood.

### 8.7 Color philosophy

- **One cool identity accent** (the existing purple) for brand + interaction + focus +
  active nav.
- **A strict four‑colour semantic set** (success / warning / danger / neutral) that
  appears **only** to convey state and **always** with a text label.
- **No second brand colour. No warm tints.** Colour is scarce so that where it appears it
  carries meaning.
- Light theme keeps every pair contrast‑measured.

### 8.8 Component personality

- **Buttons:** calm rounded rectangles; one confident primary per context; everything else
  quiet (bordered/ghost). A single spinner style for loading, width‑stable.
- **Cards:** flat frames. One optional `featured` treatment (tinted gradient + glow),
  used at most once per page.
- **Tables:** dense, tabular, with a reserved 2px selection rail so selecting a row never
  shifts layout. Stacked cards below the tablet breakpoint.
- **Badges:** never stand alone; always a word + a colour.
- **Inputs:** quiet, single hairline boundary, 2px offset focus ring, helper text in
  readable secondary (never the muted token).
- **Loading:** structural skeletons that match the real layout.
- **Empty & error states:** explain, don't apologise — state the thing, then one plain
  line of what it means and what to do.
- **The overline and the system‑pulse item** are new shared elements with the same
  discipline as the above.

### 8.9 Navigation philosophy

- **One sticky, hairline top bar.** Wordmark → primary nav → tenant switcher (always
  visible) → account menu.
- **Active nav item is multi‑signal:** accent‑subtle background + weight + a soft glow —
  never colour alone.
- **Mobile:** primary nav collapses into a panel; the tenant switcher and the account
  control never move into it.
- **The chrome recedes;** the bar should feel like an edge, not a container.

### 8.10 Information density

- **High in‑app, calm at the edges.** A billing engine's operators want to see everything
  at once; density is a feature. The design *earns* the right to be dense by being
  impeccably aligned, typeset and tabulated.
- **The edges** (auth, onboarding, empty states, page headers) are deliberately spacious —
  that's where the "premium" reads.

### 8.11 Motion philosophy

- **Near‑zero. Motion is feedback, never entertainment.** Permitted: a ~150ms colour/opacity
  transition on hover/focus, a skeleton pulse, a modal appearing/dismissing, a disclosure
  opening.
- **Forbidden:** scroll‑driven animation of any kind, parallax, reveal‑on‑scroll, marquees,
  smooth‑scroll hijacking, WebGL, page‑transition effects.
- **`prefers-reduced-motion` disables even the permitted set** (it doesn't slow it).
- **Stillness is the premium signal** — the UI is stable under the operator's hands.

### 8.12 Responsive philosophy

- **rem‑based, respects the user's font size and browser zoom.** No viewport‑locked type.
- **Desktop:** multi‑column, dense.
- **Tablet:** columns fold; density holds.
- **Mobile:** single column; tables become **stacked cards** (never horizontal scroll);
  the auth split becomes a **short banner + form**; nav collapses.
- **Nothing is hidden; everything reflows.** A control that matters on desktop still
  matters on mobile — it moves, it doesn't disappear.

### 8.13 Accessibility philosophy

- **Non‑negotiable, and already ahead — the redesign must not regress it.**
- Every token pair contrast‑measured; the `text-muted` "decorative only" rule holds.
- **Status is never colour‑alone.**
- **A visible 2px offset focus ring** on every interactive element.
- **`prefers-reduced-motion` honoured globally.**
- Semantic HTML; decorative layers `aria-hidden`; real content (eyebrows, headlines on the
  auth panel) kept in the accessibility tree.
- **New elements** (overline, system‑pulse, product‑truthful auth panel) inherit the same
  bar from day one — the pulse dot needs its word, the composed surface's decorative parts
  are hidden and its text is not, the larger display step is checked against the same
  ratios.

---

## 9. Implications for the UI‑03 visual prototype

UI‑03 is the **hard gate** of the whole program (master spec §8): the redesign has
already shown that a good written brief alone can produce a poor visual result for
open‑ended aesthetic work (two earlier `AuthArtPanel` directions were rejected only after
being rendered). The prototype must be an **actually‑rendered** artefact — the shell, one
authenticated product page, and one auth screen, in desktop and mobile, light and dark —
and, once signed off, **the approved prototype becomes the binding visual baseline** for
UI‑04 onward: later stages refine details within it but may not materially change the
approved visual language, composition, typography, or interaction direction without
explicit approval.

The UI‑03 prototype (a separate, later stage — **do not build it now**) must demonstrate,
at minimum:

1. **The two type registers, side by side:** one dense in‑app page (e.g. Subscription or
   Overview) and the auth page, so the dense‑content / calm‑frame contrast is visible in a
   single review.
2. **The evolved auth panel** (§6.1): a statically composed, fully tokenised,
   non‑interactive rendering of a **shipped** Tenora surface (subscription card / plan
   grid / members list / lifecycle timeline — **not** reconciliation / webhooks / usage /
   proration) with obviously synthetic values, plus eyebrow + one‑sentence headline. Must
   survive both themes and a narrow viewport.
3. **The overline/eyebrow element** in at least three contexts: a page header, a KPI
   caption, a card category label.
4. **The system‑pulse strip** (§6.2) on the Overview header — 2–3 items built only from
   subscription + membership data (`Plan`, `Status`, `Renews`, `Team`), each
   `overline + tabular value + status dot with word`. No reconciliation/webhook/usage
   item.
5. **The editorial page‑header pattern** (§6.3) applied to every prototyped page.
6. **A dense data table** with the reserved selection rail, plus its **stacked‑card mobile
   form**.
7. **A KPI row** with exactly one `featured` tile and the rest flat.
8. **An empty state and an error state** written in the "principle → consequence" voice.
9. **The sticky hairline top bar**, including the mobile‑collapsed state with the tenant
   switcher still visible.
10. **A reduced‑motion pass** of every prototyped screen, proving nothing essential is
    lost when motion is off.
11. **Both themes** for every screen.

The prototype must **not**: introduce a new colour or a second accent; change or add a
font; use any motion beyond the permitted feedback set; add gradient/glow to more than one
element per view; or use fluid viewport‑locked type.

---

## 10. Open design questions

Genuine questions to resolve during UI‑03 / UI‑04 — not manufactured uncertainty, and
**none of them block UI‑01 or require a decision now.** None reopens a master‑spec lock
(the status mapping, the no‑new‑backend‑surface rule, the dependency constraint, and the
motion posture are all settled).

1. **Auth panel — does "a redacted real surface" read as intended, or as a broken
   screenshot?** The whole premise of §6.1 depends on synthetic values and real components
   reading as "a calm demonstration" rather than "an app that failed to load." Needs a
   prototype test in both themes and at mobile width. Fallback: a more diagrammatic
   composition (a lifecycle timeline) rather than a data table.

2. **Top‑bar background — page ground + hairline, or keep the raised plane?** Lightening
   the bar toward the page ground makes the frame recede (good for "content‑out") but
   reduces the visual anchor when the page scrolls. Decide against a scrolled dense table.

3. **The larger display step — what value, and does it need its own line‑height/tracking
   tokens?** Somewhere in the 40–48px range for the composed register. Open: whether it
   extends the existing scale as one more step or becomes a separate "edge display" token
   with its own tighter tracking. UI‑04 sets the number; UI‑03 should trial a candidate.

4. **A fourth elevation/surface token for the system‑pulse strip?** The strip (bounded to
   subscription + membership data per §6.2) may want to sit visually "between" the page
   ground and a card. Adding a plane risks diluting the three‑plane discipline.
   Alternative, and the likely answer: render it with no surface at all — just an overline
   row on the page ground with a hairline under it, so no new token is needed.

5. **How far does monospace‑as‑register go?** Certainly IDs, keys, external references,
   event names, technical timestamps. Open: metadata *labels*, section kickers, the
   eyebrow itself? Risk: past a threshold the UI reads "terminal," which is adjacent to
   but not the same as "premium instrument."

6. **Emphasis — hold the strict one‑`featured`‑per‑view rule, or allow a quiet second
   tier?** The references use emphasis more liberally on marketing surfaces. A second tier
   (e.g. a tinted left border, no gradient, no glow) for "secondary‑important" cards could
   be useful on a busy Overview — or it could be the start of the slippery slope the spec
   already rejected. Decide with a populated Overview in the prototype.

7. **Does "quiet premium tech" apply to the light theme, or is light purely an
   accessibility/preference fallback?** Both references are dark. The proposed character is
   articulated for the dark surface. The light theme must stay fully accessible and
   usable, but it is an open call whether it should carry the same *character* (it can't
   lean on "dark surface as depth") or simply be a correct, calm, high‑contrast
   alternative. Prototype both auth‑panel treatments in light before deciding.

8. **Numbered‑step language for multi‑step flows — worth a shared pattern, or per‑flow?**
   Checkout, plan change and cancellation are the candidates. Low priority; revisit if
   UI‑03 surfaces a real need.

---

## Verification (UI‑01)

1. **Every HTML reference under `docs/design-references/` inspected.**
   - `Framer_ AI design agent.html` — read (structure, visible text in document order,
     inline CSS custom properties, colour set, type scale, radius set, transition set).
   - `SentientX _ AI Operating Partner for CPG and Retail.html` — read (same passes).
   - `Framer_ AI design agent_files/` and `SentientX … _files/` — directory listings
     reviewed; the HTML fragments within (`alpha.html`, `saved_resource.html`,
     `bc-v4.min.html`, `72c20e_*.html`) inspected and identified as editor‑bootstrap,
     analytics/service‑worker, cookie‑consent SDK, and one WebGL hero embed — no
     additional design content beyond the parent pages.
2. **No network requests were made.** All inspection was local file reads (a directory
   listing, local file reads, and a local Python text‑extraction script over the saved
   HTML). No reference site was opened or run; no external CSS, font, image, or asset URL
   was fetched; no embedded script was executed.
3. **No reference assets were copied into the frontend.** No image, font, SVG, stylesheet,
   or script from either `_files/` directory was added anywhere under `frontend/`.
4. **No production / frontend / backend source files were modified.** The only repo file
   created or changed in this stage is this document; the persistent memory index
   (outside the repo) was also updated.
5. **Only the intended UI‑01 artifact was created:** `docs/design-reference-analysis.md`.
   The `docs/design-references/` corpus is present but was supplied by the user, not
   created here.
6. **`docs/design-reference-analysis.md` exists** (this file).
7. **Reviewed for accidental transfer:** this document contains no reference CSS class
   name, no colour value, no hex code, no SVG path, no image or asset URL, no logo, no
   brand name used as branding, and no verbatim proprietary copy. Company names appear
   only as neutral attribution of where a pattern was observed; distinctive marketing
   sentences are paraphrased, never quoted. Patterns are described in Tenora's own
   vocabulary.
8. **Git status:** `docs/design-reference-analysis.md` and `docs/design-references/` are
   untracked; no tracked file is modified; `HEAD` remains `dc87ec0` (D8). Reported in
   full in the session summary.
9. **Reconciled to the finalised master specification:** §1.5 records the ten‑stage
   sequence and the two master‑spec rules (§7 status mapping fixed; §12/§22 no new
   frontend surface for backend‑only capabilities) that were applied across §4–§10 after
   the spec was finalised. The earlier draft's auth‑panel and "system pulse" examples that
   would have implied reconciliation / webhook / usage / proration UI were corrected in
   §4, §6.1, §6.2, §7.3, and §9.

---

## Hard stop

UI‑01 is complete and reconciled to the finalised master specification. No implementation
was performed. No frontend audit (UI‑02) was carried out — §7 is a deliberately light
read, not the A/B/C/D inventory. No visual prototype (UI‑03) was created. No design system
(UI‑04) was defined. Awaiting review and explicit approval of this document before UI‑02
begins.

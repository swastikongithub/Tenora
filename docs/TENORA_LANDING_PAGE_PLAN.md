# Tenora Public Marketing Landing Page — Claude Code Implementation Brief

## Feature Session

**Feature:** Public Marketing Landing Page  
**Project:** Tenora  
**Session rule:** This is a NEW feature session. `CLAUDE.md` requires one feature per session and an approved plan before implementation.

**Current product status:**
- P1–P8 Property Billing: shipped
- P10 polish: shipped
- P9 online resident payments: not yet implemented
- Landing page is intentionally being built before P9
- Existing authenticated Tenora application must remain intact

---

## 1. Claude Code Session Instructions

We are starting a NEW Tenora feature session: the public marketing landing page.

IMPORTANT:

`CLAUDE.md` requires one feature per session and an approved plan before code.

Therefore:

**DO NOT WRITE OR MODIFY IMPLEMENTATION CODE YET.**

First install/use the web-design skill:

```bash
npx skills add MengTo/Skills@build-awwwards-quality-sites
```

Then read:

- `CLAUDE.md`
- `docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md`
- the installed Build Awwwards-Quality Sites skill / `SKILL.md`
- existing frontend architecture
- existing design tokens and shared components
- existing routes and authentication behavior

After inspecting the repository and reference site, return ONLY the professional implementation proposal described in Section 13 below.

Do not implement anything until the user explicitly approves the plan.

---

## 2. Design Reference

Reference website:

https://weevolveit.com/

Study only its high-level interaction/design principles:

- pacing
- visual hierarchy
- typography scale
- section transitions
- image/media treatment
- scroll choreography
- pointer interactions
- navigation behavior
- CTA placement
- visual rhythm
- narrative progression while scrolling

### Do NOT copy

Do not:

- copy its layout
- copy its branding
- copy its content
- copy its identity
- trace its components
- reproduce sections one-for-one
- use its assets
- create a visual clone

The Tenora result must be materially original.

---

## 3. Product Definition

Tenora is a property-management SaaS.

Core workflow:

```text
Workspace
    ↓
Properties
    ↓
Units
    ↓
Residents
    ↓
Leases
    ↓
Meter Readings
    ↓
Bills
    ↓
Payments
    ↓
Receipts
    ↓
Aging / Reporting
```

### Two separate financial domains

These must remain conceptually and technically separate.

**Domain 1 — Tenora subscription**

```text
Workspace Owner
      ↓
Tenora Subscription
      ↓
apps.billing
```

**Domain 2 — Property billing**

```text
Resident
      ↓
Workspace / Property Owner
      ↓
Property Bills
      ↓
apps.properties
```

The landing page should primarily sell the property-management workflow while communicating that Tenora connects the entire system.

---

## 4. Landing Page Goal

The page should feel like a premium, serious SaaS product.

It must NOT feel like:

- generic Bootstrap
- an admin dashboard pasted into a marketing page
- a collection of rounded cards
- a stock-template site
- an AI-generated gradient/blob site
- an ornamental bento-grid exercise

Quality bar:

- memorable
- restrained
- product-focused
- technically sophisticated
- performance-conscious
- narrative-driven
- visually coherent

---

## 5. First-Viewport Requirement

The first viewport must immediately communicate:

### Brand
**TENORA**

### Headline
**Property management, without the paperwork.**

### Supporting concept
Manage properties, residents, rent, electricity, bills, payments and receipts from one workspace.

### Primary CTA
**Get started**

### Secondary CTA
**Sign in**

The hero must contain a strong visual focal point based on the REAL Tenora product experience.

Prefer actual Tenora UI or authentic reconstruction from the existing product over generic illustration.

---

## 6. Art Direction Requirements

Before coding, define:

1. Visual thesis
2. Hero focal asset
3. Typography hierarchy
4. Color system
5. Surface/material language
6. Section sequence
7. Motion narrative
8. Scroll narrative
9. Interaction language
10. Responsive strategy
11. Accessibility strategy
12. Asset provenance strategy

Explicitly decide:

- GSAP usage
- ScrollTrigger usage
- Lenis vs Locomotive Scroll
- which smooth-scroll engine is chosen and why
- whether Three.js is justified
- where real Tenora UI appears
- where generated/original assets are justified

### Smooth scrolling

Only ONE smooth-scroll engine may be installed and initialized.

Never use both Lenis and Locomotive Scroll.

Correctly integrate the chosen engine with GSAP/ScrollTrigger and clean it up during teardown.

### Three.js

Use Three.js only if meaningful spatial depth, interaction, displacement, texture transition, or similar behavior materially improves the Tenora story.

Do not use WebGL merely because it looks impressive.

If Three.js is rejected, explicitly explain why.

---

## 7. Narrative / Page Story

Claude should propose the best final sequence rather than blindly following a template.

A possible direction:

```text
Hero
    ↓
The Property Management Problem
    ↓
The Tenora Workflow
    ↓
Properties / Units / Residents
    ↓
Billing Engine
    ↓
Payments / Receipts
    ↓
Aging / Reporting
    ↓
Owner Experience
    ↓
Resident Experience
    ↓
Security / Trust
    ↓
Pricing
    ↓
Final CTA
    ↓
Footer
```

Claude may change the sequence if a better narrative is justified.

Every section needs a clear narrative purpose.

---

## 8. Motion Direction

Use motion to communicate meaning.

Study the reference for:

- entrance choreography
- scroll pacing
- section reveals
- pinned sequences
- typography reveals
- image movement
- cursor/pointer behavior
- hover behavior
- transition rhythm

For Tenora, examples of meaningful motion include:

### Property relationship
```text
Property → Units → Residents
```

### Billing story
```text
Reading → Consumption → Bill
```

### Payment story
```text
Bill → Payment → Receipt
```

### Aging
```text
Current → 1–30 → 31–60 → 61–90 → 90+
```

These are conceptual examples, not mandatory literal animations.

Avoid animation that exists only for decoration.

---

## 9. Accessibility / Motion Safety

Support:

- `prefers-reduced-motion`
- keyboard users
- touch devices
- coarse pointers
- window blur
- document visibility changes
- low-power/mobile behavior

With reduced motion:

- render final states immediately
- avoid merely shortening animation durations
- bypass scrubbed/pinned animation where appropriate
- bypass continuous smooth scrolling
- replace WebGL with static fallback if applicable

Meaningful text must remain accessible even if typography is split into animated words/characters.

Do not split links or meaningful inline markup into inaccessible animation fragments.

---

## 10. Authentic Tenora Product UI

Inspect the existing frontend and identify genuine product screens/components for:

### Hero
Owner workspace / billing overview.

### Property management
- properties
- units
- residents
- leases

### Billing
- bills
- billing overview
- meter readings
- tariffs
- aging

### Payments
- payments
- receipts

Do not market P9 online Cashfree resident payments yet because that feature is not shipped.

### Resident
- resident dashboard
- My Bills
- Billing History
- Receipts
- Notifications

Presentation-specific compositions around genuine Tenora UI are encouraged.

Do not invent product functionality.

---

## 11. Copy Rules

Write original landing-page copy.

Do not invent:

- customer logos
- testimonials
- customer counts
- revenue metrics
- countries served
- security certifications
- compliance certifications
- payment certifications
- partnerships
- press logos
- fabricated reviews

Establish credibility through actual product capabilities.

---

## 12. Pricing

Use the implemented plan model.

### Basic
- up to 2 workspaces
- up to 10 active members/residents per workspace

### Pro
- up to 20 workspaces
- up to 20 active members/residents per workspace

Do not invent pricing values if the application's pricing configuration should provide them.

Clearly distinguish:

**Tenora subscription:** workspace owner's relationship with Tenora.

**Resident property billing:** money residents owe the workspace/property owner.

Never merge these relationships in marketing copy.

---

## 13. Technical Constraints

Routes:

```text
/              → public marketing landing page
/login         → existing authentication
/register      → existing registration
/overview      → existing authenticated application
/admin/*       → existing platform admin
```

Do not break or redesign authenticated routes.

Reuse:

- existing design tokens
- existing typography
- existing shared components
- existing icon conventions

Do not create a second design system unnecessarily.

Keep dependencies intentional.

---

## 14. Performance Requirements

Plan for:

- responsive media
- lazy loading below the fold
- bounded transforms
- limited blur
- no permanent offscreen animation
- capped WebGL pixel ratio if used
- pause offscreen/hidden animation
- correct animation cleanup
- static first frame
- useful content without JS animation
- reduced-motion final states

GSAP/ScrollTrigger:
- kill timelines during cleanup
- remove listeners
- disconnect observers
- refresh measurements after fonts/media load
- avoid multiple animation systems fighting over the same property

Three.js, if used:
- cap device pixel ratio
- pause when hidden/offscreen
- throttle pointer input
- avoid per-frame allocations
- dispose resources
- handle context loss safely
- provide a static fallback

---

## 15. SEO

Plan for:

- semantic headings
- crawlable copy
- page title
- meta description
- Open Graph metadata
- accessible link text

Suggested title:

**Tenora — Property Management & Billing**

Suggested description:

**Manage properties, residents, billing, payments and receipts from one workspace with Tenora.**

Inspect the existing project and use its appropriate metadata approach.

---

## 16. Asset System

Classify assets into:

### Existing Tenora UI
Preferred for product demonstrations.

### New generated/original assets
Use only when they materially improve the concept.

### CSS/UI-created elements
Use for simple decorative geometry, interface surfaces, data graphics, subtle backgrounds and justified simple brand elements.

### External/licensed media
Only when appropriately licensed, credited/provenanced, and materially useful.

Avoid:

- watermarked assets
- copied mockups
- generic stock imagery
- decorative media without narrative purpose

---

## 17. Iconography

Use existing icon conventions where possible.

For new interface symbols, prefer Solar icons through Iconify as specified by the design skill.

Only use real company logos in truthful contexts.

Do not fabricate customer-logo walls.

---

## 18. Responsive Strategy

### Desktop
- full hero composition
- richer scroll choreography
- large typography
- side-by-side product UI
- controlled pointer interactions

### Tablet
- simplified hero
- reduced animation complexity where useful
- compressed/stacked product visuals

### Mobile
- no desktop-dependent choreography
- simplified pinned sequences
- touch-friendly controls
- no hover-only information
- reduced pointer effects
- optimized media
- meaningful final content without heavy animation

Mobile should be intentionally designed, not a collapsed desktop page.

---

## 19. Proposed Motion Stack

Claude must decide and justify:

### Primary animation
GSAP unless repository constraints provide a compelling reason otherwise.

### ScrollTrigger
Use for justified scrubbed/pinned narrative sequences and major section reveals.

Do not use ScrollTrigger for every trivial animation.

### Smooth scrolling
Evaluate Lenis and Locomotive, choose exactly ONE or reject both.

### CSS
Use CSS for simple hover/focus/tap states.

Avoid competing systems controlling the same visual property.

---

## 20. Quality Bar

The first viewport must be the strongest authored moment.

The final page should include:

- responsive navigation
- clear hierarchy
- hero with strong product focal point
- coherent section progression
- concrete conversion content
- final CTA
- footer
- complete interaction states
- visible keyboard focus
- loading/disabled/error states where applicable
- reduced-motion behavior
- touch behavior
- static fallbacks

Reject:

- generic gradient blobs
- ornamental bento layouts
- excessive glassmorphism
- stock component layouts
- fake testimonials
- invented partnerships
- logo-wall theater
- motion with no narrative role

---

## 21. Required Pre-Coding Analysis

Inspect:

### Repository
- `CLAUDE.md`
- `frontend/`
- router
- layout
- public/auth pages
- design tokens
- components
- typography
- icons
- CSS strategy
- test setup
- build setup

### Product
Identify real screens/components that can become marketing visuals.

### Reference
Study WeEvolveIT only for high-level principles:
- hierarchy
- pacing
- contrast
- media treatment
- motion principles
- interaction language

Keep Tenora materially original.

---

## 22. Required Output Before Coding

Claude must return ONLY this professional implementation proposal:

### A. Creative Direction
Visual thesis and why it fits Tenora.

### B. Reference Analysis
Interaction/design principles learned from WeEvolveIT and how Tenora will reinterpret them differently.

### C. Hero Concept
Exact composition, focal visual, headline treatment, CTA placement, product UI composition, entrance animation, pointer behavior, static fallback.

### D. Full Section Architecture
Every section in order, with purpose, core message, visual, interaction and transition.

### E. Motion Architecture
GSAP / ScrollTrigger / smooth-scroll choice, section-by-section animation, pointer/hover interactions, reduced-motion behavior, cleanup strategy.

### F. Three.js Decision
Use / don't use + technical justification.

### G. Asset Plan
Existing Tenora UI / newly generated / CSS/UI / external licensed assets, with provenance approach.

### H. Technical Implementation
Exact files/components/routes likely to change.

### I. Responsive Behavior
Desktop / tablet / mobile strategy.

### J. Accessibility and Fallback Behavior
Keyboard / focus / reduced motion / touch / no-JS / static media fallback / semantic structure.

### K. Validation Plan
Tests / typecheck / lint / production build / responsive validation / animation cleanup.

### L. Risks
Performance / maintainability / accessibility / authenticity / route safety / animation complexity / media weight.

---

## 23. Hard Stop

After producing Sections A–L:

**STOP.**

Do not:

- write implementation code
- create components
- install additional packages beyond the requested design skill
- modify routes
- modify business logic
- modify backend code
- modify authenticated application screens

Wait for explicit user approval.

---

## 24. Short Prompt to Store This in `docs/`

Use this prompt in Claude Code:

```text
Create the complete landing-page implementation brief from the attached/current landing-page instructions as:

docs/TENORA_LANDING_PAGE_PLAN.md

Preserve the full structure, requirements, constraints, reference rules, motion requirements, technical constraints, validation requirements, and mandatory A–L pre-coding proposal output.

Do not implement the landing page yet.

After writing the file, verify it exists at exactly:
docs/TENORA_LANDING_PAGE_PLAN.md

Do not modify application code.
```

---

## 25. Short Prompt to Start the Actual Planning Session

After the file exists:

```text
We are starting the Tenora public landing-page feature session.

Read:
- CLAUDE.md
- docs/TENORA_LANDING_PAGE_PLAN.md
- docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md
- the installed Build Awwwards-Quality Sites SKILL.md

Follow CLAUDE.md strictly.

Do NOT write implementation code yet.

Study the existing frontend and https://weevolveit.com/ as instructed by the landing-page plan.

Return ONLY the requested A–L professional implementation proposal.

Stop and wait for my approval.
```

---

## 26. Landing Page Definition of Done

The landing-page feature is complete only when:

- `/` is fully implemented as the public marketing page
- authenticated routes remain functional
- the identity is materially original
- the hero is compelling without depending on animation
- actual Tenora product UI is used where appropriate
- motion is coherent and purposeful
- only one smooth-scroll engine is used, if any
- GSAP/ScrollTrigger cleanup is correct
- reduced-motion behavior works
- keyboard navigation and visible focus work
- desktop/tablet/mobile layouts are intentional
- no unsupported marketing claims exist
- no fake testimonials/logos/partnerships exist
- SEO metadata is correct
- production build passes
- tests/typecheck/lint pass
- `git diff --check` passes
- performance/bundle risks are understood
- no unrelated Tenora behavior is broken

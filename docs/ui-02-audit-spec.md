# Claude Code Implementation Specification — UI-02: Frontend Audit

**Scope:** a comprehensive, read-only audit of the current Tenora frontend,
producing docs/frontend-audit.md. This stage inventories what exists and
classifies it (A/B/C/D) - it does not redesign, prototype, or write any
production code.

**Not in scope:** UI-03 (prototype), UI-04 (design system), any visual
change, any backend change, any dependency change, any route/API/theme
change, re-doing UI-01's reference research.

---

## 0. This is a read-only stage — the constraint that matters most

No frontend or backend source file is modified. No test file is modified
under any circumstance - if tracing a coupling chain seems to need a
throwaway script, run it ad hoc (bash/grep) and discard it; never create
or alter a tracked test file "for audit tooling." Only one new file is
produced: docs/frontend-audit.md. If this constraint turns out to be
genuinely impossible for some specific tracing task, stop and report it
- don't quietly work around it.

## 1. Objective

Establish a precise, code-traced inventory of the current frontend -
what must remain functionally unchanged (A), what visual implementation
may be replaced (B), what can be safely generalized (C), and what must
not be touched at all (D) - so UI-03 through UI-09 have a reliable map
instead of working from assumption.

Every claim in the resulting document must be traced to real code,
not inferred from documentation or repeated from UI-01 without
verification. UI-01's own design-reference-analysis.md section 7
explicitly flagged itself as "a light read... not the UI-02 audit" -
closing that gap honestly is this stage's actual job. Where this audit
confirms a UI-01 claim against the real code, say so. Where it finds
UI-01 was wrong or incomplete about the existing frontend (not the
proposed direction, which UI-02 doesn't re-litigate), report the
discrepancy explicitly - do not silently correct it or silently let it
stand, per this project's standing CLAUDE.md rule.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md
docs/tenora-redesign-master-spec.md    - the ten-stage program and every
                                          locked rule this audit must
                                          respect (section 7 status
                                          mapping, section 12/22 no new
                                          backend-only surfaces,
                                          section 19 no new dependency)
docs/design-reference-analysis.md      - UI-01's output; context only,
                                          not re-derived, but its
                                          section 7 claims are exactly
                                          what this stage must
                                          independently verify
frontend/src/                          - the actual repository; the
                                          audit is grounded here, never
                                          in what documentation claims
                                          exists
```

## 3. Existing Functionality That Must Not Change

Everything - this is a read-only stage. All frontend tests, all backend
tests, every route, every component, every API contract, every
dependency, the theme, unchanged. The one new artifact is
docs/frontend-audit.md.

## 4. Required Deliverable — docs/frontend-audit.md

Structure (as specified):

```
1. Purpose and scope
2. D1-D8 baseline and UI redesign context
3. Frontend architecture overview
4. Route inventory (route / access level / purpose / major dependencies /
   A-B-C-D / redesign notes, for every route)
5. Authentication audit
6. Tenant lifecycle audit
7. Subscription/billing audit
8. Members/team audit
9. Overview/dashboard audit
10. Settings/profile/tenant settings audit
11. Platform administration audit
12. Shared component inventory (role / consumers / data dependencies /
    classification / visual replaceability / refactor opportunities /
    coupling risks, for every major shared component)
13. Data/API integration map
14. State-handling inventory (loading/success/empty/error/permission-
    restricted/disabled/pending/destructive-confirmation, per major
    page/component, and whether each already exists)
15. Responsive behavior inventory
16. Accessibility inventory
17. Existing visual-system inventory (NOT the new design system)
18. AuthArtPanel / existing identity assessment
19. A/B/C/D master matrix (consolidated)
20. Safe refactoring opportunities
21. Protected/high-risk areas
22. UI redesign sequencing implications (which areas belong to UI-05
    through UI-09 - does not implement any of them)
23. Open questions/decisions - genuine only, none manufactured
24. UI-02 acceptance evidence
```

### 4.1 A/B/C/D classification — exactly as specified, non-negotiable

- A - must remain functionally unchanged: auth behavior, tenant
  behavior, authorization, API contracts, business-state interpretation,
  critical data flow, security-sensitive behavior.
- B - visual implementation may be replaced (JSX composition, styling,
  layout, typography presentation) provided the functional contract is
  unchanged.
- C - safe to generalize/refactor. Every C classification must explain
  why the refactor is safe, and must confirm it introduces no new
  dependency and follows existing composition patterns (per the master
  spec's section 19 rule) - a C classification proposing a new library
  is a contradiction, not a valid classification.
- D - do not touch: strong backend/API coupling, security-sensitive,
  tenant-isolation risk, auth/token logic, fragile mechanism. Every D
  classification must explain the specific risk, not just assert it.

Do not classify from filenames. For every component significant enough
to warrant a coupling judgment, trace the real chain: component ->
hook/query -> API client -> route/auth/tenant context -> backend
endpoint where relevant. Pay particular attention to X-Tenant-ID
injection, auth state, query caching/invalidation, tenant switching,
authorization gating, and subscription-status handling.

### 4.2 Explicit out-of-scope confirmation

Confirm explicitly, per master spec section 12/22: no new usage
analytics, usage dashboard, proration history, reconciliation UI, or
webhook-monitoring surface exists today, and none is proposed here.
D5/D6/D8 capabilities without existing frontend stay without frontend -
this audit documents that absence, it doesn't fill it.

## 5. Files Likely Affected

```
new: docs/frontend-audit.md
```

Nothing else. No source file, test file, config file, or dependency
change of any kind.

## 6. Must NOT Do

- Do not modify any source, test, config, or route file.
- Do not "clean up" code encountered while auditing.
- Do not fix any visual or accessibility problem found - document it.
- Do not add a dependency.
- Do not change the theme.
- Do not invent a frontend surface that doesn't exist, or assume one
  exists because a backend endpoint exists.
- Do not classify a component as C without tracing its actual consumers.
- Do not silently resolve a discrepancy against UI-01's claims - report
  it (section 1).
- Do not begin UI-03, UI-04, or any later stage.
- Do not redo UI-01's reference research.

## 7. Acceptance Criteria

1. Every actual frontend route accounted for.
2. Major shared components inventoried, each with a traced coupling
   chain where relevant - not a filename-based guess.
3. Every significant area carries an A/B/C/D classification with stated
   reasoning (C: why safe; D: what risk).
4. Auth and tenant coupling explicitly documented, traced to code.
5. Subscription/billing coupling explicitly documented, traced to code.
6. API/data dependencies mapped.
7. Responsive behavior documented as it actually exists today.
8. Accessibility behavior documented as it actually exists today.
9. Existing visual-system mechanisms documented (not redesigned).
10. AuthArtPanel/existing identity documented factually.
11. New backend-only frontend features explicitly confirmed excluded.
12. Safe refactors separated from protected/high-risk areas.
13. No source code modified - git status proves it.
14. No API contract changed.
15. No dependency added.
16. No UI implementation performed.
17. The document is internally consistent - no contradiction between,
    e.g., section 4's route table and section 19's master matrix.
18. git status reported in full in the final report.
19. UI-01's checkpoint commit remains untouched.
20. The result is a reliable factual foundation for UI-03 - not an
    aspirational one.
21. Any UI-01 claim this audit found to be inaccurate about the
    existing frontend is explicitly flagged, not silently corrected.
22. docs/frontend-audit.md is committed as its own checkpoint (mirroring
    UI-01's checkpoint) once approved - not left uncommitted indefinitely.

## 8. Scale caution — report, don't rush

Tracing every significant component's full coupling chain across a
frontend this size is real, substantial work - larger in scope than a
typical single Claude Code session in this project has handled. If the
actual scope discovered during inspection is larger than expected, stop
and report that plainly rather than truncating coverage silently to fit
a session. Splitting this audit into two passes (e.g., the
security/coupling-sensitive areas - auth, tenant, subscription, RBAC -
first, then the purely visual/component inventory) is an acceptable and
likely reasonable outcome; propose it if the real scope warrants it.

---

## Workflow

Produce a plan first - including an honest estimate of scope and whether
a single-session or two-session approach is warranted per section 8 -
and wait for approval before beginning the audit itself.

---

## Ready-to-paste prompt for Claude Code

Read docs/ui-02-audit-spec.md, then inspect the repository.
Produce a plan - including an honest scope estimate and whether this
should run as one session or two per section 8 - and wait for my
approval before beginning the audit.

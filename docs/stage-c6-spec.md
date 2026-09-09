# Claude Code Implementation Specification — Stage C6

**Scope:** the Overview dashboard - a tenant-scoped summary pulling together
subscription status, plan, renewal date, team size, a compact members preview,
and a plan summary panel. Replaces OverviewStub. No new backend endpoints - this
page composes data that already exists and is already fully tested.

**Milestone significance:** per the execution plan, this is the last page in the
"complete, demoable, full-stack" milestone. After this stage, the project is
CV-ready - say so plainly in the final report, it's worth marking.

**Not in scope:** any backend change, Stage D / Phase 2, the deferred
cancellation UI, the Platform Admin dashboard (tracked separately for after this
milestone).

---

## 1. Objective

Every other page in this app shows one thing (members, or the subscription, or
the workspace list). Overview is the first page to compose multiple independent
tenant-scoped queries into one view - subscription and memberships, at minimum.
That makes two things this stage's actual job, beyond just building UI:

1. Per-tile failure isolation. If the memberships query fails but the
   subscription query succeeds, the page must show the subscription tiles
   correctly and an error only where the failure actually occurred - not blank
   the whole page because one of several independent queries had a problem.
2. All tenant-scoped queries on this page must refresh together on tenant
   switch. This is a stronger version of C5's mixed-query isolation test - C5
   had one global query that should NOT refetch and one tenant-scoped query
   that should; this page likely has only tenant-scoped queries, so the proof
   here is that every one of them updates correctly and in sync when the tenant
   changes, not just one.

No fabricated data anywhere on this page. Every tile traces to a real field from
GET /api/subscriptions/current/, GET /api/memberships/, or GET /api/tenants/me/
(for the tenant's own name/role, already available via useTenant()). If a tile
concept from the original UI design spec doesn't have a real backing field, cut
the tile - don't invent placeholder content to fill the layout.

**Addendum (post-approval, see §4.1a):** this stage also extends
`src/lib/format.ts` with a `formatRelativeDate` helper (an `Intl.RelativeTimeFormat`
wrapper, same house style as `formatMoney`/`formatDate`) and adds a Workspace
Details panel, per-status plain-English explanations, and spelled-out billing
intervals. That is a scoped exception to §5/§11's "no change to format.ts" -
recorded there explicitly rather than left contradicted.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/ui-design-specification.md        - section C.4 Page 5 (Overview Dashboard)
                                          - the original design intent: KPI row
                                          (one featured card + supporting cards)
                                          plus two panels below (Members compact,
                                          Plan summary)
docs/project-master-spec.md            - section B.7 (confirm no endpoint this
                                          page needs is missing - it shouldn't
                                          be; report immediately if it is, don't
                                          invent one)
apps/billing/serializers.py            - SubscriptionSerializer field names
                                          (verify exactly what's available: plan
                                          nested object, status, period dates)
apps/tenants/serializers.py            - Membership serializer fields (for the
                                          compact members preview)
frontend/src/routes/SubscriptionPage.tsx - reuse its query, its 404-vs-error
                                          distinction, its status->Badge mapping,
                                          and its money/date formatting
                                          (src/lib/format.ts, already shared per
                                          C5)
frontend/src/routes/MembersPage.tsx    - reuse its members query and row shape
                                          for the compact preview (top 5, not the
                                          full table - don't duplicate Table's
                                          mobile transform machinery for a 5-row
                                          preview if a simpler list suffices; use
                                          judgment)
frontend/src/lib/query-keys.ts         - queryKeys.currentSubscription(tenantId)
                                          and the members key already exist and
                                          are unused-together until now
frontend/src/components/Card.tsx       - the featured variant (C1a) - reserved
                                          for exactly ONE hero tile on this page
frontend/src/routes/stubs.tsx          - current OverviewStub being replaced
frontend/src/routes/AppRoutes.tsx      - route wiring to update
```

Current state: C5 (Subscription & Plans) committed, frontend 222/222, backend
71/71. OverviewStub currently reads "Overview - built in Stage C6."

## 3. Existing Functionality That Must Not Change

- No backend file modified. This page only reads from endpoints that already
  exist and are already tested.
- AuthProvider, TenantProvider, TopNavbar, AccountMenu, the query-key isolation
  mechanism, Table.tsx, SubscriptionPage.tsx, MembersPage.tsx - none of these
  are modified. This page consumes their established query keys and formatting
  helpers; it does not change how they work.
- All 222 frontend and 71 backend tests must still pass.
- The featured Card rule from C1a ("reserve for the single most important card
  on a page - if more than one is featured, none reads as featured") - this
  page must have at most one featured card, chosen deliberately (the
  subscription status tile is the natural candidate per the original UI spec).

## 4. Required Changes

### 4.1 KPI row

Per the original UI spec's Page 5 intent, adapted to only what's real:
- Subscription status (the featured tile) - status Badge (reuse
  SubscriptionPage's exact status->variant mapping), plan name.
- Current plan - plan name + formatted price (reuse formatMoney from
  src/lib/format.ts).
- Renewal date - current_period_end, formatted (reuse formatDate).
- Team size - a count. Derive this client-side from the length of the
  memberships array already being fetched - do not create a new backend
  endpoint or field for a count. If the memberships query hasn't resolved yet,
  this tile shows its own loading state independent of the subscription tiles
  (section 4.3).

No-subscription case: if the tenant has no subscription (404, same
"not-an-error" distinction SubscriptionPage already established), the KPI row
collapses to a single message card - OWNER sees a "Choose a plan" call-to-action
linking to /subscription; MEMBER sees the same information with no action. Do
not render the other KPI tiles (plan/renewal/etc.) in a broken or empty state
when there's nothing to show - collapse the whole row to this one message.

### 4.2 Panels

- Members (compact): top 5 members from the same memberships query
  (GET /api/memberships/), each showing email + role Badge, plus a "View all"
  link to /members. Loading/error/empty states independent of the KPI row.
- Plan summary: current plan detail (name, price, interval) plus, OWNER only, a
  "Change plan" link to /subscription (same "client-side hiding is UX, server
  enforces" comment discipline as every other role-gated control in this app -
  though note this is just a link, not a mutation, so there's no server
  enforcement to point to here; the real boundary is SubscriptionPage's own
  OWNER gate on the actual mutation controls, which this page doesn't
  duplicate).

### 4.3 Per-tile failure isolation

This is the architectural point of the stage, not a minor detail:
- The subscription-derived tiles (status, plan, renewal) and the
  membership-derived tiles (team size, members panel) must be able to fail or
  load independently. Structure the queries so that a failure in one does not
  prevent the other from rendering - verify this isn't accidentally coupled by
  a shared loading gate that waits for both before showing anything.
- Each failure gets its own inline retry, scoped to just that tile/panel, not a
  page-wide error state.

### 4.1a Additional tiles/panels (post-approval addition)

Requested after the initial plan was drafted, folded in before implementation:

- **Workspace Details panel** - tenant name, slug, "Workspace created"
  (`Tenant.created_at`, from `useTenant()`) and, separately, "Member since" -
  the *viewer's own* `Membership.created_at` (matched by email via the
  existing `useCurrentUser()` hook), never `Tenant.created_at` mislabeled -
  those are two different real dates and conflating them would be fabricating
  meaning even though the number itself is real. Also states the viewer's own
  role plus a one-line explanation of what that role can do. Omit "Member
  since" (don't show a wrong value) if the memberships query hasn't resolved
  or the viewer's row can't be matched.
- **Per-status explanation.** One plain-English line per `Subscription.Status`
  value (TRIALING/ACTIVE/PAST_DUE/CANCELED), shown beside the status Badge -
  what the state means, not a restatement of the label.
- **Relative renewal phrase.** The renewal date renders both the absolute date
  (`formatDate`) and a relative phrase ("in 12 days") via the new
  `formatRelativeDate`. When CANCELED, the tile reads as "Period ended," not an
  upcoming renewal.
- **Spelled-out billing interval.** "Billed monthly" / "Billed annually," not
  the raw `MONTHLY`/`ANNUAL` enum value.

### 4.4 Tenant-scoped isolation across multiple queries

- Every query on this page (subscription, memberships) uses its established
  tenant-scoped key. On tenant switch, all of them must refetch and reflect the
  new tenant's data - verify no tile shows stale data from the previous tenant
  even momentarily in a way that's misleading (a brief loading skeleton during
  refetch is fine and expected; rendering the previous tenant's numbers under
  the new tenant's context is not).
- Reuse the exact query keys already defined - do not introduce new ones for
  data this page shares with SubscriptionPage/MembersPage.

## 5. Files Likely Affected

```
new:      frontend/src/routes/OverviewPage.tsx (replaces OverviewStub)
          tests for the above
modified: frontend/src/routes/AppRoutes.tsx (OverviewPage replaces the stub)
          frontend/src/lib/format.ts (adds formatRelativeDate - §4.1a scoped
                                       exception)
          frontend/src/lib/__tests__/format.test.ts (tests for the above)
deleted:  frontend/src/routes/stubs.tsx (OverviewStub was its last export and
                                          only remaining stub, so the file is
                                          removed outright rather than emptied)
```

No backend file. No change to Table.tsx, query-keys.ts, SubscriptionPage.tsx, or
MembersPage.tsx - this page is a consumer of what already exists.

**Scoped exception (§4.1a):** `frontend/src/lib/format.ts` gains one new export,
`formatRelativeDate`, alongside the existing `formatMoney`/`formatDate` - the
one shared-file change this stage makes, and the only one.

## 6. Business Rules

- No tile may show fabricated or placeholder data. If a concept from the
  original UI spec (e.g. something requiring a field that doesn't exist on any
  real serializer) can't be backed by a real value, cut it - report the cut,
  don't invent a number.
- tenant_id never appears in any request from this page (it makes no mutating
  requests at all - this is a read-only dashboard).

## 7. Accessibility Requirements

- KPI tiles and panels use real headings in a sensible order (not all h1, not
  skipping levels).
- Loading skeletons match the shape of their eventual content (existing project
  convention).
- Status conveyed by the Badge is never color-only (already guaranteed by the
  Badge primitive's own contract from C1 - just confirm this page doesn't
  bypass it).

## 8. Edge Cases

- Tenant has a subscription but zero members beyond the OWNER themselves - team
  size shows 1, members panel shows just that one row, not an empty state (a
  tenant always has at least its creating OWNER).
- Tenant has no subscription - KPI row collapses per section 4.1; the members
  panel still renders normally (having no subscription doesn't mean having no
  team).
- One query fails, the other succeeds - verify visually, this is the core proof
  of section 4.3, not just a theoretical requirement.
- Tenant switch mid-load - verify no tile ends up displaying a mismatched
  combination (e.g. new tenant's plan name next to old tenant's renewal date)
  due to queries resolving at different times during the switch.
- Very long tenant/plan names in the compact tiles - verify truncation, not
  overflow/wrapping breakage.

## 9. Tests Required

- KPI row: renders correctly with a real subscription; collapses to the single
  message card (OWNER variant and MEMBER variant) when there's no subscription;
  team size reflects the actual memberships count.
- Featured Card: exactly one tile carries the featured prop - an explicit
  assertion, not just visual inspection.
- Members panel: shows up to 5 members with correct role badges; "View all"
  links to /members.
- Plan summary panel: shows current plan; "Change plan" link visible for
  OWNER, absent for MEMBER.
- Per-tile failure isolation: mock the subscription query to fail while
  memberships succeeds (and vice versa) - assert the succeeding section
  renders its real data while only the failing section shows an error. This is
  the signature test for this stage, name it clearly.
- Tenant switch: both queries refetch and reflect the new tenant's data
  correctly - the page-level proof that a page with multiple simultaneous
  tenant-scoped queries handles a switch correctly, not just a single-query
  page like prior stages.

## 10. Acceptance Criteria

1. npm run build clean.
2. npm test - all previous tests pass plus new ones, exact count reported. The
   per-tile-failure-isolation test must be individually identifiable in the
   report.
3. npm run lint clean.
4. .venv/Scripts/python.exe manage.py test - still 71/71, confirmed by actually
   running it (not assumed unaffected, since this stage's whole point is
   consuming multiple endpoints together - worth the real check).
5. Manual walkthrough, screenshotted, both themes, both roles: full dashboard
   with data, no-subscription collapsed state (both roles), a live tenant
   switch confirming all tiles update together, and - if reasonably producible
   - a forced single-tile failure to show the isolation working visually, not
   just in a test assertion.
6. git status - no file outside frontend/ and docs/ (the §4.1a addendum to this
   spec file, and the corresponding note in project-master-spec.md if one is
   needed, are the only docs/ changes).
7. Report: which UI-spec Page 5 concepts (if any) were cut because no real
   field backs them, and confirm the featured-card count is exactly one.

## 11. Must NOT Do

- Do not add a new backend endpoint or field for the team-size count - derive
  it client-side from the existing memberships list.
- Do not fabricate any number, chart, or statistic not backed by a real field.
- Do not render more than one featured Card on this page.
- Do not modify SubscriptionPage.tsx, MembersPage.tsx, Table.tsx, or
  query-keys.ts - consume them as-is. `format.ts` is the one named exception
  (§4.1a/§5): only the new `formatRelativeDate` export is added, nothing
  existing in that file changes.
- Do not build the Platform Admin dashboard or the cancellation UI - both
  tracked separately, both explicitly out of scope here.
- Do not modify any backend file.
- Do not weaken any existing test.
- Do not start Stage D / Phase 2 or the Docker packaging stage.

---

## Workflow

Produce a plan first and wait for approval before writing code. This stage is
smaller than C4/C5 in raw surface area (no new backend work, mostly composition
of existing data), but the per-tile-isolation and multi-query-refetch
correctness matter more than the visual layout - treat those as the actual bar
for "done," not just "renders correctly with good data."

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-c6-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.

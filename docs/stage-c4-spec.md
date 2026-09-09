# Claude Code Implementation Specification — Stage C4

**Scope:** the Members page — list current tenant's members with role badges, and
(OWNER only) add an existing user by email. Replaces the "Members — built in Stage
C4" route stub. Also where Table's mobile stacked-card behavior (deferred since C1)
finally gets built and verified against real data.

**Not in scope:** Subscription & Plans (C5), Overview (C6), any backend change, Stage
D / Phase 2.

---

## 1. Objective

This is the first page to actually use the Table primitive with real data, and the
first page where RBAC becomes visually meaningful - an OWNER sees an "Add member"
action a MEMBER does not, and the server enforces that regardless of what the client
renders. It's also where the C1-deferred decision (build Table's mobile stacked-card
transform now, against real content, not speculatively) finally gets resolved.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md            - section B.7 (POST/GET /api/memberships/ contract)
docs/ui-design-specification.md        - section C.4 Members page spec (Page 3),
                                          section C.7 (Table mobile transform
                                          requirement - read this in full, this is
                                          the deferred decision landing here)
docs/stage-b1-spec.md                  - the actual membership endpoints' behavior:
                                          OWNER-only create, MEMBER-only role assigned,
                                          duplicate/unknown-email error shapes,
                                          concurrency handling
apps/tenants/views.py, serializers.py  - ground truth for exact request/response
                                          shapes - verify against code, don't assume
frontend/src/components/Table.tsx      - current desktop-only implementation
frontend/src/routes/WorkspacePage.tsx  - the closest existing precedent for a
                                          list+create-modal page pattern; reuse its
                                          structure where it fits
frontend/src/lib/query-keys.ts         - tenant-scoped key convention (from C2)
frontend/src/lib/tenant/               - useTenant(), for the current tenant + role
```

Current state: Navbar redesign complete (d072e8a), 171/171 frontend, 70/70 backend.
Route stub currently reads "Members - built in Stage C4."

## 3. Existing Functionality That Must Not Change

- No backend file modified. This stage consumes /api/memberships/ exactly as it
  exists.
- AuthProvider, TenantProvider, TopNavbar, AccountMenu, the query-key isolation
  mechanism - untouched. This page renders inside the existing shell.
- All 171 frontend and 70 backend tests must still pass.
- No C1/C1a primitive redesigned - this page composes Table, Button, Badge, Modal,
  Input, EmptyState, Skeleton. The one exception is Table itself gaining its mobile
  transform (section 4.3) - that's an addition, not a redesign of its existing
  desktop behavior.

## 4. Required Changes

### 4.1 Members list

- GET /api/memberships/ - tenant-scoped (requires X-Tenant-ID, already handled by
  the API client from C2). Query key: ['tenant', tenantId, 'memberships'],
  following the C2 convention exactly.
- Columns: email, role (Badge - OWNER accent, MEMBER neutral, per the existing
  badge variant convention), joined date (verify the actual field name/format the
  backend returns - check apps/tenants/serializers.py, don't assume).
- Loading: Table-shaped Skeleton rows (reuse existing pattern from other pages
  where established, or establish it here consistently).
- Empty: shouldn't realistically happen (the creating OWNER always exists in a
  tenant), but if the list somehow renders empty, treat it as a genuine error state
  per the original UI spec's guidance on this exact case, not a cheerful empty state.
- Error: inline retry panel, consistent with other pages' error handling.

### 4.2 Add member (OWNER only)

- Visible only when the current user's role in the active tenant is OWNER (from
  useTenant()). This is UX only - the server enforces the real permission
  (IsTenantOwner) regardless of what renders client-side. State this explicitly in
  a code comment at the point the button is conditionally rendered, same discipline
  as every other client-side permission check in this project.
- Modal with a single email field. Calls POST /api/memberships/.
- No role field anywhere in this form. The endpoint only ever assigns MEMBER
  (rendering a role selector would imply a capability the API doesn't have - this
  was explicitly forbidden at the backend spec level in B1 and the constraint
  carries through to the UI).
- Duplicate member -> inline field error on the email field, not a toast
  (consistent with the Workspace page's duplicate-slug handling pattern from C3).
- Unknown email -> whatever the actual backend response is (verify - B1's spec
  left this as "404 or 400, your call, but be consistent"; check what was actually
  implemented and render that correctly, don't assume).
- Success -> close modal, list reflects the new member (invalidate the
  tenant-scoped query key, or optimistically insert - implementer's call, report
  which and why).

### 4.3 Table mobile stacked-card transform (the deferred C1 decision, landing now)

Per UI spec section C.7: on mobile, the members table converts to stacked cards -
email as the card's primary text, role badge and joined date as secondary metadata
- not a horizontally-scrolling shrunken table. This was explicitly deferred in C1
specifically so it could be built and verified against real content instead of
guessed at in isolation - that moment is now.

- Decide whether this transform lives in Table.tsx itself (a general capability
  future tables can opt into) or is specific to this page's usage. Given the UI
  spec frames this as a Table requirement generally, building it into Table.tsx as
  a reusable capability is likely correct - but verify this against how Table is
  actually structured before committing to the approach, and report which you
  chose.
- Verify visually at the actual mobile breakpoint, same discipline as every other
  responsive decision in this project - don't assume the transform works,
  screenshot it.

## 5. Files Likely Affected

```
new:      frontend/src/routes/MembersPage.tsx (replaces the stub)
          frontend/src/routes/AddMemberModal.tsx (or co-located)
          tests for the above
modified: frontend/src/components/Table.tsx (mobile transform, section 4.3)
          frontend/src/lib/query-keys.ts (membership query key, if not already present)
          route config (MembersPage replaces the stub component)
```

No backend file.

## 6. Business Rules

- tenant_id never appears in any request body from this page.
- The add-member form can never produce an OWNER - no role field exists at all.
- Membership creation always targets request.tenant from the header, never
  anything the client specifies.

## 7. Security Requirements

- Client-side hiding of "Add member" for a MEMBER is UX, not authorization - the
  server's IsTenantOwner is the real boundary. State this in code, don't just rely
  on it implicitly.
- No PII beyond what's already shown elsewhere in the app (email, role) - nothing
  new introduced here.

## 8. Edge Cases

- MEMBER views the page - list renders, no "Add member" button, and if they
  somehow reach the modal via a stale render, the server's 403 must be handled
  gracefully (inline error, not a crash).
- Duplicate member submission - inline error, modal stays open with the entered
  email preserved so the user isn't forced to retype.
- Unknown email - clean, specific error message (not a generic failure).
- Switching tenant while on the Members page - the list must refresh to the new
  tenant's members via the query-key mechanism (this is exactly what C2's
  signature test exists to guarantee); verify it holds here too, don't just assume
  the mechanism "just works" without a concrete check on this page.
- Mobile stacked-card view with a long email - verify truncation/wrapping looks
  correct, not broken.

## 9. Tests Required

- Members list renders correctly for both OWNER and MEMBER roles (button
  visibility differs, data doesn't).
- Loading/error/empty(-as-error) states render correctly.
- Add-member modal: validates, submits, duplicate -> inline error, unknown email ->
  correct error, success -> list updates.
- No role field exists anywhere in the add-member form (a test asserting its
  absence, not just that the happy path works).
- Tenant switch while on this page correctly refreshes the list to the new
  tenant's members - this is the page-level proof of C2's isolation mechanism
  actually working end-to-end, not just in the abstract test from C2.
- Table mobile transform: renders as stacked cards below the mobile breakpoint, not
  a horizontally-scrolling table.

## 10. Acceptance Criteria

1. npm run build clean.
2. npm test - all previous tests pass plus new ones, exact count reported.
3. npm run lint clean.
4. .venv/Scripts/python.exe manage.py test - still 70/70, unaffected.
5. Manual walkthrough, screenshotted, both themes, both roles (use the seeded demo
   tenants/users, or create a second membership if needed): members list,
   add-member flow (success and duplicate-error cases), mobile stacked-card view,
   and a live tenant switch confirming the list updates correctly.
6. git status - no file outside frontend/.
7. Report: where the unknown-email error actually renders from (verify against
   real backend behavior), and where the Table mobile transform was implemented
   (component-level vs. page-level) and why.

## 11. Must NOT Do

- Do not add a role selector to the add-member form.
- Do not build Subscription/Plans or Overview - C5/C6.
- Do not modify any backend file.
- Do not modify AuthProvider, TenantProvider, TopNavbar, AccountMenu, or the
  query-key isolation mechanism beyond adding the new membership query key.
- Do not build a horizontally-scrolling mobile table - the stacked-card transform
  is required, not optional, per section C.7.
- Do not weaken any existing test.
- Do not start C5.

---

## Workflow

Produce a plan first and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-c4-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.

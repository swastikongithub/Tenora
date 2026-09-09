# Claude Code Implementation Specification — Stage C5

**Scope:** the Subscription & Plans page — show the tenant's current subscription
(or its absence), list available plans, and let an OWNER start a subscription or
change plans. Replaces the `SubscriptionStub` route. This is the first page where
the billing state machine (`SubscriptionService`, `Subscription.Status`) becomes
visible in the UI.

**Not in scope:** Overview dashboard (C6), any backend change beyond the single
scoped exception in §0, Stage D / Phase 2 (Stripe, invoices, usage metering,
webhooks, reconciliation).

**Deferred at C5, deliberately — subscription cancellation. RESOLVED by
`docs/cancellation-spec.md` (shipped 2026-09-07).** Cancellation is the one
irreversible action in the Phase 1 state machine, so at C5 it was held back for
its own deliberate confirmation-flow design rather than being appended to an
already-approved stage — the same treatment as the C2-reported logout and
current-user gaps that C3 §0 later closed. It now ships as an **OWNER-only
type-to-confirm flow** on `SubscriptionPage.tsx` (a danger-zone "Cancel
subscription" control on the panel → a modal that requires typing the workspace
name before the destructive button enables — the GitHub repo-deletion pattern).
It sends `PATCH /api/subscriptions/current/ {status: "CANCELED"}` through the
view's existing status branch — **no backend production change was needed**; the
permission (`IsTenantOwner` on PATCH), validation, and `LEGAL_TRANSITIONS` guard
were all already in place and tested, with three new API tests added to lock the
cancellation contract by name. The C5-era `§6` rule ("this page only ever sends
`plan_id`, never `status`") is now scoped: every *plan* action still sends
`plan_id` only; cancel is the sole `status` sender.

---

## 0. Backend Addendum — `change_plan` must reject `CANCELED` subscriptions

This stage is frontend-focused, but planning it surfaced a real backend
integrity gap, not just a UI question — the same pattern as C3's §0 backend
addendum (a small, explicit, justified backend change inside an otherwise
frontend stage).

**The gap:** `SubscriptionService.change_plan` (`apps/billing/services.py`) has
no status guard at all. `CANCELED` is documented and tested as terminal for
*status* transitions (`LEGAL_TRANSITIONS[CANCELED] = set()`,
`test_illegal_transition_returns_400_and_status_unchanged`), but nothing stops
`change_plan` from silently reassigning the `plan` field on a canceled
subscription — a canceled subscription changing plans makes no domain sense (it
has no active billing period to apply the change to) and the DB constraint is
not the seam that would catch it. This is the same class of bug the state
machine exists to prevent, just on the `plan` field instead of `status`.

**Required fix:**

1. `apps/billing/services.py` — `SubscriptionService.change_plan` raises
   `IllegalStateTransition` when `subscription.status ==
   Subscription.Status.CANCELED`, checked before any field is reassigned or
   saved. Reuse the existing `IllegalStateTransition` exception (don't invent a
   second error type for what is conceptually the same guarantee — "you cannot
   change a terminal subscription" — regardless of which field triggered it).
2. `apps/billing/views.py` — `CurrentSubscriptionView.patch`'s `plan_id` branch
   currently calls `SubscriptionService.change_plan` with no
   `try/except IllegalStateTransition` (only the `status` branch has one
   today). Add the same catch to the `plan_id` branch, returning `400` with a
   clear message (mirror the existing `{"status": [str(exc)]}` shape, e.g.
   `{"plan_id": [str(exc)]}` — verify which key reads correctly against the
   frontend's field-error handling before finalizing).
3. A new backend test in `apps/billing/tests/test_subscription_api.py`
   confirming: create a subscription, transition it to `CANCELED`
   (`SubscriptionService.transition_status`, same pattern
   `test_illegal_transition_returns_400_and_status_unchanged` already uses),
   then `PATCH .../current/` with a `plan_id` targeting a different active
   plan → `400`, and the subscription's `plan_id` is unchanged afterward
   (`refresh_from_db()` + assert, same shape as the existing illegal-transition
   test).

This is the **only** backend change permitted in this stage — everywhere else
in this document that says "no backend file" or "backend untouched" refers to
everything except these two files.

---

## 1. Objective

Every prior frontend stage consumed an endpoint that only ever returns one shape.
This page is the first to render a real state machine: a tenant may have **no**
subscription yet, or one in `TRIALING` / `ACTIVE` / `PAST_DUE` / `CANCELED` — and
`CANCELED` is **terminal**, with no reactivation path, by design (master spec
§B.5, enforced by `LEGAL_TRANSITIONS` in `apps/billing/services.py`). The page
must represent that terminality honestly rather than rendering a dead "Reactivate"
button. It's also the second consumer of `Table`'s mobile stacked-card transform
(built in C4) — the plan-card grid uses the same collapse-to-stack pattern at
narrower widths.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/project-master-spec.md            - §B.5 (subscription status state machine),
                                          §B.7 (route table)
docs/ui-design-specification.md        - §C.4 Page 4 (Subscription & Plans) —
                                          read the full block, including the
                                          Stage-B2 endpoint correction note
apps/billing/models.py                 - Plan, Subscription field names/choices —
                                          ground truth, don't assume field names
apps/billing/serializers.py            - exact output shape (PlanSerializer has
                                          NO is_active; SubscriptionSerializer has
                                          NO tenant field, nests plan)
apps/billing/views.py                  - CurrentSubscriptionView: GET is
                                          IsTenantMember, POST/PATCH is
                                          IsTenantOwner; 404 body shape;
                                          plan_id validation collapses "unknown"
                                          and "inactive" into the same 400; also
                                          gets the §0 IllegalStateTransition
                                          catch added to the plan_id branch —
                                          modified, not just inspected, this
                                          stage
apps/billing/services.py               - LEGAL_TRANSITIONS table (verify which
                                          transitions this page can ever trigger
                                          — see §6 below, most are NOT reachable
                                          from this UI); this file also gets the
                                          §0 change_plan guard — modified, not
                                          just inspected, this stage
apps/billing/tests/test_plan_api.py    - real request/response pairs for
                                          GET /api/plans/
apps/billing/tests/test_subscription_api.py - real request/response pairs for
                                          all three CurrentSubscriptionView verbs,
                                          including every error case; gains the
                                          §0 new test this stage
frontend/src/routes/MembersPage.tsx    - closest existing precedent: list + role-
                                          gated action + Table mobile transform
frontend/src/routes/WorkspacePage.tsx  - list/loading/empty/error pattern and the
                                          "prime cache then select" pattern for a
                                          just-created resource
frontend/src/components/Table.tsx      - renderMobileCard, already built in C4
frontend/src/lib/query-keys.ts         - queryKeys.plans() (global) and
                                          queryKeys.currentSubscription(tenantId)
                                          already defined, unused until now
frontend/src/lib/global-paths.ts       - /api/plans/ already listed as global;
                                          /api/subscriptions/current/ correctly
                                          absent (tenant-scoped)
frontend/src/routes/stubs.tsx          - current SubscriptionStub being replaced
frontend/src/routes/AppRoutes.tsx      - route wiring to update
```

Current state: AuthArtPanel redesign complete (`595ef5d`), frontend 188/188,
backend 70/70. Route stub currently reads "Subscription — built by /api/plans/
and /api/subscriptions/current/."

## 3. Existing Functionality That Must Not Change

- No backend file modified **except the two named in §0**
  (`apps/billing/services.py`'s `change_plan` guard and
  `apps/billing/views.py`'s corresponding `except` clause) — that is a scoped,
  explicit, justified exception, not a general license to touch the backend.
  Every other endpoint this stage consumes (`/api/plans/`, and
  `/api/subscriptions/current/`'s GET/POST behavior and every other PATCH path)
  is used exactly as it exists today.
- AuthProvider, TenantProvider, TopNavbar, AccountMenu, the query-key isolation
  mechanism, `Table.tsx`'s existing desktop/mobile behavior — untouched. This
  page composes existing primitives; it does not modify them.
- All 188 frontend and 70 backend tests must still pass.
- `queryKeys.plans()` and `queryKeys.currentSubscription()` already exist — use
  them as-is, don't rename or restructure.

## 4. Required Changes

### 4.1 Current subscription panel

- `GET /api/subscriptions/current/` — tenant-scoped (`X-Tenant-ID` via the
  existing API client). Query key: `queryKeys.currentSubscription(tenantId)`.
- **404 is not an error** — it means "no subscription yet," a legitimate empty
  state, not a fetch failure. Distinguish this from a real network/500 error
  (verify how `ApiError` surfaces status so the two don't collapse into the same
  branch).
- Ready state shows: plan name + code, formatted price (`price_cents`/100 +
  `currency`, never a hardcoded `$`, never a bare float division that loses
  cents — tabular-figure styling per the money-rendering convention already used
  elsewhere), status badge (§4.2 below), `current_period_start`/`current_period_end`
  formatted as dates.
- Empty (no subscription): "No active subscription" message. OWNER additionally
  sees a "Choose a plan" affordance (scrolls to or focuses the plan grid — no
  separate route). MEMBER sees the message with no action.
- Loading: skeleton panel matching the ready-state's shape.
- Error (genuine fetch failure, not 404): inline retry panel, consistent with
  other pages.

### 4.2 Status badge

- Map `Subscription.status` → Badge variant: `ACTIVE` → success, `TRIALING` →
  warning, `PAST_DUE` → danger, `CANCELED` → neutral.
- When `CANCELED`: no reactivate affordance anywhere on the page. This is not
  "disable the button" — there must be no button, because
  `LEGAL_TRANSITIONS[CANCELED]` is the empty set and no such transition exists
  server-side to attempt. Render the terminal state as informational only.

### 4.3 Plan grid

- `GET /api/plans/` — global path (already in `global-paths.ts`), already-active
  plans only (`PlanSerializer` never exposes `is_active` — the list is
  pre-filtered server-side, so there is no client-side active/inactive
  distinction to render). Query key: `queryKeys.plans()`.
- Cards: plan name, formatted price, `interval` (render literally —
  `MONTHLY`/`ANNUAL` — no toggle control; see §9 "not built now").
- `role="radiogroup"` semantics per the UI spec's accessibility note — cards are
  selectable, not independent buttons; the current plan (if any) renders as the
  selected radio, not merely highlighted.
- Loading: 3 skeleton cards. Empty (`[]`, no plans at all): "No plans available"
  — phrase this as an operational problem per the UI spec, not a cheerful "check
  back later." Error: inline retry.
- Table's `renderMobileCard` pattern doesn't directly apply here (this is a card
  grid, not a `Table`) — reuse the responsive breakpoints instead: 3-across
  desktop → 2 tablet → 1 mobile stacked, per the UI spec.

### 4.4 Select / change plan (OWNER only)

- Visible only when `useTenant().currentTenant.role === 'OWNER'` — same
  client-side-is-UX-only discipline as C4's "Add member" button; state this in
  a code comment at the point it's conditionally rendered.
- **No subscription yet** → clicking a plan card calls
  `POST /api/subscriptions/current/` with `{ plan_id }`. On success (`201`):
  refetch/update `queryKeys.currentSubscription(tenantId)`.
- **Subscription exists, different plan selected** → clicking that plan card
  opens a confirmation modal stating current plan, target plan, and that
  billing-period effects apply (per the UI spec's `confirm` requirement) —
  do not submit `PATCH` directly from the card click. On confirm:
  `PATCH /api/subscriptions/current/` with `{ plan_id }`. Verify from
  `test_owner_changes_plan` that the response is `200` with the updated
  subscription body.
- **Subscription exists, same plan clicked** → no-op (already selected; radio
  semantics mean re-selecting the current choice does nothing observable).
- Error surfaces (verify each against the real test file, don't assume the
  message text):
  - `403` (MEMBER attempts POST/PATCH despite the UI hiding the control, e.g. a
    stale render or role change mid-session) → inline alert, not a crash.
  - `400` unknown/inactive `plan_id` → field-level error
    (`{"plan_id": ["No active plan with this id."]}`).
  - `400` creating when one already exists → surface the `detail` message
    verbatim (`"...use PATCH to change it."`) — this indicates a client-side
    state bug (the page thought there was no subscription) more than a user
    error, so log/report it distinctly if you have a mechanism for that,
    otherwise just show the message.
  - `400` illegal status transition — **not reachable from this page's UI at
    all**, since this page never sends a `status` field, only `plan_id`. Do not
    build any control that could trigger it. See §6.
  - `400` §0's `IllegalStateTransition` on a `CANCELED` subscription's
    `plan_id` change — **is** reachable if the UI's hide/disable logic (§8) has
    a gap or races; handle it the same as the other field-level 400s rather
    than assuming it can't happen.
- Success (either verb): close any open modal, current-subscription panel
  reflects the new state, plan grid's selected radio updates.

## 5. Files Likely Affected

```
new:      frontend/src/routes/SubscriptionPage.tsx (replaces SubscriptionStub)
          frontend/src/routes/ChangePlanConfirmModal.tsx (or co-located)
          tests for the above
modified: frontend/src/routes/AppRoutes.tsx (SubscriptionPage replaces the stub)
          frontend/src/routes/stubs.tsx (remove SubscriptionStub + its export)
          apps/billing/services.py (§0 change_plan CANCELED guard)
          apps/billing/views.py (§0 IllegalStateTransition catch on the plan_id
          branch)
          apps/billing/tests/test_subscription_api.py (§0 new test)
```

No backend file beyond the three named above. No change to `Table.tsx`,
`query-keys.ts`, or `global-paths.ts` — all three already carry what this page
needs.

## 6. Business Rules

- `tenant_id` never appears in any request body from this page. As of C5,
  `plan_id` was the only field this UI sent. **Updated by
  `docs/cancellation-spec.md`:** the page now also sends
  `{status: "CANCELED"}` — but *only* from the cancel flow, and *only* that one
  value. `CurrentSubscriptionView.patch` accepts `status` for other legal
  transitions (`TRIALING`→`ACTIVE`, `ACTIVE`→`PAST_DUE`, …), and those remain
  billing-cycle events, not something an OWNER clicks — no control on this page
  constructs any `status` value other than `CANCELED`.
- `CANCELED` is terminal — verified by `test_illegal_transition_returns_400_and_status_unchanged`.
  No UI path may attempt to leave `CANCELED`.
- Plan selection always targets `request.tenant` from the header; this page
  never constructs a tenant field.

## 7. Security Requirements

- Client-side hiding of plan-selection controls for a MEMBER is UX, not
  authorization — `IsTenantOwner` is the real boundary (verified by
  `test_member_cannot_create_and_gets_403` / `test_member_cannot_update_and_gets_403`).
  State this in a code comment at the point the controls are conditionally
  rendered, same as C4.
- No payment-method UI, no card/CVV fields anywhere — Stripe owns payment
  collection in Phase 2 (CLAUDE.md). This page only ever sends a `plan_id`.

## 8. Edge Cases

- MEMBER views the page with an existing subscription — panel and plan grid
  render read-only, no selection controls, and if they somehow reach a mutation
  (stale render / role change mid-session) the server's 403 is handled inline,
  not a crash.
- Tenant has no subscription — panel shows the empty state; OWNER can create
  one directly from the plan grid without a separate "create" step.
- Tenant's subscription is `CANCELED` — plan grid still renders (so an OWNER can
  see what's available) but **no selection control is interactive**: `POST`
  would hit `SubscriptionAlreadyExists` (`400`, unchanged, pre-existing
  behavior) and `PATCH` now hits the §0 guard (`400`,
  `IllegalStateTransition`) rather than silently reassigning the plan. Per this
  project's client-side-hiding-is-convenience-not-security pattern (used
  identically for C4's OWNER-only "Add member" button and this page's own
  MEMBER-vs-OWNER controls), the frontend should hide/disable plan selection
  when `status === 'CANCELED'` as UX — the actual boundary is the backend
  guard from §0, and if a stale render or race lets a request through anyway,
  the `400` must be handled inline, not crash.
- Switching tenant while on this page — both the subscription panel and the
  plan grid must refresh correctly (`queryKeys.plans()` is global and should
  NOT refetch on tenant switch; `queryKeys.currentSubscription(tenantId)` IS
  tenant-scoped and MUST refetch) — this is the page-level proof that a page
  mixing a global and a tenant-scoped query respects both halves of the C2
  isolation mechanism at once, which no prior page has exercised.
- Confirmation modal dismissed without confirming — no request sent, selection
  reverts to the actual current plan.
- Money formatting at `price_cents` boundary values (e.g. `0`, or non-round
  numbers if any test plan uses them) — verify no rounding/truncation bug.

## 9. Tests Required

- Current-subscription panel: ready (with real data), 404-as-empty (not error),
  genuine-error, loading — all four rendered distinctly.
- Status badge: all four `Subscription.Status` values map to the correct Badge
  variant; `CANCELED` renders with no reactivate control present (an assertion
  on absence, not just that the happy path works — same discipline as C4's
  "no role field" test).
- Plan grid: loading/empty("No plans available")/error/ready.
- OWNER, no subscription: selecting a plan calls `POST` with the right
  `plan_id`, success updates the panel.
- OWNER, existing subscription, different plan: opens confirmation modal first;
  confirming calls `PATCH`; dismissing sends nothing.
- MEMBER: no selection controls render at all, for both the empty and existing-
  subscription cases.
- Error surfaces: 403 on a stale-render mutation attempt, 400 unknown/inactive
  `plan_id`, 400 already-exists `detail` message — each renders distinctly and
  without crashing.
- Tenant switch while on this page: plan grid does NOT refetch (global), current
  subscription DOES refetch (tenant-scoped) — the mixed-query-type isolation
  proof from §8.
- No control on the page can ever construct a request body containing `status`
  (an assertion on absence, verifying §6's constraint holds in the actual
  component tree, not just in the plan).

## 10. Acceptance Criteria

1. `npm run build` clean.
2. `npm test` — all previous tests pass plus new ones, exact count reported.
3. `npm run lint` clean.
4. `.venv/Scripts/python.exe manage.py test` — **must be re-run and its real
   output reported, not "confirmed unaffected."** Expected: 71/71 — 70 prior
   plus the §0 new test. This stage is the first since C3 §0 to touch a
   backend file, so "should still pass" is not sufficient; run it.
5. Manual walkthrough, screenshotted, both themes, both roles, and all four
   subscription states reachable in the seeded data (create at least one
   `CANCELED` subscription via Django shell/fixture if the demo tenants don't
   already have one — don't skip verifying the terminal state visually):
   no-subscription empty state, plan selection creating one, plan grid,
   change-plan confirmation flow, `CANCELED` terminal rendering, mobile
   card-stack plan grid, a live tenant switch confirming the mixed
   global/tenant-scoped refetch behavior.
6. `git status` — no file outside `frontend/`.
7. Report: how the 404-vs-error distinction was implemented (verify against
   real `ApiError` shape, don't assume), and which response key §0's new
   `IllegalStateTransition` catch uses on the `plan_id` branch
   (`{"plan_id": [...]}` vs. reusing `{"status": [...]}` or another shape) and
   why, plus confirmation the frontend's error handling reads that exact key.

## 11. Must NOT Do

- Do not build a monthly/annual toggle control (no UI spec requirement exists
  for switching between intervals as a user action — `interval` is
  display-only on this page).
- Do not build a feature-comparison matrix (`Plan` has no feature-list field).
- Do not build any payment-method form or card input.
- Do not render a reactivate control for `CANCELED` subscriptions under any
  circumstance.
- Do not construct a request body containing `status` anywhere on this page.
- Do not build the Overview dashboard (C6).
- Do not modify any backend file **except the two named in §0**
  (`apps/billing/services.py`, `apps/billing/views.py`) plus the one new test
  in `apps/billing/tests/test_subscription_api.py` — no other backend file,
  and no other change to those two files beyond what §0 specifies.
- Do not modify `Table.tsx`, `query-keys.ts`, `global-paths.ts`, AuthProvider,
  TenantProvider, TopNavbar, or AccountMenu.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

Read docs/stage-c5-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.

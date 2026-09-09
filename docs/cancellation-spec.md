# Claude Code Implementation Specification — Subscription Cancellation

**Scope:** the OWNER-only action to cancel a subscription, deliberately deferred
at Stage C5 specifically so it could get its own careful confirmation-flow
design rather than being appended to an already-approved plan. CANCELED is
terminal - no reactivation path exists anywhere in the state machine - so this
is the one place in the entire product where the UI must go out of its way to
prevent an accidental click from causing irreversible harm.

**Not in scope:** Razorpay/Stage D, the Platform Admin dashboard (already
done), any reactivation path (none exists, none should be implied).

---

## 1. Objective

Master spec section B.6 lists cancel as an OWNER subscription capability, and
SubscriptionService.cancel_subscription (built in B2) already enforces the
legal transitions (TRIALING/ACTIVE/PAST_DUE -> CANCELED). What's
missing is the UI action itself and a confirmation flow serious enough to
match the stakes - this is not "are you sure?" territory, it's "type
something to prove you mean it" territory, the same category of friction
GitHub uses for repo deletion.

Honesty requirement, stated up front: this project has no real payment
processor integrated yet (that's Stage D). Cancelling here does NOT
stop a real charge, does NOT trigger a real refund, and does NOT
currently restrict access to any feature in the app (verify this - if some
access gate does exist somewhere by this point, the confirmation copy must
say so accurately; if not, don't invent a consequence that doesn't happen).
The confirmation copy must describe only what actually happens: the
subscription's status becomes CANCELED in this system, permanently, with
no path back except creating a new subscription later - not any claims
about payment, refunds, or feature access that aren't real yet.

## 2. Inspect Before Implementing — verify before assuming

```
CLAUDE.md
docs/stage-c5-spec.md                  - the original deferral note; this
                                          stage resolves it, update that
                                          doc's "not in scope" block to say
                                          so rather than leaving it looking
                                          perpetually deferred
docs/project-master-spec.md section B.6 - the deferred-cancel note added
                                          when C5 shipped; update similarly
apps/billing/services.py               - SubscriptionService.cancel_subscription
                                          and LEGAL_TRANSITIONS - confirm
                                          exactly what's already enforced,
                                          don't assume
apps/billing/views.py                  - CurrentSubscriptionView.patch's
                                          status-branch handling - verify
                                          whether PATCH .../current/ with
                                          {status: "CANCELED"} already works
                                          correctly today at the API layer
                                          (B2 likely tested the service
                                          layer; confirm whether the view
                                          layer's status branch was ever
                                          exercised by an existing test, or
                                          if this stage is the first real
                                          caller). Report which is true -
                                          this determines whether this stage
                                          needs any backend work at all
                                          beyond what's already tested.
apps/billing/tests/test_subscription_api.py - existing status-transition
                                          tests, if any exist already
frontend/src/routes/SubscriptionPage.tsx - already renders CANCELED
                                          correctly (neutral badge, no
                                          reactivate control per C5) - this
                                          stage adds the cancel action for
                                          non-canceled subscriptions; don't
                                          re-do what C5 already built
                                          correctly
frontend/src/routes/OverviewPage.tsx   - already shows "Period ended"
                                          copy for CANCELED (per C6) -
                                          confirm this still reads correctly
                                          after this stage, no change
                                          expected but verify
frontend/src/lib/format.ts             - reuse existing formatters, no new
                                          ones needed
```

Current state: Platform Admin dashboard complete and committed. Backend
117/117, frontend 267/267.

## 3. Existing Functionality That Must Not Change

- SubscriptionService's existing transitions, LEGAL_TRANSITIONS,
  IllegalStateTransition - untouched unless a genuine gap is found per
  section 2's verification step.
- SubscriptionPage.tsx's existing rendering of every status (including
  CANCELED's current "no reactivate control" behavior) - this stage adds
  one new action for the pre-cancellation states; it doesn't redesign
  anything C5 already built correctly.
- OverviewPage.tsx's existing CANCELED handling - verify unaffected.
- All existing tests must still pass.

## 4. Required Changes

### 4.1 Backend (only if section 2's verification finds a real gap)

If PATCH /api/subscriptions/current/ with {status: "CANCELED"} doesn't
already work correctly and safely at the API layer (permission-checked,
validated, tested), close that gap - following the exact same shape as
every other transition already handled there. Do not assume this needs
backend work; verify first and report which is true.

### 4.2 Frontend — the cancel action

On SubscriptionPage.tsx, for a subscription in a cancellable state
(TRIALING/ACTIVE/PAST_DUE) and only for OWNER (same "client-side
hiding is UX, IsTenantOwner is the real boundary" comment discipline as
every other role-gated control in this app): a "Cancel subscription"
action, visually distinct from the primary actions on the page (a
danger-variant control, not styled like the plan-selection cards) - this
should not compete visually with or be easy to confuse with routine
actions like changing plans.

### 4.3 The confirmation flow — deliberately higher friction than PlanConfirmModal

Given this is the one irreversible action in the entire product, a plain
"Are you sure?" modal (the pattern used for plan changes) is NOT
sufficient. Build a type-to-confirm pattern: the modal states plainly
what will happen (per section 1's honesty requirement - no invented
consequences), and requires the user to type an exact confirmation string
(e.g. the tenant's name, or the literal word "CANCEL") into a field before
the destructive action button becomes enabled. This is a recognized,
appropriate pattern for irreversible actions (the same category as GitHub's
repository-deletion confirmation) - don't substitute a lighter pattern to
save implementation time.

On success: the page reflects the new CANCELED state using
SubscriptionPage's existing rendering (no new UI needed there - it
already handles this status correctly per C5). Close the modal, show the
result plainly.

### 4.4 Copy — verify honesty against actual app behavior

Before finalizing the confirmation modal's exact wording, check whether
any real access restriction exists anywhere in the app tied to
subscription status. If none exists (expected, given no such gating has
been built), the copy must not claim one - no "you'll lose access to
members/billing" language unless that's actually true. State only real,
verifiable consequences: the subscription becomes CANCELED, permanently,
in this system, and a new subscription would need to be created to resume
billing (verify this last part too - does creating a new subscription
after cancellation work correctly today? SubscriptionService.create_subscription
should handle this, but confirm rather than assume).

## 5. Files Likely Affected

```
modified: frontend/src/routes/SubscriptionPage.tsx (cancel action added)
new:      frontend/src/routes/CancelSubscriptionModal.tsx (or co-located)
          tests for the above
modified: docs/stage-c5-spec.md (mark the deferral resolved)
          docs/project-master-spec.md section B.6 (mark the deferral resolved)
          apps/billing/views.py, tests/ (only if section 2 finds a real gap)
```

## 6. Business Rules

- CANCELED remains terminal - this stage must not introduce any
  reactivation path, implied or actual.
- The confirmation copy makes no claim about payment, refunds, or feature
  access that isn't genuinely true of this system today.
- tenant_id never appears in any request body from this action.

## 7. Security Requirements

- IsTenantOwner (or equivalent) is the real boundary for the cancel
  endpoint - verified by a test, not assumed from the frontend hiding the
  button.
- A MEMBER attempting this action via a stale render or direct API call
  gets a clean 403, not a crash.

## 8. Edge Cases

- Attempting to cancel an already-CANCELED subscription (e.g. via a
  stale render or a race) - the existing LEGAL_TRANSITIONS guard should
  already reject this; confirm the frontend surfaces that error cleanly
  rather than crashing.
- The confirmation modal is dismissed without completing the type-to-confirm
  step - no request sent, no state change.
- Cancelling, then later creating a new subscription - confirm this works
  end-to-end (section 4.4) and that SubscriptionPage/OverviewPage both
  reflect the new, non-canceled state correctly afterward.

## 9. Tests Required

- Backend (if section 2 finds work is needed): the transition succeeds for
  each legal starting status, is rejected for CANCELED -> CANCELED, and is
  rejected for a MEMBER (403).
- Frontend: the cancel action is visible only for OWNER on a cancellable
  status; the confirm button stays disabled until the exact confirmation
  string is typed; a successful cancellation updates the page to the
  correct terminal rendering; a dismissed modal sends no request.

## 10. Acceptance Criteria

1. manage.py test, npm test - full counts reported.
2. npm run build, npm run lint - clean.
3. Manual walkthrough, screenshotted, both themes: cancel a real
   subscription through the full flow (including the type-to-confirm
   step), confirm the resulting terminal state renders correctly on both
   SubscriptionPage and OverviewPage, and confirm a MEMBER never sees
   the action.
4. docs/stage-c5-spec.md and the master spec's section B.6 note both
   updated to reflect the deferral is now resolved.
5. Report: whether backend work was actually needed (per section 2), and
   confirmation the modal's copy was checked against real app behavior,
   not assumed.

## 11. Must NOT Do

- Do not build any reactivation path.
- Do not use a plain "are you sure?" modal for this action - type-to-confirm
  is required, per section 4.3.
- Do not claim any consequence (refund, access loss) in the UI copy that
  isn't genuinely true of the app today.
- Do not start Razorpay/Stage D.
- Do not weaken any existing test.

---

## Workflow

Produce a plan first and wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

Read docs/cancellation-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.

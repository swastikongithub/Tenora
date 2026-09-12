# Tenora — Remaining Production Roadmap Master Plan

## Purpose

This document is the execution contract for Claude Code to finish the remaining Operator Control Plane work and close the current production roadmap with minimal interactive prompting.

Claude Code should treat this file as the primary execution brief for the remaining phases. Read the repository and existing specification first, reconcile this document with the actual codebase, then implement the remaining phases end-to-end.

The user intends to use a high-reasoning Opus model for this work and wants a single, autonomous execution pass rather than repeated prompt/approval cycles.

---

# 0. NON-NEGOTIABLE EXECUTION RULES

## 0.1 Preserve the existing architecture

Do not redesign working architecture merely because a different approach is possible.

The following are already established and must remain intact unless a concrete defect makes a change necessary:

- Django 5 + DRF backend.
- PostgreSQL database.
- SimpleJWT authentication.
- `X-Tenant-ID` tenant selection at the authentication layer.
- Explicit tenant-scoped querying; no thread-local tenant state.
- Existing password authentication.
- Existing Google Identity Services authentication.
- Existing email verification semantics.
- Provider-neutral payment-gateway abstraction.
- Existing Subscription/Plan/domain services.
- Existing Celery/Redis infrastructure and conventions.
- Existing Operator Control Plane authorization boundaries.
- Existing audit architecture introduced in Operator Control Plane Phase 2.

Do not introduce a parallel architecture when an established repository abstraction already exists.

## 0.2 Do not regress completed work

Completed and accepted work includes:

- Production bootstrap/superuser mechanism.
- Operator Control Plane Phase 1.
- Operator Control Plane Phase 2 implementation.
- Authentication UI improvements.
- Google login UI treatment.
- Provider-neutral email delivery abstraction.

Phase 2 implementation already exists in commit `4096a54` and is present in the current repository history. Do NOT reimplement Phase 2 from scratch.

Current HEAD has later authentication/email commits as well. Inspect the actual repository rather than relying on commit order assumptions.

## 0.3 Payment architecture remains provider-neutral

Use only generic terminology at the platform level:

- Payment Gateway
- Gateway Adapter
- External Plan ID
- External Subscription ID
- External Event ID
- Gateway Sync
- Gateway Webhook

Do not couple new platform/business logic to a specific payment provider.

A concrete provider may appear only inside its isolated adapter implementation.

## 0.4 Tenant isolation and JWT semantics are frozen

Do not change:

- `X-Tenant-ID` semantics.
- JWT claims/issuance semantics.
- Tenant isolation behavior.
- Tenant-scoped manager/query patterns.
- Authentication boundary behavior.

If a Phase requires tenant suspension enforcement, integrate it at the existing authentication boundary rather than creating a parallel authorization system.

## 0.5 No routine permission prompting

For normal development work, proceed autonomously without repeatedly asking for approval for:

- repository inspection
- source edits
- tests
- static checks
- local database reset/migration checks where explicitly safe
- frontend builds
- backend builds/checks
- git diff/status/log
- local development commands
- creating migrations
- normal refactors needed to satisfy this plan

Do not repeatedly stop for "Allow", "Submit", or similar routine confirmations when the action is a normal part of this implementation task.

## 0.6 Stop only for genuinely dangerous or impossible conditions

Pause and report before:

- destructive production data deletion
- irreversible production migrations when a safe rollout cannot be established
- exposing secrets/credentials
- changing production infrastructure in a way that cannot be rolled back
- making a production mutation that is not part of the approved feature scope
- force-pushing or rewriting Git history
- deleting customer/tenant/payment data
- inventing missing business rules that are not inferable from the repository/spec

Do not stop for minor design ambiguity if the existing architecture, spec, and code make the intended behavior clear. Choose the least surprising implementation and document the decision.

## 0.7 Git discipline

Do not stage or commit unrelated files.

The repository has a pre-existing untracked root `package-lock.json`. Leave it untouched unless the repository itself now clearly requires it and a separate decision is made.

Use one logical commit per major phase. Never bundle unrelated cleanup into a feature commit.

Do not rewrite published history.

---

# 1. CURRENT REPOSITORY STATE

The following is the expected high-level state. Verify it directly before acting.

Known commits:

- `2e41065` — production bootstrap fix.
- `4e614b5` — Operator Control Plane Phase 1.
- `4096a54` — Operator Control Plane Phase 2 implementation.
- `5268b7f` — authentication/email-delivery configuration + Google auth UI improvements.
- `0ecb3da` — provider-neutral transactional email delivery abstraction with optional Brevo provider.

Current HEAD was most recently verified as `0ecb3da`.

Do not assume these SHAs are still the exact repository state. Run:

```bash
git status --short
git branch --show-current
git log --oneline --decorate -12
git rev-parse HEAD
git rev-parse origin/master
```

Confirm whether local `master` and `origin/master` are synchronized before new work.

Then inspect:

- `docs/operator-control-plane-spec.md`
- current backend operator/platform routes
- platform services
- audit models/services
- platform frontend pages/layout/navigation
- billing/subscription domain services
- payment gateway abstraction and adapters
- tenant authentication code
- existing tests for all of the above

---

# 2. PHASE STATUS

## Phase 0 — Production bootstrap

Status: COMPLETE.

Do not rework unless a real regression exists.

## Phase 1 — Operator Control Plane read-only surface

Status: COMPLETE.

Do not redesign.

## Phase 2 — Controlled mutations + audit infrastructure

Status: IMPLEMENTED and already in Git history.

Known implementation commit: `4096a54`.

Required behavior already includes:

- subscription overrides
- controlled subscription mutation
- fallback webhook sweep trigger
- fallback reconciliation sweep trigger
- fallback usage sweep trigger
- sweep throttling
- `AuditEvent`
- critical/observational audit recording
- audit-log API
- audit-log UI
- confirmation-before-mutation UI
- staff/root boundary handling

Do not reimplement Phase 2.

However, before beginning Phase 3, verify that Phase 2 remains intact after later authentication/email changes. Run the existing test suite and inspect diffs affecting `apps/platform`, billing, tenants, and the Phase 2 frontend.

Production verification of privileged UI may be limited by lack of a shared browser session. Do not fake a successful authenticated production check. Clearly distinguish automated verification from authenticated manual verification.

---

# 3. PHASE 3 — PLAN & PRICING MANAGEMENT

## Objective

Turn the existing operator control plane into the system of record for platform billing plans/pricing management while preserving provider-neutral gateway boundaries and immutable external identifiers.

## 3.1 Inspect before implementing

Identify the exact existing models/services for:

- billing plans
- pricing fields
- external plan identifiers
- subscription references to plans
- payment-gateway adapters
- any existing gateway sync helpers
- existing plan/subscription tests

Do not create duplicate plan or pricing models if the repository already has the required domain entities.

## 3.2 Required capabilities

Implement through the first-party operator UI and corresponding backend endpoints:

1. List plans.
2. View plan details.
3. Create a plan when permitted by the domain rules.
4. Edit mutable plan/pricing fields.
5. Archive a plan without deleting historical billing data.
6. Synchronize a plan with the configured payment gateway through the existing adapter boundary.
7. Show synchronization state/result clearly to the operator.
8. Prevent unsafe mutation of immutable external identifiers once set.

## 3.3 Plan immutability rule

Once a plan has an `external_plan_id`, treat that external identifier as immutable.

Do not silently replace an external plan ID.

If the gateway provider requires a new external plan for a material pricing change, model the correct lifecycle rather than mutating the identifier in place.

The platform-level API should remain provider-neutral.

## 3.4 Gateway sync behavior

Use the existing gateway interface rather than calling a concrete provider directly from platform routes/views.

Operator flow should be conceptually:

```text
Operator UI
  -> Platform API
    -> Domain/service layer
      -> Payment Gateway Adapter
        -> External gateway
```

Normalize provider-specific results at the adapter boundary.

Do not expose raw provider payloads in routine plan management responses.

## 3.5 Authorization

Routine plan/pricing management is Staff-tier unless the existing approved spec explicitly reserves a specific mutation for Root.

Root-only operations remain Root-only.

Every privileged mutation must be auditable.

## 3.6 API design

Follow existing operator route conventions.

Do not introduce arbitrary endpoint patterns when the codebase already has a platform API style.

Validate all IDs and mutable fields server-side.

Never accept tenant IDs or security-sensitive ownership fields from the client when the server already knows them from authenticated context.

## 3.7 UI requirements

Use the established `/admin` operator layout.

Add a dedicated Plans/Pricing section that is consistent with existing Phase 1/2 pages.

Required UX:

- table/list view
- plan detail
- create form
- edit form for mutable fields
- archive action with confirmation
- gateway sync action with confirmation where it causes an external side effect
- clear state for active/archived/sync status
- disabled controls for immutable fields
- success/error feedback

Do not redesign the broader admin shell.

## 3.8 Audit requirements

Record at minimum:

- plan creation
- pricing changes
- archive
- gateway sync request/result
- failed privileged mutations when the existing audit pattern supports this

Include enough metadata for an operator to understand what changed without storing secrets or raw credentials.

## 3.9 Tests

Backend tests must cover:

- staff authorization
- root restrictions where applicable
- plan creation
- plan edits
- archive behavior
- immutable external plan ID
- gateway sync success
- gateway sync failure
- provider-neutral service behavior
- audit events
- malicious/invalid payloads
- duplicate plan edge cases if the domain defines uniqueness

Frontend tests must cover:

- plan list
- plan detail
- create/edit/archive controls
- confirmation dialogs
- disabled immutable fields
- sync action states
- authorization/UI visibility

Run the full backend suite and full frontend suite.

## 3.10 Definition of done

Phase 3 is complete only when:

- code is implemented
- migrations are correct
- tests pass
- Django checks pass
- frontend build passes
- provider-neutral boundary is preserved
- audit coverage is present
- no tenant/JWT regression exists
- git diff is clean
- one logical commit is created
- production deployment is performed only if the deployment path is already established and safe

---

# 4. PHASE 4 — ROOT CONTROLS

## Objective

Complete the Root-only operational security controls without weakening Staff privileges or creating self-lockout conditions.

## 4.1 Root definition

Root is:

```text
is_staff = True
AND
is_superuser = True
AND
is_active = True
```

Use the existing repository convention if equivalent helper logic already exists.

## 4.2 Operator role management

Provide first-party operator controls to:

- view operators
- promote a user to Staff
- demote Staff
- promote to Root when authorized
- demote Root when authorized
- deactivate an operator if permitted by the approved model

Do not expose password reset or identity-management functionality unless it is explicitly part of the existing architecture.

## 4.3 Last-root invariant

No mutation may result in zero active Root users.

Before performing any mutation, compute the resulting active Root count and reject operations that would leave zero.

Test:

- deleting/removing the only Root must fail
- demoting the only Root must fail
- deactivating the only Root must fail
- demoting a Root when another Root exists can succeed
- promotion to Root works when authorized

## 4.4 Authorization

Only Root can perform Root-only actions.

A Staff user must receive the correct authorization response and must not be able to bypass the API using direct IDs or alternate routes.

Do not rely on frontend hiding as the security control.

## 4.5 Raw webhook payload visibility

Expose raw webhook payload only through Root-protected functionality if the approved spec requires it.

Do not expose secrets, credentials, signatures, or unrelated private data.

Preserve provider-neutral platform terminology.

## 4.6 Audit

Audit every Root-only mutation.

Audit metadata should include:

- actor
- target
- action
- timestamp
- safe summary of the change

Never record passwords, tokens, API keys, webhook secrets, or full sensitive payloads unless the approved spec explicitly and safely requires a specific redacted representation.

## 4.7 UI

Create a Root Controls section under `/admin`.

Show Root-only navigation/action surfaces only to Root users, but preserve server-side enforcement regardless of UI visibility.

Use explicit confirmations for dangerous role changes.

## 4.8 Tests

Backend:

- Staff cannot perform Root operations
- Root can perform allowed Root operations
- last-root invariant
- invalid target IDs
- inactive users
- self-role changes
- audit events
- raw webhook authorization
- privilege escalation attempts

Frontend:

- Root controls visible only to Root where appropriate
- confirmation flows
- error handling
- unauthorized responses handled safely

Full suites required.

---

# 5. PHASE 5 — TENANT SUSPEND / REACTIVATE

## Objective

Add a first-party operator control for tenant suspension/reactivation and enforce suspension at the existing tenant authentication boundary.

## 5.1 Domain model

Use the existing Tenant model/fields if an equivalent lifecycle state exists.

If a new field is required, use the narrowest compatible addition, such as an explicit active/suspended state rather than overloading unrelated flags.

Do not create a second tenant status system if one already exists.

## 5.2 Operator capabilities

Staff or Root authorization should follow the approved operator permission model.

Provide:

- tenant status visibility
- suspend action
- reactivate action
- confirmation for both mutations
- audit event for both mutations

## 5.3 Authentication enforcement

Integrate the suspension check into the existing `TenantJWTAuthentication` flow.

Do not create a separate middleware/authentication stack.

Expected behavior:

```text
Authenticated user
  -> tenant selected via existing X-Tenant-ID mechanism
  -> tenant status checked
  -> if suspended: deny normal tenant access
  -> if active: continue existing authentication flow
```

Preserve current JWT semantics.

Do not alter tenant IDs in tokens or invent new authentication claims unless absolutely required by the existing design.

## 5.4 Suspended behavior

Define one consistent API response for suspended-tenant access according to existing authentication error conventions.

Do not leak unnecessary information.

Ensure platform-operator functionality remains usable for inspecting/managing the suspended tenant where the existing architecture permits it.

Do not accidentally lock operators out of the control plane because a customer tenant is suspended.

## 5.5 Tests

Backend must prove:

- active tenant remains accessible
- suspended tenant is blocked
- reactivated tenant works again
- invalid tenant ID behavior remains unchanged
- cross-tenant access remains blocked
- operator can suspend/reactivate only with correct permissions
- audit events are produced
- normal JWT semantics remain intact

Include regression tests around `X-Tenant-ID`.

Frontend:

- tenant status displayed
- suspend/reactivate confirmations
- correct state labels
- authorization handling

---

# 6. PHASE 6 — REAL WORKER / SCHEDULER ARCHITECTURE

## Objective

Replace the Phase 2 fallback sweep buttons with real asynchronous worker/scheduler execution where the existing infrastructure supports it.

This is the most operationally significant phase and must be implemented without silently breaking the existing fallback controls.

## 6.1 Inspect existing infrastructure first

Use the repository's existing Celery/Redis conventions.

Inspect:

- Celery app initialization
- task discovery
- worker configuration
- Redis configuration
- deployment services
- existing asynchronous jobs
- billing/webhook/reconciliation/usage services

Do not invent a second queue technology.

## 6.2 Jobs to schedule

At minimum, determine the correct cadence and execution architecture for:

- webhook processing
- reconciliation
- usage sweep/aggregation

Use idempotent task design.

A task must be safe to retry.

## 6.3 Idempotency

Each task must be safe when:

- executed twice
- retried after a timeout
- partially completed
- delayed
- executed after a previous successful attempt

Use existing event IDs, subscription identifiers, timestamps, or other domain keys where appropriate.

Do not create duplicate billing events as a side effect of retry behavior.

## 6.4 Locking/concurrency

Prevent concurrent workers from executing the same logical sweep in conflicting ways.

Use the existing database/queue primitives rather than a custom in-memory lock that fails across processes.

## 6.5 Observability

Record task success/failure through the existing audit/operational pattern without flooding the audit log with meaningless noise.

Distinguish:

- critical operator-visible events
- observational operational events

## 6.6 Fallback controls

Do not immediately delete the existing manual sweep controls.

Keep them available as a controlled fallback until the scheduler has been validated in production.

Only after the scheduled path is demonstrably stable should the UI/spec be updated to reduce or remove manual fallback controls.

## 6.7 Failure handling

A failed scheduled task must:

- be retryable where appropriate
- not silently disappear
- surface enough information for operator investigation
- not expose credentials or sensitive provider payloads

## 6.8 Tests

Cover:

- task registration/discovery
- correct schedule configuration
- idempotency
- retries
- duplicate execution
- concurrency behavior
- audit/observability behavior
- failure handling
- existing manual fallback behavior remains valid

If production workers/scheduler cannot be enabled safely on the current Render plan, do not fake the capability. Implement the application-side task architecture and document the deployment prerequisite.

---

# 7. CROSS-PHASE SECURITY REQUIREMENTS

These apply to every remaining phase.

## 7.1 Authorization is server-side

Never trust frontend route guards or hidden buttons as security.

Every privileged endpoint must enforce the correct role server-side.

## 7.2 No insecure object-level access

For IDs supplied by clients:

- validate existence
- validate ownership/relationship
- validate operator permission
- return the repository's standard not-found/forbidden behavior

Do not accidentally turn an ID into an authorization bypass.

## 7.3 Audit critical mutations

Every privileged state-changing action introduced by these phases must go through the established audit mechanism.

## 7.4 No secrets in code or logs

Never commit:

- API keys
- SMTP passwords
- JWT secrets
- webhook secrets
- provider credentials

Never log them.

## 7.5 No raw provider coupling

External provider details belong only behind the adapter boundary.

## 7.6 No accidental tenant crossover

Every tenant-sensitive operation must preserve the existing tenant isolation contract.

---

# 8. MIGRATION POLICY

For every migration:

1. Inspect current schema.
2. Determine whether data already exists.
3. Make the migration safe for current data.
4. Test locally with the repository's established reset/migration workflow.
5. Verify `makemigrations --check --dry-run` is clean.
6. Run relevant backend tests.
7. Never use production-destructive shortcuts.

Do not squash or rewrite old migrations merely for cosmetic cleanliness.

If an existing table/field already expresses the required concept, evolve it instead of introducing a parallel representation.

---

# 9. API & FRONTEND CONSISTENCY

For every new endpoint:

- use repository-standard URL conventions
- use standard validation/error response shape
- maintain consistent pagination where applicable
- return safe representations
- do not leak internal provider payloads

For every new frontend feature:

- use existing operator layout/components/design system
- preserve accessibility
- preserve keyboard/focus behavior
- avoid unrelated redesign
- ensure loading, success, error, and disabled states are implemented

---

# 10. TESTING CONTRACT — REQUIRED AFTER EACH PHASE

After each phase implementation:

### Backend

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Run focused tests first, then the full suite.

### Frontend

Run the full existing frontend test suite.

Run:

```bash
npm test
npm run build
```

Use the actual project scripts if names differ.

### Git

```bash
git diff --check
git status --short
git diff --stat
```

Do not commit if tests/checks are failing unless the failing test is a clearly identified pre-existing unrelated failure, and document it explicitly.

---

# 11. EXECUTION ORDER

Execute in this order:

## Step 1 — Repository reconnaissance

Verify actual state and read the existing operator-control-plane spec and implementation.

## Step 2 — Phase 2 regression gate

Confirm Phase 2 remains intact after later commits.

Do not reimplement it.

## Step 3 — Phase 3

Plan/pricing management.

## Step 4 — Phase 4

Root controls.

## Step 5 — Phase 5

Tenant suspend/reactivate.

## Step 6 — Phase 6

Worker/scheduler architecture.

## Step 7 — Final end-to-end regression

Run:

- backend full suite
- frontend full suite
- Django check
- migration check
- frontend production build
- diff check

Then perform a final security/architecture audit across all changed files.

---

# 12. COMMIT STRATEGY

Use separate commits:

```text
feat: complete operator plan and pricing management
feat: add root operator controls
feat: add tenant suspension controls
feat: add scheduled billing operations
```

Exact wording may be adjusted to match repository conventions.

Do not combine all phases into one giant commit.

Before each commit:

- run relevant tests
- inspect `git diff`
- stage only intentional files
- never stage root `package-lock.json` unless explicitly required

After each commit:

- report SHA
- report test results
- report working tree status

Push only after the commit is internally validated and the repository is not in a conflicted state.

---

# 13. PRODUCTION DEPLOYMENT POLICY

The goal is to finish the codebase without pretending production verification succeeded when it did not.

For every phase:

1. Implement locally.
2. Test locally.
3. Commit.
4. Push.
5. Allow the existing Render deployment path to deploy.
6. Verify health/configuration.
7. Verify public/unauthenticated behavior automatically where possible.
8. Verify authenticated operator behavior if an authenticated browser/session is genuinely available.
9. Clearly report anything that could not be production-verified.

Never claim an authenticated production action was verified if no authenticated session was actually available.

---

# 14. EMAIL NOTE

Email delivery is NOT a blocker for the remaining roadmap.

Current email architecture includes:

- provider-neutral email abstraction
- Django/local provider
- optional Brevo provider
- standard SMTP configuration

The user has decided:

- no paid Render upgrade
- no Brevo adoption as a current project priority
- no further email implementation work unless required by a real regression

Do not spend remaining-session budget polishing email infrastructure unless a new production defect directly blocks another phase.

Do not remove the current provider abstraction unless it causes an actual problem.

---

# 15. WHAT NOT TO DO

Do not:

- reimplement Phase 0/1/2
- redesign the authentication system
- add Apple Sign-In
- replace Google GIS unnecessarily
- redesign approved authentication UI
- introduce a second tenant-isolation mechanism
- change JWT semantics
- replace the payment gateway abstraction
- hardcode a specific payment provider into platform logic
- replace Celery/Redis with another queue system
- create duplicate plan/subscription models
- create duplicate tenant state models
- introduce speculative features not in this roadmap
- perform broad unrelated refactors
- add large dependencies when an existing dependency already solves the problem
- spend time cleaning harmless legacy/untracked files unrelated to the phases

---

# 16. FINAL EXIT CRITERIA

This remaining-roadmap execution is considered complete only when:

- Phase 3 is implemented and tested.
- Phase 4 is implemented and tested.
- Phase 5 is implemented and tested.
- Phase 6 is implemented to the extent supported by the current deployment environment.
- All full automated suites are green.
- No migration drift exists.
- No provider-specific business logic leaked outside adapters.
- Tenant isolation and JWT semantics are unchanged.
- Root/Staff permission boundaries are enforced server-side.
- Critical mutations are audited.
- Last-root invariant is enforced.
- Tenant suspension is enforced at the authentication boundary.
- Scheduled operational tasks are idempotent/retry-safe.
- Manual fallbacks remain safe until scheduled execution is validated.
- Git history contains one logical commit per phase.
- The working tree contains no accidental modifications.
- Final report clearly distinguishes code-complete behavior from production behavior that could not be verified because of environment limitations.

---

# 17. FINAL REPORT FORMAT

At the end of the entire execution, provide a concise but complete report containing:

## Repository

- final HEAD
- origin/master synchronization
- remaining untracked files

## Phase 3

- implemented features
- endpoints
- UI
- migrations
- tests
- commit SHA

## Phase 4

- implemented features
- security invariants
- tests
- commit SHA

## Phase 5

- implemented features
- authentication enforcement
- tests
- commit SHA

## Phase 6

- tasks/schedules
- worker/scheduler behavior
- idempotency/retry guarantees
- deployment limitations, if any
- tests
- commit SHA

## Global validation

- backend full suite
- frontend full suite
- Django check
- migration check
- production build
- diff check

## Deviations

List only genuine deviations from this document or the approved repository spec.

Do not claim success for a production behavior that could not actually be exercised.

---

# END OF EXECUTION CONTRACT

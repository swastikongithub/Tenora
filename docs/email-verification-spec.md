# Claude Code Implementation Specification — Email Verification

**Scope:** require a verified email before password-based login succeeds.
Registration creates an unverified account; a verification link (real DB-backed
token) must be used before the user can obtain JWTs. Touches both backend
(new model, new endpoints, a SimpleJWT subclass) and frontend (the Register
success flow, a new "check your email" screen, a verify-email landing route).

**Not in scope:** Google OAuth (explicitly separate, per the original proposal),
Razorpay/Stage D, the Platform Admin dashboard, the cancellation UI, any
real transactional email provider (Django's console backend is used for
this stage — see §4.6).

---

## 1. Objective

Today, POST /api/auth/register/ creates a usable account from any
syntactically valid email - nothing proves the person controls that mailbox.
This stage closes that gap: an account starts unverified, a real emailed link
must be used to verify it, and until that happens, password-based login must
not issue JWTs.

This is a real, deliberate change to an already-shipped, tested flow -
RegisterPage.tsx's current "register -> auto-login -> redirect to
/workspace" success path (built in C3) cannot survive unchanged, because an
unverified user must not receive tokens. Treat updating that flow as a first-
class part of this stage, not an afterthought.

Locked design decisions, from prior evaluation - do not re-litigate:
- A new, explicit User.email_verified boolean field. is_active is never
  reused for this - it has a distinct, real meaning (administrative
  disable) that would be conflated with "unverified" if overloaded.
- Verification tokens are a DB-backed model (EmailVerificationToken),
  hashed at rest, single-use via a used_at timestamp - not stateless/signed
  tokens. This mirrors the exact pattern already proven in this codebase for
  refresh-token blacklisting (C3 section 0.2).
- Login's error message stays identical for wrong-password and
  unverified-account cases - no new disclosure surface. An unverified
  account attempting login gets the same generic failure as a wrong
  password; "check your email" is only ever shown immediately after
  registration and via the resend-verification flow, never during a login
  attempt.
- Existing users (including all seeded demo accounts) are grandfathered as
  verified via a data migration - this change must not lock anyone out.

## 2. Inspect Before Implementing

```
CLAUDE.md
docs/proposal-evaluation-email-and-billing.md  - the full design rationale;
                                                  read this in full, it's the
                                                  source of every locked
                                                  decision above
apps/users/models.py, serializers.py, views.py - RegisterView, MeView,
                                                  LogoutView, UserManager -
                                                  the existing home for
                                                  auth-shaped views
config/settings.py                             - SIMPLE_JWT config,
                                                  AUTH_USER_MODEL, current
                                                  EMAIL_BACKEND (verify what,
                                                  if anything, is set -
                                                  likely nothing yet)
config/urls.py                                 - TokenObtainPairView is
                                                  currently wired directly
                                                  from SimpleJWT; this stage
                                                  replaces it with a project
                                                  subclass
apps/tenants/authentication.py                 - GLOBAL_PATHS exact-match
                                                  set - the two new endpoints
                                                  in this stage go here
frontend/src/routes/RegisterPage.tsx           - the flow being changed;
                                                  read its current success
                                                  path in full before touching it
frontend/src/routes/LoginPage.tsx              - messageFor()'s existing
                                                  generic-401 logic - verify
                                                  it already covers this
                                                  case correctly by
                                                  construction (it should,
                                                  since the backend won't
                                                  distinguish the reason)
frontend/src/lib/auth/                         - AuthProvider, login(),
                                                  token storage - confirm
                                                  nothing here needs to
                                                  change beyond what the
                                                  Register flow redesign
                                                  requires
apps/users/tests/test_register.py,
apps/tenants/tests/test_isolation.py           - confirm which existing
                                                  tests assume "register
                                                  implies immediately
                                                  authenticated" and will
                                                  need real revision, not
                                                  just additions
```

Current state: full core product + Docker packaging complete and committed.
Backend 75/75, frontend 245/245.

## 3. Existing Functionality That Must Not Change

- Tenant resolution, GLOBAL_PATHS's exact-match semantics, the 400/403
  contract, TenantScopedManager - untouched. This stage only touches
  apps/users/ and the JWT-issuance path; it does not add or change any
  tenant-scoped behavior.
- AuthProvider, TenantProvider, the query-key isolation mechanism,
  TopNavbar/AccountMenu - untouched.
- Every currently-passing test that isn't specifically about the
  register-then-login assumption must still pass.
- The non-disclosure principle already established for login errors is
  extended, not weakened - see section 1's locked decision.

## 4. Required Changes

### 4.1 User model

Add email_verified = models.BooleanField(default=False). Write a data
migration setting email_verified=True for every existing row as part of
the same migration that adds the field (or an immediately-following data
migration) - this must ship in one deployable unit, not as a manual step
someone might forget to run.

### 4.2 EmailVerificationToken model

New model in apps/users/:
- user (FK to User)
- token_hash (the raw token is never stored - hash it the same way
  passwords are hashed, or at minimum a strong one-way hash; verify against
  a hash of the presented token, never a raw string comparison)
- created_at
- expires_at
- used_at (nullable - NULL means unused)

Token expiration window: 24 hours, as a concrete default (this was left
open in the prior evaluation; picking 24h now rather than leaving it
unresolved - flag if you have a strong reason to differ, but don't leave it
unset).

### 4.3 Registration flow changes

RegisterView (existing): after creating the user, generate a
verification token (cryptographically random via secrets.token_urlsafe,
store only its hash), send a verification email (section 4.6), and return a
response indicating the account was created but is unverified - do not
change the current 201 status or the {id, email} response shape unless
genuinely necessary; report if you find it needs to change.

### 4.4 New endpoints (global paths - add to GLOBAL_PATHS exactly)

```
POST /api/auth/verify-email/
  body: { token }
  -> 200 on success (email_verified = True, token's used_at set)
  -> 400 on invalid, expired, or already-used token - same generic message
    for all three cases, don't let the response distinguish "expired" from
    "already used" (no benefit to the caller, and it's a minor information
    leak about token state)

POST /api/auth/resend-verification/
  body: { email }
  -> 200 with an identical response regardless of whether the email exists,
    is already verified, or a token was actually sent - same non-disclosure
    principle as registration and login. Internally: if a valid unverified
    account exists, invalidate any previous unused token for that user and
    issue a new one.
```

### 4.5 Login gate - SimpleJWT subclass

Replace the stock TokenObtainPairView wired in config/urls.py with a
project-specific subclass (apps/users/views.py or a new auth.py in that
app - use judgement, report where). The subclass's serializer:
- Calls the parent's validate() first (this is what actually checks the
  password via authenticate()).
- If that succeeds but user.email_verified is False, raise the same
  AuthenticationFailed with the same message the parent raises on
  invalid credentials - do not construct a distinguishable error. Verify
  this by comparing the actual response bodies for "wrong password" and
  "correct password, unverified" - they must be identical.

### 4.6 Email sending

Use Django's console EMAIL_BACKEND for this stage (prints the email to
the terminal/log rather than attempting real delivery) - this is honest for
local development and a portfolio demo, and doesn't require provisioning a
real transactional email provider. Document this choice clearly (in
CLAUDE.md or the relevant README section) as a deliberate scope boundary,
not an oversight - a real provider (SES/Postmark/SendGrid) would be a
separate, later decision if this project ever needs actual delivered email.

The email content itself: a verification link pointing at a frontend route
(e.g. /verify-email?token=...) - plain text is fine for the console
backend; don't over-invest in HTML email templating for a feature whose
"delivery" is currently a terminal print statement.

### 4.7 Rate limiting - scoped narrowly

This project has no throttling anywhere today. Add DRF's built-in throttle
classes to exactly two endpoints: register and resend-verification -
both are realistic abuse/spam vectors this feature newly introduces. Do not
attempt a platform-wide throttling redesign; that's out of scope here.
Reasonable defaults (e.g. a handful of requests per hour per IP) are fine -
this isn't a security-critical rate limit, just basic spam resistance.

### 4.8 Frontend - Register flow redesign

RegisterPage.tsx's success path changes from "auto-login -> redirect to
/workspace" to: show a "check your email" confirmation screen (using
existing primitives - Card, Alert or similar), with a way to trigger
resend-verification if the user doesn't see the email. Do not
auto-login after registration anymore - the account isn't usable yet.

### 4.9 Frontend - verify-email landing route

A new route (e.g. /verify-email) that reads a token query parameter,
calls POST /api/auth/verify-email/, and shows success (with a link to
/login) or failure (invalid/expired, with a way to request a new link)
states. This is a new, small page - reuse existing primitives, don't design
new visual language for it.

## 5. Files Likely Affected

```
Backend:
  new:      apps/users/migrations/... (email_verified field + data migration)
            EmailVerificationToken model + its migration
            verify-email / resend-verification views + serializers
            the TokenObtainPairView subclass
            tests for all of the above
  modified: apps/users/models.py, serializers.py, views.py
            config/urls.py (new routes + the TokenObtainPairView swap)
            apps/tenants/authentication.py (GLOBAL_PATHS +2 entries)
            config/settings.py (EMAIL_BACKEND, throttle scopes)
            docs/project-master-spec.md (record the shipped decisions,
                                          same pattern as every prior stage)

Frontend:
  new:      frontend/src/routes/VerifyEmailPage.tsx
            a "check your email" component/state for RegisterPage
            tests for both
  modified: frontend/src/routes/RegisterPage.tsx (success path redesign)
            frontend/src/routes/AppRoutes.tsx (new route)
```

## 6. Business Rules

- email_verified is never set to True except via a successful
  verify-email call (or the one-time grandfathering migration for
  pre-existing users).
- A token is single-use - used_at is set atomically with the verification
  succeeding, and a second attempt with the same token fails the same way
  an expired one does.
- resend-verification never reveals account existence or verification
  status through its response.

## 7. Security Requirements

- Tokens: cryptographically random, hashed at rest, never logged or
  returned in any API response body after creation.
- Login error responses are byte-identical for wrong-password and
  unverified-account cases - verify this with an actual test comparing both
  response bodies, not just an assumption that the code path is shared.
- Rate limiting per section 4.7.
- No change to tenant isolation, RBAC, or any existing security boundary.

## 8. Edge Cases

- A user requests resend multiple times rapidly - only the most recent
  unused token should be valid; prior ones are invalidated, not left as
  additional valid tokens.
- Token used successfully, then the same link clicked again - second
  attempt fails with the same generic message as an expired token.
- Existing seeded demo accounts (from Docker's seed_demo_data command and
  any manually created via Django admin) must still be able to log in
  after this migration ships - verify explicitly, don't just assume the
  grandfathering migration covers them.
- A user who never verifies - their account exists indefinitely in an
  unverified state; this stage doesn't need to build account cleanup/expiry
  for abandoned unverified accounts (out of scope, not required).

## 9. Tests Required

Backend:
- Token generation, hashing, expiry rejection, single-use rejection (mirror
  the exact "already-blacklisted -> 400" test shape from C3 section 0.2).
- Unverified user cannot obtain a JWT via login; verified user can, with an
  identical error body for both wrong-password and unverified cases
  (explicit byte-for-byte comparison).
- resend-verification returns an identical response for: nonexistent
  email, already-verified email, and a genuine unverified email - three
  cases, one indistinguishable response shape.
- Existing users/seeded accounts can still log in after the grandfathering
  migration (a real test against migrated data, not just a unit assumption).
- Rate limiting actually throttles after the configured threshold on both
  new endpoints.

Frontend:
- Register success shows the "check your email" state, does not auto-login,
  does not redirect to /workspace.
- Resend-verification can be triggered from that screen.
- /verify-email?token=... handles success and failure (invalid/expired)
  states correctly.
- Existing Register tests that assumed auto-login are revised to match the
  new flow - not just left broken or silently deleted.

## 10. Acceptance Criteria

1. manage.py check and manage.py test - full count reported, including
   every new test above.
2. npm run build, npm test, npm run lint - full count reported.
3. Manual walkthrough, screenshotted: register a new account through the UI
   -> see "check your email" -> find the verification email in the console
   log/Django server output -> use the link -> land on the success page ->
   log in successfully. Then attempt to log in with an unverified second
   account and confirm the generic error matches a wrong-password attempt
   exactly.
4. Confirm existing seeded demo accounts still log in after the migration.
5. git status review - no unrelated file changed.
6. Report: the exact login-error response body for both the wrong-password
   and unverified-account cases, proving they're identical; the chosen
   token expiration window; and confirmation the grandfathering migration
   was tested against real existing data, not just asserted to work.

## 11. Must NOT Do

- Do not reuse is_active for verification status.
- Do not use stateless/signed tokens - DB-backed only, per section 1.
- Do not make the login error distinguishable between wrong-password and
  unverified-account.
- Do not configure a real transactional email provider - console backend
  only, per section 4.6.
- Do not build a platform-wide rate-limiting redesign - scoped to exactly
  two endpoints, per section 4.7.
- Do not build Google OAuth, Razorpay, the Platform Admin dashboard, or the
  cancellation UI as part of this stage.
- Do not weaken any existing test - revise the ones that assumed the old
  register-then-auto-login flow, don't delete their coverage.

---

## Workflow

Produce a plan first and wait for approval before writing code. This stage
touches both backend and frontend in real proportion - propose a session
split if it makes sense (e.g. backend model/endpoints/SimpleJWT subclass
first, frontend flow redesign second), same pattern as every other
stage this size.

---

## Ready-to-paste prompt for Claude Code

Read docs/email-verification-spec.md, then inspect the repository.
Produce an implementation plan and wait for my approval before writing any code.

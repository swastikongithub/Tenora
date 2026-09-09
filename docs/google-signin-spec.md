# Claude Code Implementation Specification — Google Sign-In

**Scope:** add "Sign in with Google" as a second, independent way to obtain a
session — verified via Google ID token, not a heavy OAuth framework. One new
backend endpoint, one new frontend button/flow. Existing password-based login,
registration, and email verification are unaffected and remain fully
functional alongside this.

**Not in scope:** removing or replacing password-based auth, Razorpay/Stage D,
the Platform Admin dashboard, the cancellation UI, any other OAuth provider
(GitHub, Apple, etc.) — Google only, per the original proposal's explicit
scoping.

---

## 0. Prerequisite (the user's action, not Claude Code's)

A **Google Cloud OAuth 2.0 Client ID** (Web application type) must exist
before this can be tested end-to-end — this requires creating a project in
Google Cloud Console, configuring the OAuth consent screen, and generating a
Client ID. This is analogous to Docker needing to be installed before the
Docker stage could proceed: **check whether `GOOGLE_OAUTH_CLIENT_ID` is
already set** (in `.env` or otherwise); if not, report this as a blocker and
stop — obtaining it is the user's action, not something to work around or
stub out.

## 1. Objective

**Architectural decision, locked — do not default to `django-allauth` or
`dj-rest-auth`, even though they're the most commonly documented approach.**
Those packages are session/cookie-based frameworks with their own account
app, their own signals, and — critically — their **own built-in email
verification system**, which would duplicate or conflict with the
`EmailVerificationToken` system already built and tested in this codebase.
Pulling in a heavy framework here would mean either ripping that work out or
running two parallel, competing verification systems.

**Instead: verify Google ID tokens directly**, using the `google-auth`
library — a small, focused dependency that does exactly one thing (verify a
JWT's signature against Google's public keys), fitting the same
"thin custom view in `apps/users/`" pattern every other auth endpoint in this
project already follows. This is the smaller, better-fit surface area, and
it produces the same output as every other login path: your existing
SimpleJWT access/refresh tokens — nothing downstream of login needs to know
or care that a session originated via Google.

**Locked design decisions:**
- A Google-authenticated user's email is verified **by Google** —
  `email_verified=True` is set immediately on account creation via this path;
  the email-verification-link flow is never triggered for Google sign-ins.
- **Auto-link by email**: if a password-based account already exists with
  the email Google returns, Google sign-in logs into that same account rather
  than creating a duplicate or rejecting the attempt. Rationale: Google's own
  email verification is at least as strong a proof of ownership as this
  project's own email-link mechanism — recorded as a deliberate decision, not
  a silent default, because it's a real account-linking policy choice.
- A Google-only account (no local password ever set) gets
  `set_unusable_password()` — the standard Django idiom for "this account
  cannot authenticate via the password flow," preventing any confusion about
  a blank or guessable password.
- Loading Google's Identity Services script from Google's own domain is a
  **deliberate, necessary exception** to this project's general preference
  against third-party CDN dependencies (established for fonts in C1) — this
  specific integration cannot be self-hosted by its nature; note this
  explicitly wherever the script is loaded, so it doesn't read as an
  inconsistency with the font-loading rule.

## 2. Inspect Before Implementing

```
CLAUDE.md
apps/users/models.py, serializers.py, views.py, auth.py — the existing home
                                        for auth-shaped views; auth.py now
                                        also holds the JWT-issuance subclass
                                        from the email-verification stage —
                                        this new endpoint follows the same
                                        pattern, doesn't touch that subclass
docs/email-verification-spec.md      — the email_verified field and
                                        EmailVerificationService this stage
                                        interacts with (skips, for Google
                                        sign-ins) — read in full
config/settings.py                   — where GOOGLE_OAUTH_CLIENT_ID should
                                        be read from env, alongside the
                                        existing pattern for other secrets
apps/tenants/authentication.py       — GLOBAL_PATHS — the new endpoint goes
                                        here, unauthenticated and untenanted
                                        like /api/auth/login/
frontend/src/routes/LoginPage.tsx,
RegisterPage.tsx                     — where the "Sign in with Google"
                                        button/flow gets added
frontend/index.html or main.tsx      — where a third-party script tag would
                                        need to load, if that's the chosen
                                        integration approach — verify against
                                        how Google's current Identity
                                        Services library expects to be
                                        loaded (script tag vs. an npm
                                        package) before assuming either
```

Current state: email verification complete and committed. Backend 98/98,
frontend 252/252.

## 3. Existing Functionality That Must Not Change

- Password-based login, registration, and email verification all continue
  working exactly as they do today — this is an additive second path, not a
  replacement.
- `TokenObtainPairView`'s subclass from the email-verification stage is not
  modified — this new Google endpoint is a separate view issuing tokens
  through its own logic, not routed through the password-login serializer.
- Tenant resolution, `GLOBAL_PATHS` exact-match semantics, the query-key
  isolation mechanism — untouched.
- All existing tests must still pass.

## 4. Required Changes

### 4.1 Backend dependency

Add `google-auth` (the library, not `django-allauth`) to
`requirements/base.txt` — justify this addition explicitly in the report,
same as `gunicorn` was justified in the Docker stage.

### 4.2 New endpoint

```
POST /api/auth/google/
  body: { credential: <google-issued ID token> }
  → 200 with { access, refresh } on success — the same shape as
    /api/auth/login/'s success response
  → 400 if the token fails Google's signature/audience verification
```

Global path (add to `GLOBAL_PATHS`, no tenant context, same category as
`/api/auth/login/`).

Logic:
1. Verify the token via `google.oauth2.id_token.verify_oauth2_token`,
   checking it against `GOOGLE_OAUTH_CLIENT_ID` — a failed verification
   (bad signature, wrong audience, expired) returns the 400 above, generic
   message, no distinction between failure reasons (same non-disclosure
   discipline as every other auth error in this project).
2. Extract the verified email from the token payload.
3. Find-or-create the local `User`:
   - Existing user with that email → this is the account, regardless of how
     it was originally created. If it wasn't already `email_verified`, set
     it to `True` now (§1's locked decision).
   - No existing user → create one, `email_verified=True` immediately,
     `set_unusable_password()` called.
4. Issue and return real JWT tokens via the existing token-issuing mechanism
   — this account, having just been resolved as verified, does not need to
   go through the email-verification-gated login serializer's check (it's
   verified by construction at this point) — but confirm this is
   consistent, not a bypass of a check that should still apply for some
   other reason; report your reasoning either way.

### 4.3 Frontend integration

Add "Sign in with Google" to both `LoginPage.tsx` and `RegisterPage.tsx`.
Use Google's current Identity Services approach (verify the current
integration method — script tag vs. an official npm wrapper — against
Google's actual current documentation rather than assuming a specific
implementation detail that may be stale). On receiving a credential from
Google's button callback, POST it to `/api/auth/google/`, then handle the
response exactly like a successful password login (store tokens, navigate
into the app) — reuse `AuthProvider`'s existing `login`-adjacent state
management rather than inventing a parallel auth-success path.

## 5. Files Likely Affected

```
Backend:
  new:      the Google verification view + serializer (apps/users/)
            tests for the above
  modified: apps/users/models.py (if any field is needed beyond what
                                    email_verified already provides — report
                                    if so, don't assume)
            config/settings.py (GOOGLE_OAUTH_CLIENT_ID from env)
            apps/tenants/authentication.py (GLOBAL_PATHS +1)
            requirements/base.txt (+google-auth)

Frontend:
  new:      the Google sign-in button/integration component
            tests for it (mocking Google's callback, not a real OAuth flow)
  modified: LoginPage.tsx, RegisterPage.tsx
            frontend/src/lib/global-paths.ts (+1 entry, mirroring the
                                                backend's GLOBAL_PATHS)
```

## 6. Business Rules

- Google-authenticated accounts skip the email-verification-token flow
  entirely — never issued, never checked for these accounts.
- Auto-linking by email is the only linking behavior — no separate
  "connect your Google account" flow for an already-logged-in user is
  required by this stage (that would be a reasonable future enhancement,
  not required now).

## 7. Security Requirements

- Token verification must check the audience (`GOOGLE_OAUTH_CLIENT_ID`) —
  a token issued for a *different* Google app must not be accepted here.
  This is what `verify_oauth2_token`'s audience parameter exists for;
  confirm it's actually passed, not omitted.
- No card/payment fields, no new tenant-scoped surface — this stage is
  authentication only.
- `GOOGLE_OAUTH_CLIENT_ID` (and if applicable, a client secret) are read
  from environment variables, never hardcoded, following the existing
  `.env`/`.env.example` pattern.

## 8. Edge Cases

- Google returns an email that's already verified via the password flow —
  auto-links cleanly, no error.
- Google returns an email tied to an account that was previously
  unverified via the password flow (registered but never clicked the link)
  — Google sign-in should still work and should mark the account verified,
  effectively "completing" verification through an alternate proof.
- A malformed or expired Google token — clean 400, not a 500.
- `google-auth`'s verification call itself failing due to a network issue
  (fetching Google's public keys) — this should surface as a clear error,
  not crash unhandled; report how this is handled.

## 9. Tests Required

**Backend:** mock `verify_oauth2_token` — there's no way to obtain a real
Google-signed token in an automated test without live user interaction, and
the test suite must not attempt to hit real Google servers. Cover:
successful verification creates a new, `email_verified=True`, unusable-
password user; successful verification with an existing email auto-links
and returns tokens for that account; a previously-unverified password
account becomes verified via this path; a failed verification (mocked to
raise) returns a clean 400.

**Frontend:** mock the Google button's callback (don't attempt a real
Google OAuth flow in tests) — verify the credential gets POSTed correctly
and a successful response routes into the app the same way a password
login does.

## 10. Acceptance Criteria

1. `manage.py check`, `manage.py test` — full count reported.
2. `npm run build`, `npm test`, `npm run lint` — full count reported.
3. Manual walkthrough, screenshotted, using a **real** Google account
   (this is the one part of this stage that can't be verified by automated
   tests alone): sign in with Google for the first time (new account
   created, immediately usable, no verification email needed), sign out,
   sign in again (existing account, same result), and confirm a
   pre-existing password-based account with the same Google email
   auto-links correctly.
4. Confirm password-based login/registration/verification are all
   unaffected — run through at least one full password-based flow
   manually alongside the Google one.
5. `git status` — no file outside what's named above.
6. Report: which Google Identity Services integration approach was used and
   why, confirmation the audience check is real (not omitted), and the
   `set_unusable_password()` behavior verified against an actual created
   Google-only account.

## 11. Must NOT Do

- Do not use `django-allauth` or `dj-rest-auth`.
- Do not build a separate email-verification path for Google accounts —
  they're verified by construction, per §1.
- Do not hardcode `GOOGLE_OAUTH_CLIENT_ID` anywhere.
- Do not attempt to hit real Google servers in the automated test suite.
- Do not modify the email/password login serializer or the
  `TokenObtainPairView` subclass from the email-verification stage.
- Do not build Razorpay, the Platform Admin dashboard, or the cancellation
  UI as part of this stage.
- Do not weaken any existing test.

---

## Workflow

Confirm the prerequisite (§0) before anything else. Then produce a plan and
wait for approval before writing code.

---

## Ready-to-paste prompt for Claude Code

```
Read docs/google-signin-spec.md, then check whether GOOGLE_OAUTH_CLIENT_ID
is available (§0). Report the result. If it's available, inspect the
repository and produce an implementation plan, then wait for my approval
before writing any code.
```

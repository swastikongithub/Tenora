# Proposal Evaluation — Email Verification & Billing UI

No code or Claude Code prompts in this document, per instruction. This is
architecture-level analysis only.

---

## 1. Assessment of Proposal 1 — Email Ownership Verification

**Is this a good architectural addition? Yes, with real caveats worth naming
plainly rather than glossing over.**

Email verification is legitimate, standard security hygiene, and it's defensible
portfolio content — it demonstrates thinking about account-integrity threats, not
just CRUD. But it is **not free**, and three things need to be said before
proceeding:

1. **It breaks an already-shipped, tested UX flow.** C3 built register →
   auto-login → redirect to `/workspace` as a deliberate, verified piece of work
   (screenshotted, tested, working). Point 4 of your proposal ("an unverified user
   must not receive application JWTs") directly ends that flow. This isn't a small
   patch — `RegisterPage.tsx`'s success path and its tests need a real redesign
   (e.g., register → "check your email" screen, not an automatic login).
2. **It requires SimpleJWT's stock view to be replaced with a custom one.**
   `config/urls.py` currently wires `TokenObtainPairView` directly (a SimpleJWT
   built-in). Blocking token issuance for unverified users means subclassing
   `TokenObtainPairSerializer`/`TokenObtainPairView` — a genuine new piece of
   custom auth code, not a config change.
3. **It surfaces a gap this project doesn't have a story for yet: rate limiting.**
   Nothing in this codebase throttles any endpoint today. A resend-verification
   endpoint is a spam/abuse vector by nature. This proposal is a good forcing
   function to finally address that — but it's additional, real scope, not
   something to silently skip.

None of these are reasons not to build it. They're reasons to treat it as its own
deliberate stage (§8 below), the same way every other cross-cutting change in this
project (light mode, the navbar redesign, the AuthArtPanel redesign) got its own
focused session rather than being folded into whatever was already in flight.

**I'm also challenging one specific assumption in your spec, per your own
instruction to do so:** you didn't say whether login should distinguish
"unverified account" from "wrong password" in its error response. I'm recommending
it should **not** — see §2E.

---

## 2. Recommended Design for Proposal 1

### A. Where it lives
`apps/users/` — consistent with `RegisterView`, `LogoutView`, `MeView` already
living there as the established home for auth-shaped views on the `User` model.

### B. Interaction with the custom `User` model
**Add an explicit `email_verified` boolean field (default `False`). Do not overload
`is_active` for this.** `is_active` already has a distinct, real meaning in Django
(administratively disabling an account) and is checked by `ModelBackend` during
authentication. Using it to mean "not yet verified" would conflate two different
concepts a real system eventually needs to distinguish — a banned user and an
unverified user are not the same thing, and a single boolean can't represent both
once you need both. This is the same category of judgment call as the `on-accent`
token addition in C3b: don't reuse an existing field for a second, different
meaning just because it's mechanically convenient right now.

**Migration concern:** existing seeded/demo users (and any real accounts created
before this ships) must be grandfathered — a data migration setting
`email_verified=True` for all pre-existing rows, so this change doesn't silently
lock out every account created so far. Flagging this explicitly so it isn't
missed mid-implementation.

### C. Interaction with SimpleJWT
Subclass `TokenObtainPairSerializer` (and the view) to add an explicit
`email_verified` check after `authenticate()` succeeds, raising the **same generic
`AuthenticationFailed`** message used for a wrong password (§2E) — not a
distinguishable one. Wire the custom view in place of the stock
`TokenObtainPairView` in `config/urls.py`.

### D. Token mechanism — recommendation: **DB-backed token model**, not
stateless/signed tokens.

Compared:
- **Stateless/signed tokens** (e.g. Django's `PasswordResetTokenGenerator`
  pattern, or an HMAC-signed value) — no new table, but genuine single-use
  enforcement is awkward (a signed token stays valid until it expires unless you
  track *something* stateful about "already used," which defeats the "no new
  state" appeal).
- **A separate `EmailVerificationToken` model** — `user` FK, `token_hash`
  (never store the raw token, same principle as password hashing), `created_at`,
  `expires_at`, `used_at` (nullable). Single-use is a real `used_at IS NOT NULL`
  check, mirroring the exact pattern C3 §0.2 already established for refresh-token
  blacklisting (a real DB row is the actual guarantee, not client trust).

**Recommendation: DB-backed.** It matches the architectural taste already
established in this codebase — explicit state over stateless cleverness — and it
reuses a pattern (real revocation via a real row) this project has already built
and tested once.

### E. Token expiration, single-use, resend — and the login-disclosure decision

- **Single-use:** `used_at` set on success; a second attempt with the same token
  gets the same "invalid or expired" response as a genuinely expired one — don't
  distinguish "already used" from "expired" in the response (that distinction
  leaks information for no benefit).
- **Resend:** invalidate the previous unissued token when a new one is requested
  (don't let multiple valid tokens exist for one user at once). Response to a
  resend request must be **identical regardless of whether the email exists or is
  already verified** — "if this email exists and needs verification, we've sent a
  link" — same non-disclosure principle already applied to registration and login.
- **Login-error disclosure (the assumption I'm challenging):** recommend the
  **exact same generic message** for wrong-password and unverified-account cases.
  Here's why, reasoned from this project's own stated priorities: the master
  spec ranks security above UI quality explicitly. Distinguishing "your password
  was right but your email isn't verified" from "invalid credentials" is a real
  oracle — it tells an attacker running a password-guessing attack against a known
  email exactly when they've found the right password, which is *more* dangerous
  than the account-existence leak this project already accepts at registration
  (registration necessarily reveals "this email is taken"; login revealing "you
  had the right password" is a stronger signal). The UX cost (a legitimately
  unverified user gets a confusing generic error) is real, but smaller than the
  security cost of the alternative — and it's fully mitigated by making "check
  your email" the explicit message shown immediately after registration, before
  the user ever attempts to log in. **This is a recommendation, not something I
  consider fully locked without your sign-off** — see §7.

### F. Security/abuse controls
- Tokens: cryptographically random (`secrets.token_urlsafe`), hashed at rest.
- **Rate limiting on `register` and `resend-verification`** — this project has
  zero throttling today; recommend DRF's built-in throttle classes as the
  lightest-weight fix, scoped only to these two endpoints for now rather than a
  platform-wide throttling redesign (that's bigger scope than this proposal
  needs).
- No existence leakage beyond what's already accepted (§2E).

### G. New API endpoints
```
POST /api/auth/verify-email/            { token } → verifies, single-use
POST /api/auth/resend-verification/     { email } → identical response either way
```
Both global paths (no tenant context needed, consistent with the existing
`GLOBAL_PATHS` exact-match convention).

### H. Database/model changes
- `User.email_verified` (new field, migration + data migration for existing rows).
- New `EmailVerificationToken` model (see §2D).

### I. Tests required
- Token generation/hashing, expiry rejection, single-use rejection (mirror the
  exact "already-blacklisted → 400" test shape from C3 §0.2).
- Unverified user cannot obtain JWTs; verified user logs in normally.
- Resend never leaks existence.
- **Existing registration/login tests need real revision, not just additions** —
  the current "register succeeds, tokens returned" assumption in B1's tests and
  C3's frontend register-then-auto-login test both change fundamentally.

### J. Stage sizing
This is **its own stage** — call it something like a dedicated auth-hardening
stage — not a §0-style scoped addendum folded into something else. It touches
backend (new model, new views, SimpleJWT subclass, migration) and frontend
(Register flow redesign, a new "check your email" screen, a verify-email landing
route) in roughly equal measure. Comparable in shape to C3, not to a small
addendum like C1a.

### K. Risks / unintended consequences (summarized, expanded above)
1. Breaks the shipped register→auto-login flow — must be redesigned, not patched.
2. Requires a real infrastructure decision: email sending. Django's console email
   backend is sufficient for local dev and honest for a portfolio demo (it prints
   the email to the terminal rather than faking delivery) — recommend this for
   now, with a note that a real transactional provider (Postmark/SES/SendGrid)
   would be a Phase-2-or-later concern if this project ever needs actual delivered
   email. **Flagging as explicitly undecided** — see §7.
3. First rate-limiting need in the project — scoped narrowly per §2F, not a
   platform-wide redesign.
4. Existing seeded demo users need a grandfathering migration or they'll be
   locked out.
5. The login non-disclosure question in §2E needs your explicit sign-off, not a
   silent choice either way.

---

## 3. Assessment of Proposal 2 — Billing / Payment UI

**This is the important finding: most of what you're describing already exists.**
Stage C5 (Subscription & Plans, already built and committed) covers:
- Current subscription/plan ✅ (already built)
- Available plans ✅ (already built)
- Upgrade/downgrade actions ✅ (already built)
- Billing period ✅ (already built — including relative-time rendering, added in C6)
- Subscription status ✅ (already built, with plain-English explanations added in C6)
- Loading/empty/unavailable/error states ✅ (already built, including the
  per-tile failure isolation work from C6)

**What's genuinely new in your proposal, and not yet built:**
- Payment method section
- Billing history / invoice list

Both of these depend on things that don't exist in this codebase at all yet:
Stripe integration (for payment methods) and the `Invoice`/`Payment` models
(named in the master spec as Phase-2-reserved, with no fields ever defined).

**Is it appropriate to build these two remaining pieces now, even just as UI?**
**No — and this is a case worth pushing back on rather than just designing what
was asked.**

- **Payment method UI, even as an empty/placeholder shell, should not be built
  now.** There is no real state to represent yet (no payment method has ever
  existed for any tenant, and can't, since there's no Stripe integration). Any UI
  here — even a "not yet available" placeholder — would need to be redesigned the
  moment real Stripe Elements/Checkout integration lands, because that
  integration dictates real UI constraints (Stripe's own embedded components)
  that a generic placeholder can't anticipate. Building it now is speculative
  work that gets thrown away, the same category of mistake C1 avoided by
  deferring Table's mobile transform until a real page needed it.
- **Billing history / invoice list** is a more defensible placeholder candidate
  (an empty state saying "billing history will appear here" is honest and
  low-risk, similar to the C2-era route stubs), but it's also genuinely low
  value right now — a placeholder for a placeholder. I'd recommend against
  building even this until the `Invoice` model's fields are actually decided
  (still an open item per the master spec), so the "empty state" isn't
  eventually retrofitted around a data shape decided later.

**Recommendation: Proposal 2 should not result in new work right now.** The
valuable parts are done; the remaining parts are better built alongside their
actual backend (Phase 2/Stripe), not ahead of it. This isn't a rejection of the
idea — it's confirming the idea's realistic, safe parts already shipped, and its
risky parts should wait for the infrastructure that makes them real rather than
speculative.

---

## 4. Recommended Design for Proposal 2

No new page or component. Two small documentation actions:
1. Note in the master spec (§9 below) that Proposal 2's Phase-1-eligible scope is
   satisfied by the existing Subscription & Plans page (C5) plus Overview's plan
   summary (C6) — so this doesn't get proposed again as if it's missing.
2. Explicitly record that Payment Method UI and Billing History/Invoices are
   deferred **as a design decision, not an oversight** — to be built as part of
   the Stripe/Phase 2 stage(s) that give them real data and real constraints, not
   before.

---

## 5. Should either proposal be changed?

- **Proposal 1:** change the `is_active` assumption (use a new explicit field
  instead) and settle the login-disclosure question explicitly (§2E) rather than
  leaving it implicit. Otherwise the proposal's own listed requirements (1–14)
  are sound and don't need structural changes.
- **Proposal 2:** change the ask entirely — from "build this now" to "confirm
  it's covered, document the deferral for the rest." Building the two missing
  pieces now would violate this project's own no-fabrication and
  don't-build-ahead-of-real-data principles.

---

## 6. Architectural decisions that should become LOCKED

1. Email verification is its own stage, not folded into existing work.
2. `User.email_verified` is a new, explicit field — `is_active` is never reused
   for this purpose.
3. Verification tokens are DB-backed (`EmailVerificationToken`, hashed at rest,
   single-use via `used_at`), not stateless/signed.
4. `TokenObtainPairView`/`Serializer` gets a project-specific subclass to enforce
   the verification gate — the stock SimpleJWT view is no longer wired directly
   once this ships.
5. Existing users are grandfathered as verified via a data migration — this
   change must not lock out any existing account.
6. Payment Method UI and Billing History/Invoices are deferred to the Phase
   2/Stripe stage(s) — not built as placeholders beforehand. This is a decision,
   recorded the same way the subscription-cancellation deferral was recorded in
   C5.
7. Proposal 2 requires no new roadmap stage — its Phase-1-eligible scope is
   already satisfied by C5/C6.

## 7. Items that should remain EXPLICITLY UNDECIDED

1. **Login error disclosure** — I've made a firm recommendation (§2E: identical
   generic message for wrong-password and unverified-account), grounded in this
   project's own stated security-over-UX priority ordering, but this is a real
   product tradeoff and shouldn't be treated as locked without your explicit
   confirmation.
2. **Email sending infrastructure** — Django's console backend is recommended
   for now (honest for local/portfolio use, no new external dependency), but
   whether this project ever wires a real transactional email provider is
   genuinely open and not needed to build the feature itself.
3. **Token expiration window** — no specific duration recommended here (24h,
   48h, etc. are all reasonable); this is a product decision, not an
   architectural one.
4. **Resend cooldown specifics** — that a cooldown/rate-limit should exist is
   locked; the exact throttle numbers are not.
5. **Whether Billing History gets even a minimal "coming soon" placeholder** —
   I recommended against it, but it's a low-stakes enough call that it's fair to
   leave open rather than firmly locked either way.

## 8. Impact on the roadmap

- **New stage:** Email Verification (Proposal 1) — sized like C3, touching both
  backend and frontend. Insert wherever you like relative to Docker packaging
  and the Platform Admin dashboard; no hard dependency on either.
- **No new stage:** Billing UI (Proposal 2) — resolved by documentation, not
  code.

## 9. Recommended implementation order

If you want both addressed: do the **documentation-only resolution of Proposal 2
first** (near-zero cost, closes the question), then treat Email Verification as
its own deliberate stage whenever you're ready to take it on — it's real,
valuable scope, but it's exactly the size of thing this project has repeatedly
insisted on giving its own focused session (see: light mode, navbar redesign,
AuthArtPanel redesign) rather than rushing.

## 10. Conflicts with existing architectural decisions

- Proposal 1 conflicts with (i.e., requires deliberately changing) the C3
  register→auto-login flow and the direct use of SimpleJWT's stock
  `TokenObtainPairView`. Both are named, intentional changes, not accidental
  breakage — call them out plainly in whatever stage spec eventually implements
  this.
- Proposal 2, if implemented as originally written, would conflict with two
  standing rules: never fabricate data/UI ahead of real backend support, and
  never build anything resembling payment-collection UI before Stripe owns that
  surface. This is why §3–4 recommend against building it now rather than
  designing around the conflict.

---

## Proposed Master Specification Update

Add to `docs/project-master-spec.md`:

**§A (Locked Decisions) — new entries:**
- Email verification, when built, uses an explicit `User.email_verified` field
  and a DB-backed `EmailVerificationToken` model — never `is_active` repurposed,
  never stateless/signed tokens.
- Login failure responses remain identical for wrong-password and (once it
  exists) unverified-account cases — no new disclosure surface, consistent with
  the existing non-disclosure rule. *(Recorded as locked per the recommendation
  in §2E/§7 — confirm before treating as final.)*
- Payment Method UI and Billing History/Invoice UI are explicitly deferred to
  the Phase 2/Stripe stage(s) — not built as Phase 1 placeholders. The
  Subscription & Plans page (C5) and Overview's plan summary (C6) are the
  complete Phase-1-eligible billing UI; no further billing UI work is expected
  before Phase 2.

**§E (Explicitly Undecided) — new entries:**
- Email verification token expiration window.
- Resend-verification cooldown specifics.
- Whether this project ever configures real transactional email delivery versus
  relying on Django's console backend indefinitely.
- Whether a minimal "coming soon" placeholder for Billing History is worth
  building before Phase 2 (leaning no, not locked).

No other locked decision in the master spec is changed by this proposal.

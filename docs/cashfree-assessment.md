# Architectural Assessment — Cashfree as a Development-Time Alternative

No code changed. This is analysis only, per your instruction. Verified
against Cashfree's current documentation, not assumed from memory.

---

## 1. The core question: does Cashfree's sandbox let you complete D2+ without KYC/activation?

**Mostly yes — with one real caveat worth understanding, not glossing over.**

Cashfree's own quickstart states plainly: **"KYC: Not required for
simulated testing"** and **"Activation: Instant access for initial
integration."** Creating a test-mode account, generating sandbox API
keys, and calling the standard Payment Gateway APIs (orders, payments,
plans, subscriptions via the **non-seamless / hosted-checkout** flow) all
work immediately after signup — no waiting period, no document
submission, no "Company Registration" gate like the one that stopped you
on Razorpay.

**The caveat:** Cashfree's docs for their *Seamless* subscription
integration state explicitly — **"To use this API integration, the S2S
flag must be enabled for your account. To enable Card Payments, ensure
the PCI DSS flag is active."** This is the same *shape* of problem you
hit with Razorpay (a specific flag/product gate, not blanket KYC) — just
narrower in scope. It applies specifically to the *Seamless* (embedded,
no-redirect) flow and to card payments within it, not to Subscriptions
as a whole.

**The practical path that avoids this entirely:** Cashfree's
**Non-Seamless / Hosted Checkout** subscription flow — where the
customer is redirected to a Cashfree-hosted authorization page rather
than an embedded widget — appears to work with nothing beyond standard
sandbox API keys. Their own "Hosted Checkout" integration guide lists
exactly two prerequisites: create an account, generate test keys. No
flag-enablement step is mentioned for that path.

**Verdict on the core question:** if you use the hosted-checkout
subscription flow (not the embedded/Seamless one), Cashfree's sandbox
genuinely looks unblocked right now, in a way Razorpay currently isn't
for you. That's a real, meaningful difference — not a marketing claim.

## 2. Feature-by-feature, against your requirements list

| Requirement | Cashfree sandbox | Notes |
|---|---|---|
| Subscription creation | ✅ | `POST /pg/plans` (Create Plan) → `POST /api/v2/subscriptions/...` (Create Subscription) |
| Hosted checkout | ✅ | This is actually Cashfree's more natural, less-gated path (see §1) |
| Payment status | ✅ | Standard status-retrieval endpoints, same shape as Razorpay's |
| Webhooks | ✅ | Dashboard-configurable, same general pattern as Razorpay |
| Webhook signature verification | ✅, but **different construction** | See §3 — not a drop-in match for D1's existing logic |
| Idempotency | ⚠️ Same gap as Razorpay | No built-in idempotency-key mechanism found on subscription/plan creation — same "the unique-constraint-on-event-ID pattern is your own responsibility" situation D1 already solved generically |
| Subscription lifecycle events | ✅ | Webhook-driven states (`ACTIVE`, `ONHOLD`, etc.), broadly comparable shape to Razorpay's |
| Test/sandbox credentials | ✅, self-serve, instant | No waiting period for the standard flow |

## 3. Real architectural differences — not just a name swap

Two things would genuinely need provider-specific handling, not just a
renamed field, if this project ever supported both:

**Webhook signature construction is different, not just differently
named.** Razorpay: HMAC-SHA256 over the **raw body alone**, hex digest,
keyed with a **separate webhook-specific secret**. Cashfree: HMAC-SHA256
over **`timestamp + raw body` concatenated**, **Base64-encoded** (not
hex), keyed with the **same client secret** used for API auth (no
separate webhook secret). D1's `verify_webhook_signature` is written
specifically for Razorpay's exact construction — it would not verify a
Cashfree webhook correctly, and a second, provider-specific function
would be needed. This *can* sit behind a common interface (something
like a `WebhookVerifier` per provider, both satisfying "take headers +
raw body, return a boolean"), but the interface would need to exist —
it doesn't yet, because D1 was written for one provider.

**Checkout UX shape is fundamentally different, not just a config
value.** Razorpay's Checkout is an **embedded JS widget** — `.open()`
on the same page, success/dismiss callbacks fire in-browser, D2's
`useRazorpayCheckout` hook is built entirely around that pattern.
Cashfree's Hosted Checkout (the less-gated path from §1) is a
**redirect flow** — the customer leaves your site for a Cashfree-hosted
page, then returns to a `returnUrl` you specify. This is not a
config-level difference; it's a different frontend integration pattern
entirely (redirect-and-resume vs. embedded-widget-with-callbacks), and
D2's actual checkout hook would need a real rewrite, not a parameter
change, to support both.

## 4. How much of D1 is already provider-neutral, and how much isn't

**Already effectively provider-neutral, just named otherwise:**
- The **core idea** of `WebhookEvent` (store first, verify signature
  before processing, dedupe via a unique constraint on the provider's
  event ID) is a sound, provider-agnostic pattern. Renaming
  `razorpay_event_id` → `provider_event_id` + a `provider` field would
  make this genuinely reusable with minimal change.
- The **"never let processing failure affect the HTTP response"**
  principle (D3's core rule) is provider-agnostic by nature — it's about
  how *you* handle your own logic, not about the provider's API shape.

**Not provider-neutral today, and would need real work to become so:**
- `verify_webhook_signature` — hand-rolled for Razorpay's exact
  construction; a second implementation would be needed for Cashfree,
  behind a shared interface that doesn't exist yet.
- `Plan.razorpay_plan_id` / (D3's) `Subscription.razorpay_subscription_id`
  — provider-specific field names. A genuine multi-provider design would
  need either a generic `external_id` + `provider` pair, or one field
  per provider — a real schema decision, not a rename.
- The **checkout integration itself** (frontend hook + backend
  create-checkout endpoint) — built entirely around Razorpay's embedded
  widget. This is the deepest non-portable piece; no backend abstraction
  layer papers over a fundamentally different frontend UX pattern.

## 5. Recommendation

**Don't switch now, for two reasons:**

1. **Razorpay's blocker has a defined, short timeline** (24-48h business
   verification, already submitted) — waiting it out is cheap compared
   to redoing D1's signature logic and D2's checkout integration for a
   different provider's different patterns.
2. **Razorpay was chosen for a real, stated reason** — better fit for an
   India-based portfolio, since Stripe's support for Indian merchants is
   limited. That reasoning hasn't changed; Cashfree doesn't add anything
   Razorpay doesn't already offer for this project's actual purpose.

**What I'd do instead:** treat this assessment as a documented fallback
option, not an active plan. If Razorpay's verification genuinely stalls
well past its stated window, revisiting Cashfree (via its
hosted-checkout path specifically, per §1) is a legitimate, verified-viable
plan B — but activating it now, while Razorpay's fix is still pending
and on a known clock, would mean redoing real work for a problem that's
likely about to resolve on its own.

**If you do eventually pursue a genuine multi-provider design** (not
just "switch which one is currently active," but "support both"), §4's
gaps are the real scope of that work — worth keeping this document
around as the starting point when that's actually decided, rather than
re-deriving it later.

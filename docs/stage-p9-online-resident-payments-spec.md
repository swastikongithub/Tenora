> **Superseded in part (2026-09-16).** P9 was implemented with **Cashfree**
> (hosted checkout, API version 2025-01-01), not Razorpay/Route, per the P9
> implementation brief. The domain design below (separate property gateway,
> `OnlinePaymentAttempt`, webhook-only settlement, UNAPPLIED + refund, no void
> of online payments, full-amount-only) was kept; provider-specific details
> (Route transfers, Razorpay signatures/event names) no longer apply. Settlement
> routing to individual owners (Cashfree Easy Split vendors) remains an open
> decision — see the P9 implementation report.

# Stage P9 — Online Resident Payments (specification, awaiting approval)

Status: **DRAFT — no P9 code may be written until this document is approved.**
Parent plan: `docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md` §18, §35, Phase P9.
Builds on: `docs/payment-gateway-adapter-spec.md`, `docs/stage-d2-spec.md`
(checkout), `docs/stage-d3-v2-spec.md` (webhook processing), P1–P8 and P10
(`apps.properties`).

---

## 0. Summary

A resident can pay a published property bill online from their bill page. The
money is a **resident → workspace owner** payment. It is recorded as an ordinary
`apps.properties.Payment` (method `ONLINE`) with its receipt — but **only after a
signature-verified gateway webhook confirms capture**, never from anything the
browser reports. Nothing about it touches `Plan`, `Subscription`,
`SubscriptionCheckout` or `WebhookEvent`, and a property payment is never
evidence of a Tenora subscription payment (plan §35).

---

## 1. Decisions that need approval

These change money flow, compliance or existing rules. Each has a
recommendation; the rest of the spec assumes the recommendation.

### D1 — Where the money goes (settlement model) — **blocking**

| Option | What it means | Assessment |
|---|---|---|
| **A. Razorpay Route (recommended)** | Tenora's Razorpay account creates the order with a `transfers` entry to the owner's **linked account**; Razorpay settles to the owner. Tenora never holds the owner's API keys. | Correct marketplace model. Needs Route enabled on Tenora's Razorpay account and a KYC'd linked account per owner. Live verification blocked until the account is activated (the Subscriptions product is already blocked account-side). |
| B. Owner's own Razorpay keys | Each workspace stores its owner's key id + secret; orders are created on the owner's account. | Tenora must store third-party API secrets (encryption at rest, key rotation, a new secret-management surface) and route webhooks per workspace. Higher security surface. |
| C. Tenora collects, pays owners out | Money lands in Tenora's account. | **Not recommended.** Collecting and holding funds on behalf of merchants is payment-aggregator activity (RBI PA regulation in India). Out of scope for this project. |

Until D1-A is live, the feature ships **disabled by default** and fully testable
with the mock adapter.

### D2 — Amount a resident may pay online
**Recommended: the full amount due only**, computed on the server at attempt
creation. Part-payments stay an owner-recorded offline workflow. (Alternative:
any amount between a minimum and the amount due.)

### D3 — Money captured that can no longer be applied
The bill can change between checkout and capture: the owner records a cash
payment, cancels the bill, or applies a downward correction. Overpayment is
refused (existing rule), so the captured money cannot always become a
`Payment`.
**Recommended for MVP:** mark the attempt `CAPTURED_UNAPPLIED`, record nothing
on the bill, notify the owner and the resident, and show it to the owner and the
platform admin for a **manual refund** in the Razorpay dashboard. Automated
refunds via API are a later stage. (Alternative: automatic refund through the
adapter — adds a refund state machine and a second webhook family now.)
To make this rare, while a live attempt exists (≤ 30 min), bill **cancel** and
**downward corrections below paid + pending** are refused with a clear error;
recording an offline payment is still allowed (the owner may be standing in
front of the resident with cash).

### D4 — Voiding an ONLINE payment
**Recommended:** `PaymentService.void` refuses `method=ONLINE`
(`ONLINE_PAYMENT_NOT_VOIDABLE`). Money that really moved must be reversed by a
refund, not hidden by a void. Refunds are out of P9 scope.

### D5 — Amend the CLAUDE.md property-billing rule
Today: "Nothing in `apps.properties` references Plan, Subscription or the
payment gateway." P9 needs the gateway **infrastructure**. Proposed wording:
"`apps.properties` never references Plan, Subscription, SubscriptionCheckout or
WebhookEvent, and never calls a subscription gateway method. It may use only the
collection interface (`get_collection_gateway()`)."

### D6 — Who pays the gateway fee
**Recommended:** the owner absorbs it. The resident is charged exactly the
amount due; no convenience fee line is added. (A fee line would need its own
bill-line and receipt semantics.)

---

## 2. Architecture

```
Resident browser ──POST /api/bills/<id>/pay-online/──▶ OnlinePaymentService.start()
       │                                              ├─ lock bill, compute amount_due
       │                                              ├─ get_collection_gateway().create_order(...)
       │                                              └─ OnlinePaymentAttempt(CREATED)
       │◀──── {key_id, order_id, amount, currency} ────┘
       │
       ├── Razorpay Checkout (order mode) ──▶ success handler
       │        POST /api/online-payments/<id>/confirm/  (UI feedback ONLY; verifies
       │        HMAC(order_id|payment_id); sets nothing but `client_confirmed_at`)
       │
Razorpay ──POST /api/webhooks/razorpay/property-payments/──▶ verify signature (own secret)
                                                             ├─ PropertyWebhookEvent (unique event id)
                                                             └─ OnlinePaymentService.apply_capture()
                                                                  ├─ lock attempt + bill
                                                                  ├─ PaymentService.record(method=ONLINE,
                                                                  │     idempotency_key=attempt.id,
                                                                  │     reference=provider payment id)
                                                                  └─ attempt CAPTURED (+ receipt, notify, audit)
```

### 2.1 Gateway interface — a separate collection interface
`apps/billing/gateway/base.py` gains a **second ABC**, `CollectionGatewayAdapter`,
next to `PaymentGatewayAdapter`. The two are deliberately separate so no
subscription method can be called from property code, and vice versa.

```python
class CollectionGatewayAdapter(abc.ABC):
    def create_order(self, *, amount_minor: int, currency: str, receipt: str,
                     notes: dict, transfer_account_id: str | None) -> str: ...
    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool: ...
    def verify_collection_webhook_signature(self, headers, raw_body: bytes) -> bool: ...
    def parse_collection_webhook(self, headers, raw_body: bytes) -> NormalizedCollectionEvent: ...
    def fetch_order_state(self, order_id: str) -> ProviderOrderState | None: ...  # read-only
```

- `RazorpayGatewayAdapter` and `MockGatewayAdapter` implement **both** ABCs, so
  `apps.billing.gateway.razorpay` stays the only module that imports `razorpay`.
- `get_collection_gateway()` sits beside `get_gateway()`, driven by the same
  `settings.PAYMENT_GATEWAY`.
- `CollectionEventType`: `PAYMENT_CAPTURED`, `PAYMENT_FAILED`, `ORDER_PAID`,
  `UNKNOWN`. Razorpay mapping: `payment.captured`, `payment.failed`,
  `order.paid`.
- Checkout signature: HMAC-SHA256 of `f"{order_id}|{payment_id}"` keyed with
  `RAZORPAY_KEY_SECRET`, timing-safe. **To be verified against Razorpay's SDK
  before implementation**, as D2 did; the order of the two ids matters.
- The webhook uses a **separate secret**, `RAZORPAY_PROPERTY_WEBHOOK_SECRET`,
  and a separate URL, so subscription and property events can never be
  confused, replayed across endpoints, or processed by the wrong service.

### 2.2 New models (additive migration only)

**`WorkspaceSettings`** — add fields:
- `online_payments_enabled` (bool, default False)
- `payout_account_id` (char, blank) — the Route linked-account id; an id, not a secret

**`OnlinePaymentAttempt`** (`apps.properties`, `TenantScopedManager`):

| Field | Notes |
|---|---|
| `id` UUID | also the `Payment.idempotency_key` when applied |
| `tenant`, `bill`, `resident` | PROTECT; resident taken from `request.user`, never from the client |
| `amount_cents`, `currency` | server-computed at creation; immutable |
| `status` | `CREATED` → `CAPTURED` / `CAPTURED_UNAPPLIED` / `FAILED` / `EXPIRED` |
| `provider` | e.g. `razorpay` |
| `external_order_id` | unique |
| `external_payment_id` | unique when set |
| `payment` | OneToOne to `Payment`, null until applied |
| `client_confirmed_at`, `captured_at`, `expires_at` | timestamps |
| `failure_code`, `failure_reason` | sanitized provider text, ≤ 255 chars; never the raw payload |
| `unapplied_reason` | e.g. `BILL_CANCELLED`, `AMOUNT_EXCEEDS_DUE` |

Constraints:
- partial unique: one `CREATED` attempt per bill (a double click reuses it)
- check: `amount_cents > 0`

**`PropertyWebhookEvent`** (not tenant-owned, like `WebhookEvent`):
- fields: `external_event_id` **unique** (the idempotency guarantee),
  `event_type`, `external_order_id` (indexed), `external_payment_id`,
  `raw_payload`, `processed`, `received_at`, `processed_at`,
  `processing_error` (class name only)

**`Payment`** — add `online_attempt` reverse relation only. `method=ONLINE`
already exists, and `recorded_by` stays null for gateway-applied payments.

### 2.3 State machine (explicit table, like `SubscriptionService`)

| From | Event | To |
|---|---|---|
| CREATED | verified capture; bill open and amount ≤ due | CAPTURED (+ Payment + Receipt) |
| CREATED | verified capture; bill cancelled or amount > due | CAPTURED_UNAPPLIED |
| CREATED | verified `payment.failed` | stays CREATED (Checkout allows a retry), failure fields updated |
| CREATED | `expires_at` passed and provider order unpaid (sweep) | EXPIRED |
| EXPIRED | verified capture (late) | CAPTURED or CAPTURED_UNAPPLIED |
| CAPTURED / CAPTURED_UNAPPLIED | any | no-op (terminal) |

---

## 3. Services (all mutations here; views stay thin)

`apps/properties/online_payments.py` → `OnlinePaymentService`:

- **`start(*, user, tenant, bill)`**
  - Refused unless:
    - `settings.PROPERTY_ONLINE_PAYMENTS_ENABLED` is on,
    - the workspace has `online_payments_enabled` and a `payout_account_id` (D1-A),
    - the bill is visible to this resident, issued and open, with amount due > 0,
    - the currency is INR.
  - Locks the bill row. Reuses a live `CREATED` attempt; otherwise creates the
    provider order **inside the transaction**, exactly the D2
    `create_checkout` trade-off (the order create has no idempotency key).
  - Catches `IntegrityError` outside `atomic`.
- **`confirm(*, user, attempt, order_id, payment_id, signature)`**
  - Verifies the checkout signature against the attempt's own `external_order_id`,
    never the body's alone.
  - Sets `client_confirmed_at`. **Creates nothing.**
- **`apply_capture(event)`**
  - Locks the attempt, then the bill.
  - Applies D3, then `PaymentService.record(... method=ONLINE,
    idempotency_key=str(attempt.id), reference=payment_id, actor=None)`.
    A redelivered or replayed capture hits the idempotency key and returns the
    same payment.
  - Writes a critical audit row, a receipt, and notifications (resident:
    payment received; owner: online payment received).
- **`record_failure(event)`**, **`expire_stale(now)`**
  - `expire_stale` is a read-only `fetch_order_state` check before marking an
    attempt EXPIRED. `ProviderUnavailable` → skip, never expire.

`PropertyWebhookService.record_event` / `process_event` mirror D1/D3:
- store first (the unique collision absorbs redelivery), then process inline;
- a processing failure never changes the 200 response;
- `manage.py process_property_webhooks` retries unprocessed rows.

`BillService.cancel` and `BillCorrectionService` gain the D3 guard;
`PaymentService.void` gains the D4 guard.

---

## 4. API

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/api/bills/<id>/pay-online/` | resident (`billing.view_own`) on own bill | Returns `{attempt_id, key_id, order_id, amount_cents, currency, expires_at}`. Tenant from header. No amount in the body — any body amount is ignored. Throttled per user. Owners get 403 (they record offline payments). |
| POST | `/api/online-payments/<id>/confirm/` | the attempt's resident | UI feedback only. Returns `{status}`. |
| GET | `/api/online-payments/<id>/` | attempt's resident; workspace owner | Status polling for the "processing" screen. |
| GET | `/api/online-payments/` | owner (`payments.manage`) | Filter by status; unapplied attempts first. Never includes `raw_payload`. |
| PATCH | `/api/workspace/settings/` | owner | Adds `online_payments_enabled`, `payout_account_id`. |
| POST | `/api/webhooks/razorpay/property-payments/` | gateway (no auth, signature is the auth) | Separate URL and secret. |
| GET | `/api/platform/property-billing/online-payments/` | platform staff | Cross-workspace list, including unapplied. |
| GET | `/api/platform/property-billing/webhook-events/` | platform staff | Raw payload view is observational-audited, like the existing subscription webhook raw view. |

`GLOBAL_PATHS` additions (exact match; frontend mirror and parity test updated):
- `/api/platform/property-billing/online-payments/`
- `/api/platform/property-billing/webhook-events/`

The webhook path also becomes global, the same way `/api/webhooks/razorpay/`
already is. Everything else in the table is tenant-scoped.

Error codes (stable):
- `ONLINE_PAYMENTS_DISABLED`
- `BILL_NOT_PAYABLE`
- `NOTHING_DUE`
- `CURRENCY_NOT_SUPPORTED`
- `PAYMENT_IN_PROGRESS`, on cancel or correction
- `ONLINE_PAYMENT_NOT_VOIDABLE`
- `INVALID_CHECKOUT_SIGNATURE`

---

## 5. Frontend

- **Resident bill page and dashboard:**
  - A "Pay ₹X online" button, shown only when the API says the bill is payable
    online (new `online_payment` block on the bill detail: `{available, reason}`).
  - It opens Razorpay Checkout in order mode, generalizing
    `useRazorpayCheckout` to accept `order_id`.
  - After success the page shows "Payment processing…" and polls the attempt.
    It says "Paid" only when the server reports CAPTURED.
- **Owner:**
  - Settings → Billing: an "Online payments" toggle plus the payout account id,
    with a clear note that settlement goes to that account.
  - Payments list: the ONLINE method, the provider reference, and an
    **"Online payments needing refund"** alert for CAPTURED_UNAPPLIED attempts.
  - The void button is hidden for ONLINE payments (the backend refuses anyway).
- **Platform admin:** an online payments tab and a property webhook events tab.
- **Never shown:** raw provider payloads, to residents or owners.

---

## 6. Security and isolation rules (tests pin each one)

1. The amount comes only from the server. A body `amount`, `bill_id` swap,
   `tenant_id` or `resident_id` is ignored or 404.
2. A resident can start an attempt only for their own published open bill;
   anything else is 404.
3. A `Payment` exists only after a verified webhook, never from `/confirm/`.
4. Signature failure → 400, nothing stored. Duplicate event id → 200, no second
   effect.
5. A subscription-webhook body sent to the property endpoint fails its
   signature (different secret). A property event with a valid signature but an
   unknown order id is stored and processed as a no-op.
6. Cross-workspace: an order id belonging to workspace A cannot apply to
   workspace B (the attempt row carries the tenant; nothing is looked up by
   client input).
7. Concurrency:
   - double-clicking "Pay" creates one attempt and one provider order;
   - a capture webhook racing an owner's cash entry cannot overpay (bill row
     lock plus the existing overpayment check lead to D3);
   - two concurrent deliveries of one capture produce one Payment (idempotency
     key plus unique `external_payment_id`).
8. No secret is ever serialized. `failure_reason` is sanitized and
   length-capped.

---

## 7. Tests

**Backend:**
- **Adapter contract:** both adapters implement both ABCs; the Razorpay
  signature construction is checked against a known vector.
- **Services:** `start` (enabled, disabled, wrong resident, draft, paid,
  cancelled, non-INR, reuse of a live attempt), `confirm`, `apply_capture`
  (normal, replay, amount > due, bill cancelled, late after EXPIRED),
  `record_failure`, `expire_stale` (paid at provider, unavailable provider).
- **Webhook view:** bad signature, missing event id, duplicate, unknown order,
  processing failure still 200, retry command.
- **Guards:** cancel, correction and void guards.
- **Concurrency:** threaded tests for double start and for capture racing a
  cash payment.
- **Isolation:** API-level tests for the rules in §6.
- **End to end with the mock adapter:** a resident pays March online →
  webhook → bill PAID → receipt → owner report counts it as collected.
- **Additions to existing suites:** a GLOBAL_PATHS parity update, and a new
  `properties.expire_online_payments` task in the beat-schedule expectations.
  That is additive, and it needs the same `test_scheduler` approval as P10's
  reminder task.

**Frontend:**
- the Pay button appears only when available;
- the Checkout options carry `order_id` and never a client-side amount;
- the processing state never claims "Paid" early;
- the owner refund-needed alert;
- the void button is hidden for ONLINE payments.

---

## 8. Configuration

| Setting | Default | Purpose |
|---|---|---|
| `PROPERTY_ONLINE_PAYMENTS_ENABLED` | `False` | Platform kill switch |
| `RAZORPAY_PROPERTY_WEBHOOK_SECRET` | `""` | Property webhook HMAC key; an empty value rejects every delivery |
| `PROPERTY_ONLINE_ATTEMPT_TTL_MINUTES` | `30` | Attempt expiry |

Existing `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are reused. No production
secret or infrastructure is changed by this stage. Setting the new secret and
registering the webhook URL in Razorpay are operator steps, documented rather
than performed.

---

## 9. Out of scope for P9

- Refunds (manual via the Razorpay dashboard for CAPTURED_UNAPPLIED).
- Partial online payments (D2), convenience fees (D6), saved cards, UPI
  autopay, recurring rent mandates.
- Non-INR currencies.
- Owner self-serve linked-account onboarding through Razorpay's API; for the
  MVP the owner or an operator enters the linked-account id.
- Email or SMS delivery; notifications stay in-app.

---

## 10. Delivery plan (each step green before the next)

1. **P9a — domain and mock:**
   - collection ABC, mock adapter, models plus additive migration, services,
     webhook endpoint, guards;
   - all backend tests.
2. **P9b — Razorpay adapter:**
   - order create with Route transfer, signature and webhook parsing,
     `fetch_order_state`;
   - verified against the SDK source and docs;
   - live verification recorded as **owed** until the account supports Route.
3. **P9c — frontend:** resident pay flow, owner settings and refund alert,
   admin tabs; frontend tests.
4. **Docs:** CLAUDE.md rule update (D5) and ops notes for webhook registration
   and secrets.

Each step: Django check, `makemigrations --check`, full backend suite, frontend
tests, typecheck, lint, build, then one commit.

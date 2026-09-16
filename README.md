# Tenora — multi-tenant property billing

Tenora is a multi-tenant SaaS for property owners: workspaces, properties and
units, residents and leases, electricity meters and tariffs, monthly bill
generation, payments and receipts, reminders and reports — plus online payment
collection from residents, and Tenora's own subscription billing for the
owners.

It is a portfolio project, and the engineering problems are the point rather
than feature count: **tenant isolation**, **idempotency**, **concurrency
correctness**, **webhook-driven state**, and **reconciliation**. Where a
shortcut would have made a demo look better but the system less honest, the
honest option was taken and written down.

**Live:** [app](https://tenora-frontend.onrender.com) ·
[API](https://tenora-l70u.onrender.com) (Render free tier — the first request
after idling wakes the service and can take ~30s)

---

## Two financial domains that never mix

The single most important thing to understand about this codebase is that it
contains **two separate money flows**, deliberately kept apart down to the
database table:

| | `apps.billing` | `apps.properties` |
|---|---|---|
| Who pays whom | workspace owner → **Tenora** | resident → **workspace owner** |
| What | SaaS subscription (Basic / Pro) | monthly property bills (rent, electricity, charges) |
| Provider | Cashfree **Subscriptions** (recurring mandate) | Cashfree **Payment Gateway** (one-off order) |
| Gateway seam | `apps.billing.gateway.get_gateway()` | `apps.properties.gateway.get_property_gateway()` |
| Webhook route | `/api/webhooks/cashfree/subscriptions/` | `/api/webhooks/cashfree/property-payments/` |
| Settings | `CASHFREE_SUBSCRIPTION_*` | `CASHFREE_*`, `PROPERTY_*` |

Neither imports the other. They share a vendor and nothing else — different API
families, credentials, event vocabularies and routes — so a change to one
cannot quietly alter the other.

---

## What it does

**Workspaces and people.** A `Tenant` is a workspace. Owners manage it;
residents (`Membership.Role.MEMBER`) see only their own billing. Nobody is ever
added silently — an invitation is created PENDING and only the invited user
accepting it creates the membership and resident profile. Authorization is by
capability (`property.manage`, `billing.manage`, `billing.view_own`, …), not
scattered role checks. Plan limits on workspaces and seats are enforced under
row locks, with pending invitations reserving a seat.

**Property setup.** Properties → units → leases (with monthly rent) → meters
(with multipliers) → readings, plus an electricity tariff with effective dates
and full rate history.

**Billing.** Open a monthly cycle, generate draft bills from the leases,
readings and the tariff in force, review, then publish. Issued bills are
immutable history: they snapshot names, rent, readings, rates and totals, and
change afterwards only through a `BillCorrection` (a visible adjustment line
with a reason and an author) or a payment. Overdue is always derived from the
server date, never stored. Money is integer minor units end to end; rounding
happens in exactly one place.

**Payments and receipts.** Offline payments (cash, UPI, bank transfer) are
recorded by the owner; online payments are collected from residents through
Cashfree. Every payment issues a numbered receipt, and both bills and receipts
download as PDFs. Aging and collection reports, portfolio roll-ups across
workspaces, and scheduled due/overdue reminders are included.

**Online resident payments (P9).** A resident pays their bill from the resident
portal. The browser never supplies an amount or an outcome: the server fixes the
amount, creates the provider order, and only a **verified capture** settles the
bill — through the same `PaymentService.record` path an offline payment uses.
Transient checkout state lives on `OnlinePaymentAttempt`, never on `Payment`.

**Tenora subscriptions.** Owners subscribe through Cashfree Subscriptions
(recurring mandates: UPI AutoPay, card, eNACH). A local `Subscription` row is
never created from anything the client reports — only a verified webhook creates
or changes it. Plan changes follow explicit billing rules (below).

**Operator control plane.** A staff-only admin surface spanning tenants,
plans, subscriptions, webhook events, reconciliation, users and an audit log,
with root-tier controls and workspace suspension.

**Accounts.** JWT auth (SimpleJWT) with refresh rotation, Google sign-in, email
verification, password change, and account deletion that anonymises rather than
hard-deletes.

---

## Engineering decisions worth reading

These are the parts a reviewer should look at; each was deliberated, and most
are pinned by tests that fail if the reasoning is undone.

**Tenant isolation.** Tenant resolution lives in a DRF *authentication class*
(`apps/tenants/authentication.py`), not Django middleware — SimpleJWT
authenticates after the middleware stack, so middleware could not rely on
`request.user`. `tenant_id` is never accepted from a request body on any
endpoint; it comes only from the `X-Tenant-ID` header plus an ACTIVE
`Membership`. Cross-tenant access returns **404, never 403** — a 403 confirms
the object exists. The exemption list is an exact-match frozenset, because a
prefix would silently exempt every future sub-route.

**Idempotency is a database constraint, not a check.** Webhook deduplication is
a unique index on the provider's delivery id (or a digest of the verified raw
body); one open checkout per bill, one payment per provider capture, and one
subscription per tenant are all unique constraints. `IntegrityError` is caught
*outside* the `atomic()` block that raised it, because Postgres marks the
transaction broken otherwise.

**Webhooks are the authority.** Signatures are verified on the **raw body**
before anything is parsed, and a failed check stores nothing. Provider events
are normalised into the project's own vocabulary inside the adapter, so domain
code never sees provider JSON. Subscription state changes only through
`SubscriptionService` and its explicit legal-transition table.

**Money the browser cannot influence.** Amounts, orders and outcomes are all
server-side. The browser receives an opaque session token, never a key, never a
price it can edit.

**Plan changes are billing decisions.** One policy answers both entry points, so
a client cannot get a different answer by picking a different endpoint:
same plan is a no-op; Basic → Pro is a paid upgrade that must go through
checkout; downgrades and monthly↔annual switches are refused (no proration
semantics have been designed, and inventing one would be a guess about the
customer's money); an unclassified plan code fails closed. An upgrade takes
effect **only** when the new mandate's webhook activates — until then the
existing subscription keeps running untouched, so an abandoned checkout or a
failed authorisation changes nothing.

**Failing closed.** When a provider is unreachable or returns a status the
adapter does not recognise, the answer is "unknown" — never "safe to discard".
An abandoned checkout can be replaced only when it is unconfirmed, past a
staleness window, *and* the provider confirms it was never taken up.

---

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, Django 5, Django REST Framework, SimpleJWT |
| Database | PostgreSQL |
| Async | Celery + Redis (webhook retry sweep, reminders, reconciliation, usage snapshots) |
| Payments | Cashfree (subscriptions + payment gateway), behind per-domain adapters |
| Frontend | React 19, TypeScript, Vite, TanStack Query, Tailwind |
| Frontend tests | Vitest, Testing Library, MSW |
| Packaging | Docker Compose (frontend, backend, Postgres, Redis, worker, beat) |
| Hosting | Render (two services: static frontend + Dockerised backend) |

## Repository layout

```
apps/
  users/         accounts, auth, email verification, Google sign-in
  tenants/       workspaces, memberships, invitations, plan limits, capabilities
  properties/    the property domain: properties, units, residents, leases,
                 meters, readings, tariffs, cycles, bills, payments, receipts,
                 reports, and P9 online resident payments (own gateway package)
  billing/       Tenora's own subscriptions: plans, checkout, webhooks,
                 proration records, reconciliation (own gateway package)
  notifications/ in-app notifications and reminder delivery
  platform/      operator control plane (staff-only, cross-tenant)
config/          settings, URLs, Celery app
frontend/        React app (see frontend/README.md)
docs/            specifications — one per stage, written before the code
```

---

## Running it

Two independent ways; Docker is additive, not a replacement.

### Docker

```
cp .env.example .env
docker compose up --build
```

Open **http://localhost:8080** and sign in with the seeded demo account:

```
demo@example.com / demo-pass-12345
```

That seed is throwaway public demo data (one workspace, plans, a trialing
subscription) so the dashboard has something to show. It is idempotent, and
`SEED_DEMO_DATA=false` disables it.

Default host ports, each overridable in `.env` if taken: frontend `8080`
(`FRONTEND_HOST_PORT`), backend `8001` (`BACKEND_HOST_PORT`), Postgres `5433`
(`DB_HOST_PORT`).

### Manually

Prerequisites: Python 3.12, Node 20+, PostgreSQL (Redis only if you want the
background jobs — not needed for the app or the tests).

```
python -m venv .venv
.venv\Scripts\activate            # Windows; source .venv/bin/activate elsewhere
pip install -r requirements/base.txt
cp .env.example .env              # set POSTGRES_PASSWORD etc.
python manage.py migrate
python manage.py runserver
```

```
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

### Background jobs (optional)

```
celery -A config worker --loglevel=info
celery -A config beat   --loglevel=info
```

The same work is available on demand: `process_webhook_events`, `meter_usage`,
`reconcile_subscriptions`, `reconcile_online_payments`, `send_billing_reminders`.
The test suite runs tasks in-process and never needs Redis.

### Email verification

Registration creates an **unverified** account and password login is refused
until the emailed link is used. No real email provider is configured (a
deliberate boundary — `docs/email-verification-spec.md` §4.6): Django's console
backend prints the message. Find the `http://.../verify-email?token=...` link in
the backend terminal, or `docker compose logs backend`.

---

## Configuration

Every variable the stack reads is documented in `.env.example`; `.env` itself is
gitignored and no secret is ever committed. The groups that matter:

| Group | Purpose |
|---|---|
| `POSTGRES_*`, `DJANGO_*`, `CORS_ALLOWED_ORIGINS` | core service configuration |
| `PAYMENT_GATEWAY` | which subscription adapter is active: `cashfree`, `razorpay` or `mock` |
| `CASHFREE_SUBSCRIPTION_*` | Tenora subscription credentials, environment, API version, webhook tolerance |
| `PROPERTY_PAYMENT_GATEWAY`, `PROPERTY_ONLINE_PAYMENTS_ENABLED`, `CASHFREE_*` | P9 resident payments (kill switch defaults to off) |
| `SUBSCRIPTION_CHECKOUT_STALE_AFTER_MINUTES` | how long an in-flight checkout is presumed live |
| `EMAIL_*`, `GOOGLE_OAUTH_CLIENT_ID`, `FRONTEND_URL`, `BACKEND_PUBLIC_URL` | delivery, sign-in and the URLs providers redirect to |

Use **sandbox** credentials for anything but production. Both webhooks must be
registered in the Cashfree dashboard — the subscription one under the
Subscriptions tab, at API version `2026-01-01`.

---

## Tests

```
python manage.py test            # backend — 961 tests
cd frontend && npm test          # frontend — 557 tests
```

Backend tests use a `mock` gateway (`@override_settings(PAYMENT_GATEWAY="mock")`
or by patching `get_gateway`) and never touch the network; provider adapters are
tested against recorded fixtures, including signature verification with known
vectors. Concurrency guarantees are tested with real threads on real
connections (`TransactionTestCase`), not simulated. Frontend tests run against
the real app with MSW-stubbed endpoints.

---

## Status and known gaps

Stated plainly, because a README that overclaims is worse than one that admits
where the edges are.

- **P9 resident payments are verified end to end** against the deployed backend
  and the real Cashfree sandbox: order creation, hosted checkout, webhook
  delivery and signature verification, settlement, exactly one payment and one
  receipt, idempotent refreshes, failed and pending outcomes, and access
  isolation between residents and workspaces.
- **Duplicate webhook replay was not verified live** — the Cashfree dashboard's
  webhook log was unavailable at the time. It is covered by a unique constraint
  on the delivery digest, two further idempotency guards, and an automated test.
- **Cashfree subscriptions are verified end to end** against the deployed
  backend and the real sandbox: the three plans are synced
  (`tenora_basic_monthly`, `tenora_pro_monthly`, `tenora_pro_annual`), a mandate
  was authorised in the browser, and its signed webhook activated exactly one
  subscription on the intended plan through `SubscriptionService`. The
  downgrade and billing-cycle refusals were confirmed on production too.
- **Returning from the Cashfree mandate page renders a blank `/subscription`.**
  Cosmetic but real: the webhook has already activated the subscription by
  then, so no state is lost — the page just fails to show it. Not yet
  diagnosed.
- **Subscription period dates can start a cycle late.** A subscription created
  on 16 Sep came back with `current_period_start` of 16 Oct, because the period
  is taken from the CHARGED event's `next_schedule_date` rather than the cycle
  actually being paid for.
- **A CHARGED event that overtakes its own ACTIVATED stays unprocessed.** When
  the charge webhook lands a fraction of a second before the activation it
  describes, there is no subscription to attach it to yet, so it waits in the
  out-of-order retry window — which only the Celery sweep clears, and Render's
  free tier runs no worker. `python manage.py process_webhook_events` is the
  manual path. Subscription state is unaffected; the event is simply pending.
- **Render's free tier runs no worker**, so scheduled Celery work does not
  execute in production; the management commands above are the manual path.
  See `docs/worker-scheduler-operations.md`.
- Settlement reaches the Tenora merchant account; routing payouts to individual
  owners would need Cashfree Easy Split.

## Documentation

`docs/` holds a specification per stage, written before the code and kept as the
record of what was decided and why — `project-master-spec.md` for the
subscription platform, `TENORA_PROPERTY_BILLING_MASTER_PLAN.md` for the property
domain, `payment-gateway-adapter-spec.md` for the gateway seam,
`operator-control-plane-spec.md` for the admin surface, and the numbered stage
specs for everything else. `CLAUDE.md` lists the architecture rules that must
not be "fixed" back.

## Security notes

No card numbers, CVVs or expiry dates are ever stored — the provider owns
payment collection. Webhook signatures are verified on the raw body before
parsing. Credentials live only in the environment, never in the repository, and
are never logged: provider diagnostics record the error code, type, message and
a sanitised request body, with subscriber contact details redacted.

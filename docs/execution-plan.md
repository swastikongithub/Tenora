# Execution Plan — Multi-Tenant SaaS Billing Engine

## Part 1 — Blockers to Clear Before Any Coding

Five open decisions. Three of them block work that's already queued, so answer these first — none need more than a sentence.

| # | Decision | Blocks | Recommendation |
|---|---|---|---|
| 1 | **User signup** — no endpoint exists anywhere | The entire UI, and add-member (which requires an *existing* user) | Add a minimal `POST /api/auth/register/` (email + password, no email verification). Without it, users can only be created via Django shell and the app is undemoable. |
| 2 | **Frontend framework** | All UI work | React + Vite + TypeScript + Tailwind. Matches your existing portfolio work, so you're not learning a stack and a domain simultaneously. |
| 3 | **Frontend repo location** | Repo setup | Same repo, `frontend/` directory. One repo is easier to show and to clone for a reviewer. |
| 4 | **Plan billing interval** | Plans UI, later proration | Add `interval` field (`MONTHLY`/`ANNUAL`) to `Plan` now while it's cheap — proration needs it in Phase 2 anyway. |
| 5 | **Light vs dark theme** | UI build | Dark, as specced. Only revisit if you dislike it. |

Answer these, then everything below is unblocked.

---

## Part 2 — Build Sequence

Each step is one Claude Code session with its own spec, its own tests, and its own commit. Do not merge steps.

### Stage A — Get the existing code actually running (do this first)
**A1. Repo audit and environment.** You have Phase 1 files but they've never been run — no migrations, no Postgres, no verified boot. Get `python manage.py check`, `makemigrations`, `migrate`, and the existing isolation test suite running locally. Expect the isolation tests to fail (no views exist yet) — that's correct and expected.
**A2. Signup endpoint** (decision #1) + `Plan.interval` field (decision #4). Small, gets migrations settled early.

### Stage B — Finish Phase 1 backend
**B1. Tenant API layer** — `POST /api/tenants/`, `GET /api/tenants/me/`, `GET/POST /api/memberships/`. Spec already written (`antigravity-phase1-tenant-api-prompt.md`) — hand it to Claude Code instead, it works as-is.
**B2. Plan/Subscription API layer** — `GET /api/plans/`, `GET/POST/PATCH /api/subscriptions/current/`.
**B3. Real-JWT integration tests** — closes the known gap where the isolation suite bypasses `TenantJWTAuthentication` via `force_authenticate`. **Phase 1 is not done until this passes.**

### Stage C — Frontend
**C1. Scaffold + design tokens + component primitives** (Button, Input, Table, Card, Badge, Modal, Skeleton, EmptyState).
**C2. API client + auth + tenant switcher + app shell.** This is the highest-risk frontend piece — the header logic and cache-clearing-on-tenant-switch. Do it as its own session.
**C3. Login + Workspace pages.**
**C4. Members page.**
**C5. Subscription & Plans page.**
**C6. Overview dashboard.**

**Checkpoint: this is a complete, demoable, CV-worthy project.** Everything past here is upside. If you stall, stall here, not mid-Phase-2.

### Stage D — Phase 2 (the parts that actually differentiate you)
**D1. Stripe setup** — test mode, Stripe CLI (`stripe listen`) for local webhook forwarding. Set this up before writing webhook code, not after.
**D2. Stripe customer/subscription creation.**
**D3. `WebhookEvent` model + signature verification + idempotency.** ← the single best interview story in the project.
**D4. Out-of-order event handling.** (Decide the exact mechanism first — it's still open in §E.)
**D5. Usage metering + ingestion idempotency + concurrency test.**
**D6. Proration.**
**D7. Celery + retries.**
**D8. Reconciliation.**

Stop at D8. That's v1.0.

---

## Part 3 — How to Use Claude Code Well

### Setup
1. Install (native installer, no Node needed): macOS/Linux `curl -fsSL https://claude.ai/install.sh | bash`; Windows uses the PowerShell `irm` command from the docs. On Windows also install Git for Windows.
2. Verify with `claude --version`. If anything misbehaves later, `claude doctor`.
3. `cd` into your project directory, run `claude`, authenticate with your Claude.ai account.
4. Docs: https://code.claude.com/docs/en/overview

### The one thing that matters most: CLAUDE.md
Create a `CLAUDE.md` in your repo root. Claude Code reads it automatically at the start of every session — it's persistent project context so you don't re-explain your architecture every time. Put in it:

```markdown
# Multi-Tenant SaaS Billing Engine

## Architecture rules (do not violate)
- Tenant resolution lives in TenantJWTAuthentication (DRF auth layer), NEVER Django middleware.
- GLOBAL_PATHS is an exact-match frozenset. Never convert to prefix matching.
- Tenant-owned querysets go through TenantScopedManager.for_tenant(tenant). No ad hoc .filter(tenant=...).
- tenant_id is NEVER accepted from a request body, on any endpoint.
- Cross-tenant object access returns 404, never 403.
- Status codes: missing/malformed X-Tenant-ID = 400; valid header no membership = 403.
- All mutations go through services. No business logic in serializers or views.
- Subscription status changes only via SubscriptionService. CANCELED is terminal.
- Never store card numbers/CVV. Stripe owns payment collection.

## Commands
- Tests: python manage.py test
- Check: python manage.py check

## Before implementing
Read the relevant files first. If the repo contradicts the spec, report it — don't silently pick one.
```

This single file prevents most architectural drift.

### Session workflow
```
1. Give it the implementation spec (one feature, not the whole app)
2. Ask it to inspect the repo and produce a PLAN first — do not let it write code yet
3. Read the plan. Correct it. Approve it.
4. Let it implement
5. Make it run the tests
6. Review the diff yourself
7. Commit before starting the next feature
```

Step 2 is the one people skip and regret. A wrong plan costs one message to fix; wrong code costs a session.

### Practical habits
- **One feature per session.** Long sessions degrade — context fills, and on Pro you'll hit limits faster.
- **Commit often.** Every working feature. Claude Code can and will modify multiple files; git is your undo.
- **Use plan mode** (Shift+Tab cycles modes) for anything architectural.
- **`/clear` between unrelated tasks** to reset context rather than starting a new session.
- **Make it run tests, don't take its word.** "The tests should pass" is not the same as green output.
- **Push back when it's wrong.** You've done this well throughout this project — same instinct applies. It's a tool, not an authority.

### Division of labor
- **This chat (Claude, architect):** specs, architecture decisions, reviewing Claude Code's output, UI specs, catching drift.
- **Claude Code (engineer):** reads the repo, writes code, runs tests, commits.

Bring Claude Code's diffs and test output back here for review before moving to the next stage. That review loop is what keeps the architecture coherent across ~15 build sessions.

### Managing Pro plan limits
Usage is shared between Claude chat and Claude Code, with session and weekly caps. Practical consequences:
- Do architecture/spec work here in chat, implementation in Claude Code — don't burn Code sessions on planning discussions.
- If you hit a limit mid-feature, commit what works before you're cut off.
- Long autonomous runs are expensive. Scoped, reviewed steps use less and produce better code anyway.

---

## Part 4 — Realistic Milestones

Solo, no deadline. Use these as checkpoints, not a schedule.

| Milestone | You can say... |
|---|---|
| End of Stage B | "Multi-tenant Django API with enforced tenant isolation and RBAC, proven by tests." |
| End of Stage C | "Full-stack multi-tenant SaaS app." ← **CV-ready** |
| End of D3 | "...with idempotent Stripe webhook processing." ← **the differentiator** |
| End of D5 | "...and usage metering with concurrency guarantees." |
| End of D8 | v1.0. Stop. |

Put it on your CV after Stage C. Update the bullets as D-stages land — don't wait for v1.0 to have something to show.

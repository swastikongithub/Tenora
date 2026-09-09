# Multi-Tenant SaaS Billing Engine

Django + DRF multi-tenant SaaS billing platform, with a React + TypeScript
frontend. A portfolio project — the engineering problems (tenant isolation,
idempotency, concurrency correctness, reconciliation) are the point, not
feature count or UI polish. Full specification: `docs/project-master-spec.md`.

There are **two independent ways to run this project** — pick whichever suits
you. Docker is additive; it does not replace the manual workflow.

## Run with Docker

**Prerequisites:** Docker Desktop (or Docker Engine + Compose) installed and
running.

```
cp .env.example .env
docker compose up --build
```

Open **http://localhost:8080**. Log in with the seeded demo account:

```
demo@example.com / demo-pass-12345
```

**This is throwaway, public demo data** — a demo user, one workspace ("Demo
Workspace"), two plans (Pro/Team), and a trialing subscription so the
dashboard has real data to show immediately. It is seeded automatically on
first start (`SEED_DEMO_DATA=true` in `.env.example`) and is safe to run
repeatedly — the seed command is idempotent, it will not duplicate rows on a
restart. Set `SEED_DEMO_DATA=false` in your `.env` to disable it. This is a
demo/review convenience, not a pattern to follow for real user data.

**Ports.** Chosen to avoid colliding with the manual workflow below, so both
can run at the same time if you want:

| Service  | Host port (default) | Override via `.env` |
|----------|----------------------|----------------------|
| frontend | `8080`               | `FRONTEND_HOST_PORT` |
| backend  | `8001`               | `BACKEND_HOST_PORT`  |
| Postgres | `5433`               | `DB_HOST_PORT`       |

If a port is already taken on your machine, set the corresponding variable in
`.env` and re-run `docker compose up --build`.

**Restarting** (`docker compose up` again after already running once) reuses
the existing named Postgres volume — migrations re-apply safely, and the demo
seed does not duplicate anything.

`.env` is gitignored; only `.env.example` (placeholder, non-secret values) is
committed. See it for every variable the stack reads.

## Run manually

**Prerequisites:** Python 3.12, Node 20+, PostgreSQL. Redis too if you want the
background jobs running (see below) — not needed just to run the app or the tests.

Backend:

```
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements/base.txt
cp .env.example .env            # then set POSTGRES_PASSWORD etc. to your local Postgres
python manage.py migrate
python manage.py runserver
```

Frontend (separate terminal):

```
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. See `frontend/README.md` for frontend-specific
details (stack, testing, design tokens).

### Background jobs (optional for local use)

Stage D7 adds Celery jobs: a webhook retry sweep (every 5 min) and a daily usage
snapshot. They need Redis as a broker. `docker compose up` runs them automatically;
manually you'd run, in two more terminals, with Redis up:

```
celery -A config worker --loglevel=info
celery -A config beat --loglevel=info
```

The same work is also available on demand as `python manage.py process_webhook_events`
and `python manage.py meter_usage`. The test suite runs tasks in-process and never
needs Redis.

## Email verification

Registering an account creates it **unverified** — password login is refused
until the emailed verification link is used. No real email provider is
configured (a deliberate scope boundary, not an oversight — see
`docs/email-verification-spec.md` §4.6 and `CLAUDE.md`): Django's console
`EMAIL_BACKEND` prints the verification email instead of sending it. Find it
in whichever server is running the backend —

- manual workflow: the terminal running `python manage.py runserver`
- Docker: `docker compose logs backend`

— and open the printed `http://.../verify-email?token=...` link.

## Tests

```
python manage.py test         # backend
cd frontend && npm test       # frontend
```

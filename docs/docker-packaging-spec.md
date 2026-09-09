# Claude Code Implementation Specification — Docker Packaging

**Scope:** package the full stack (PostgreSQL, Django backend, React frontend) so
it runs with `docker compose up --build` from a clean clone - no manual Postgres
install, no pg_hba.conf editing, no venv setup. This does NOT replace the
existing manual dev workflow (venv + npm run dev) - both must keep working,
side by side, as two valid ways to run the project.

**Not in scope:** any application code change beyond what packaging requires,
email verification, Google OAuth, Razorpay/Stage D, the Platform Admin
dashboard, the cancellation UI.

---

## 0. Prerequisite check (do first)

Confirm Docker Desktop (or Docker Engine + Compose) is installed and running on
the machine before writing anything. Report the Docker and Compose versions
found. If Docker isn't installed, stop and report that - this is a genuine
blocker, the same way Postgres/Python/Node being absent was a blocker in Stage A,
and installing Docker Desktop is the user's action to take, not something to work
around.

## 1. Objective

Right now, getting this project running requires: installing Postgres, resetting
its password via pg_hba.conf if forgotten, creating a database, creating a
Python venv, installing backend dependencies, running migrations, separately
installing frontend dependencies, and running two processes in two terminals.
That's real, documented friction (the entire Stage A process). This stage
collapses all of it into one command for anyone evaluating the project - an
interviewer, a reviewer, or future-you on a different machine.

This is an additive packaging layer, not a replacement. The existing
.venv + npm run dev workflow must be fully intact afterward - Docker is a
second, independent way to run the same code, not a migration off the first.

## 2. Inspect Before Implementing

```
CLAUDE.md
requirements/base.txt              - exact current backend dependencies/versions
config/settings.py                 - DATABASES, ALLOWED_HOSTS, DEBUG, SECRET_KEY
                                      handling, static files config (none yet -
                                      verify)
.env.example                       - existing documented env vars for the backend
frontend/package.json              - build script, exact dependency versions
frontend/vite.config.ts            - the existing dev-only proxy config from C2
                                      (section 4.7's "no CORS in dev" decision) -
                                      the production/Docker equivalent of this
                                      proxy is what nginx needs to replicate
frontend/.env.example (if present) - any frontend build-time env vars
docs/project-master-spec.md        - section F.5 (local Stripe/webhook testing
                                      gap, unrelated to this stage but check for
                                      any other Docker-relevant open item) and
                                      the section E note that Docker was
                                      "proposed, not committed" - this stage is
                                      what commits it
README.md (root, if one exists) and frontend/README.md - current setup
                                      instructions this stage must not contradict
```

Current state: full core product complete (Stages A through C6, navbar redesign,
AuthArtPanel redesign, light mode). Backend runs via manage.py runserver in a
venv; frontend via Vite dev server with a dev-only proxy to the backend.

## 3. Existing Functionality That Must Not Change

- The manual dev workflow (.venv\Scripts\activate, manage.py runserver,
  npm run dev) must work exactly as it does today, unmodified, after this
  stage. Docker is additive.
- No application code (views, models, components) changes to accommodate
  Docker - this is packaging/infrastructure only. If something in the app
  genuinely can't be containerized without a code change, stop and report why
  rather than modifying business logic to fit.
- All existing backend and frontend tests must still pass - this stage doesn't
  touch test-relevant code, but confirm by actually running both suites.

## 4. Required Changes

### 4.1 Backend Dockerfile

- Python base image matching the project's actual Python version (verify
  against what's been used in the venv, likely 3.12).
- Install requirements/base.txt. Add gunicorn as a new, justified
  dependency for serving in the containerized context (manage.py runserver
  is a dev server, not meant for anything resembling production use - this is
  the one new package this stage needs).
- An entrypoint script that: waits for the database to be ready (or relies on
  Compose's depends_on health check - prefer the health-check approach,
  it's more robust than a manual wait-loop), runs python manage.py migrate,
  then execs gunicorn.
- DEBUG should default to False in the containerized image - Django's debug
  error pages with full stack traces are not appropriate for something a
  stranger might run and poke at. DRF already returns structured JSON errors
  regardless of DEBUG, so API behavior doesn't regress; verify this holds.

### 4.2 Frontend Dockerfile - multi-stage build

- Stage 1: Node image, npm ci, npm run build (produces the Vite dist/
  output).
- Stage 2: an nginx image serving the built static files, reverse-proxying
  /api/* to the backend service by its Docker Compose service name - this
  is the direct, container-native equivalent of the Vite dev-server proxy from
  C2, and it means the frontend keeps calling relative /api/... paths exactly
  as it does today. This avoids needing django-cors-headers or any CORS
  configuration at all - same-origin from the browser's perspective, same
  architectural preference already established in C2 section 4.7. Do not
  introduce CORS configuration as an alternative approach.

### 4.3 docker-compose.yml

Three services:
- db - official postgres image, version matching what's been used locally
  (verify - Postgres 18 per the Stage A setup), environment variables for
  database/user/password, a named volume for data persistence, a health check
  Django's service depends on.
- backend - built from 4.1, depends on db's health check, reads
  configuration from environment variables (mirroring .env.example's keys).
- frontend - built from 4.2, depends on backend, exposes a host port
  (document which - e.g. localhost:8080 or similar, avoid colliding with
  common local dev ports like 3000/5173/8000 that might already be in use from
  the manual workflow).

### 4.4 Environment configuration

- A Docker-specific .env.example (or extend the existing one) documenting
  every variable docker-compose.yml expects, with safe non-secret defaults
  for local/demo use (e.g. a throwaway DJANGO_SECRET_KEY clearly marked as
  dev-only, not meant for any real deployment).
- The real .env used by Compose stays gitignored, same as the existing
  backend .env - don't commit actual values, only the example file.

### 4.5 Demo data seeding - explicit, opt-in, clearly labeled

A reviewer running this for the first time will hit a login screen with nothing
to log in with. Add a management command (or entrypoint step) that seeds a demo
user + demo tenant + demo plan(s), gated behind an explicit environment flag
(e.g. SEED_DEMO_DATA=true), defaulting to enabled in the packaged
docker-compose.yml specifically because the whole point of this stage is
letting a stranger try the app immediately - but implemented so it can be
turned off, and documented clearly as throwaway public demo credentials, not a
pattern to follow for real user data. Do not seed unconditionally with no way
to disable it.

### 4.6 Documentation

- A clear "Run with Docker" section in the project's README: prerequisites
  (Docker installed), the one command (docker compose up --build), the URL
  to open, and the demo credentials if seeding is enabled.
- Keep the existing manual setup instructions intact alongside this - present
  both as valid options, not one replacing the other.

## 5. Files Likely Affected

```
new:      Dockerfile (backend, likely at repo root or in a backend-specific
                       location - use judgment based on existing structure)
          frontend/Dockerfile
          frontend/nginx.conf (or similar, for the reverse-proxy config)
          docker-compose.yml
          docker-entrypoint.sh (or equivalent, for the backend's migrate-then-serve
                                 sequence)
          .env.example updates (or a new docker-specific example file)
          a management command for demo seeding (apps/.../management/commands/)
modified: requirements/base.txt (+gunicorn)
          README.md / frontend/README.md (new Docker section, existing sections
                                            preserved)
          .gitignore (if anything Docker-specific needs excluding, e.g. local
                       override compose files)
```

No change to application source files (models, views, components) unless
something is discovered that genuinely requires it - report before making any
such change.

## 6. Business Rules

- No real secrets committed anywhere - .env.example files document variable
  names with placeholder/dev-only values only.
- Demo-seeded data is explicitly, visibly labeled as demo/throwaway in
  documentation - never presented as if it were real user data guidance.

## 7. Security Requirements

- DEBUG=False in the containerized backend by default.
- The dev-only DJANGO_SECRET_KEY fallback already in config/settings.py
  stays as-is for convenience, but the Docker .env.example should make clear
  a real deployment would need a real, unique secret - this project isn't
  claiming to be production-hardened, just honestly packaged for demo/review.
- No card/payment fields, no new auth surface - this stage is infrastructure
  only.

## 8. Edge Cases

- Fresh clone, no .env present - docker compose up should fail with a
  clear error pointing at .env.example, not a cryptic crash.
- Common local ports (5432, 8000, 5173) already in use by someone's manual dev
  setup running simultaneously - document how to override the exposed host
  ports in Compose, since a developer might reasonably want both the manual
  workflow and the Docker workflow available without a permanent conflict.
- Restarting the stack (docker compose up again after already running once)
  must not re-run migrations destructively or duplicate demo-seed data - the
  seed command should be idempotent (check-then-create, not blind insert).

## 9. Tests / Verification Required

This stage is primarily infrastructure, not application code - verification is
mostly operational, not unit tests:
- docker compose up --build from a clean state succeeds without manual
  intervention.
- The frontend, reached via the documented host port, successfully calls the
  backend through nginx's reverse proxy (verify a real request round-trip, e.g.
  loading the plans list after logging in with the seeded demo account).
- Migrations apply automatically on first startup.
- Restarting the stack doesn't break or duplicate anything (section 8).
- The existing manual venv + npm run dev workflow still works, unchanged -
  run both test suites (manage.py test, npm test) in the manual environment
  to confirm nothing broke.

## 10. Acceptance Criteria

1. docker compose up --build succeeds from a clean clone (or as close to
   clean as achievable in this environment) and results in a working,
   reachable application.
2. Backend and frontend test suites still pass when run the traditional way
   (manual venv / npm) - exact counts reported, confirming zero regression.
3. Demo login works through the Dockerized stack end-to-end (login -> see real
   data from a real API call through the nginx proxy).
4. README documents both the Docker path and the existing manual path clearly.
5. No secrets committed; .env.example files are complete and accurate.
6. Report: exact Docker/Compose versions used, the chosen host ports and why,
   and confirmation that no application source file needed modification (or,
   if one did, exactly why and what).

## 11. Must NOT Do

- Do not remove, replace, or break the existing manual dev workflow.
- Do not add django-cors-headers or any CORS configuration - use the nginx
  reverse-proxy approach per section 4.2.
- Do not commit real secrets or a .env file with actual values.
- Do not seed demo data with no way to disable it.
- Do not modify application source code to accommodate packaging unless
  genuinely unavoidable - report before doing so.
- Do not start email verification, Google OAuth, Razorpay/Stage D, the
  Platform Admin dashboard, or the cancellation UI.

---

## Workflow

Confirm Docker is installed (section 0) before anything else. Then produce a
plan and wait for approval before writing any files. Given this is
infrastructure rather than typical feature code, the plan should clearly
separate what's genuinely new (Dockerfiles, compose config) from anything it
discovers might need a small, justified touch elsewhere - flag the latter
explicitly rather than just doing it.

---

## Ready-to-paste prompt for Claude Code

Read docs/docker-packaging-spec.md, then check whether Docker is installed and
running (section 0). Report the result. If Docker is available, inspect the
repository and produce an implementation plan, then wait for my approval
before writing any code.

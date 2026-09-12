#!/bin/sh
# Backend container entrypoint: migrate, optionally bootstrap a superuser
# and seed demo data, then serve with gunicorn (manage.py runserver is a
# dev server, not meant for this). No manual DB-wait loop here — docker-
# compose.yml's depends_on.db.condition: service_healthy already guarantees
# Postgres is accepting connections before this container even starts.
set -e

python manage.py migrate --noinput

# Bootstrap-only convenience for hosts with no shell/SSH access (e.g.
# Render's Free plan) to create the first superuser. The command itself is
# the no-op guard: it does nothing unless DJANGO_SUPERUSER_EMAIL and
# DJANGO_SUPERUSER_PASSWORD are both set, and never touches an
# already-existing user — see apps/users/management/commands/
# bootstrap_superuser.py.
python manage.py bootstrap_superuser

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  python manage.py seed_demo_data
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3

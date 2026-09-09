#!/bin/sh
# Backend container entrypoint: migrate, optionally seed demo data, then
# serve with gunicorn (manage.py runserver is a dev server, not meant for
# this). No manual DB-wait loop here — docker-compose.yml's
# depends_on.db.condition: service_healthy already guarantees Postgres is
# accepting connections before this container even starts.
set -e

python manage.py migrate --noinput

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  python manage.py seed_demo_data
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3

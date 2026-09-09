# Backend image — Django served by gunicorn behind the frontend container's
# nginx reverse proxy (see frontend/Dockerfile + frontend/nginx.conf). This
# does not replace the manual .venv + manage.py runserver workflow; it's a
# second, independent way to run the same code.
FROM python:3.12-slim

# Match psycopg2-binary's manylinux (glibc) wheel — alpine's musl would force
# a from-source build requiring extra build deps for no benefit here.
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy requirements first so dependency installs are cached independently of
# application code changes.
COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]

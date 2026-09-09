"""
Vercel Python entrypoint.

Vercel's native Python runtime discovers files under ``api/`` and serves the
module-level WSGI/ASGI callable it finds (``app`` / ``application``). This file
is a thin re-export of the project's existing Django WSGI application — no
Django application code is changed, and ``config/wsgi.py`` stays the entrypoint
for every other environment (runserver, gunicorn, Docker).

Routing is defined in the repo-root ``vercel.json``: ``/api/*`` and ``/admin/*``
are rewritten here, and Vercel passes the *original* request path through to the
function, so Django receives ``/api/...`` / ``/admin/...`` with the prefix
intact and ``config/urls.py`` matches unchanged.
"""

from config.wsgi import application

app = application

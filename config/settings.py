"""
Phase 1 settings. Deliberately minimal — no Stripe or channels config yet;
those arrive in later phases. Celery config was added in Stage D7 (see the
Celery block near the end). Split into a proper settings/ package
(base/dev/prod) once there's an actual need to diverge environments;
premature splitting here would just be structure for its own sake.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

from corsheaders.defaults import default_headers
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Must run before any os.environ.get() below, or those calls read the
# environment before .env has been loaded into it.
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-for-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Frontend and API are deployed as separate origins (e.g. two Render
# services), so the API must explicitly allow cross-origin requests from the
# frontend's origin. Environment-driven, comma-separated, no wildcard —
# an empty/unset value means no origin is allowed, not "allow everything".
# Auth is Bearer-token based (Authorization header), not cookies, so
# CORS_ALLOW_CREDENTIALS is deliberately left at its default (False).
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
# django-cors-headers' default allow-list doesn't include X-Tenant-ID (it's
# not a standard header) — without adding it here, the browser's preflight
# would block every tenant-scoped cross-origin request even though
# CORS_ALLOWED_ORIGINS permits the origin itself.
CORS_ALLOW_HEADERS = [*default_headers, "x-tenant-id"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    # Required because SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] is True —
    # without this app the blacklist models don't exist and refreshing
    # a token fails at runtime (manage.py check does not catch it).
    "rest_framework_simplejwt.token_blacklist",
    "apps.users",
    "apps.tenants",
    "apps.billing",
    "apps.platform",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Must come before CommonMiddleware (django-cors-headers requirement) so
    # CORS response headers get added, and preflight OPTIONS requests get
    # short-circuited, ahead of Django's own request handling.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Deliberately NO tenant-resolution middleware here — see
    # apps/tenants/authentication.py for why that has to live at the
    # DRF authentication layer instead of Django middleware.
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "billing_engine"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# email-verification-spec.md §4.6: console backend prints the email to the
# terminal/log rather than attempting real delivery — a deliberate scope
# boundary for local dev and this portfolio demo, not an oversight. A real
# transactional provider (SES/Postmark/SendGrid) would be a separate, later
# decision if this project ever needs actual delivered email. See CLAUDE.md.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "noreply@billing-engine.local"
)
# Where verification links point — the frontend's own origin, not this
# backend's. Docker Compose / production deployments override this.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# google-signin-spec.md §0/§7: the Web-application OAuth Client ID every
# Google ID token's audience is checked against. Empty-string default (not a
# placeholder that looks real) so a misconfigured deployment fails closed —
# verification's audience check simply never matches — rather than crashing.
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")

# stage-d1-spec.md §4.1: Razorpay credentials. Same empty-string-default pattern
# as GOOGLE_OAUTH_CLIENT_ID above — a misconfigured deployment fails closed
# (plan sync errors out; every webhook signature check fails) rather than
# crashing at import. Test-mode keys only in dev; never live keys (spec §11).
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

# Which PaymentGatewayAdapter apps.billing talks to (payment-gateway-adapter
# -spec.md §4.4). "razorpay" (real SDK) or "mock" (no network, no credentials —
# for local dev and the automated suite).
PAYMENT_GATEWAY = os.environ.get("PAYMENT_GATEWAY", "razorpay")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.tenants.authentication.TenantJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # Scoped narrowly to the two endpoints this feature introduces as real
    # abuse/spam vectors (email-verification-spec.md §4.7) — no
    # DEFAULT_THROTTLE_CLASSES, so nothing else on the platform is throttled.
    # Register/ResendVerificationView opt in explicitly via throttle_classes.
    "DEFAULT_THROTTLE_RATES": {
        "register": "10/hour",
        "resend-verification": "5/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# --- Celery / background jobs (docs/stage-d7-spec.md) ---
# The beat schedule lives in config/celery.py; this is just the broker + the
# test-eager switch. Manual workflow: a locally running Redis. Docker Compose
# overrides CELERY_BROKER_URL to the `redis` service.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_TIMEZONE = "UTC"
# Celery 6 will require this to be set explicitly; do it now to silence the
# startup warning.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Under `manage.py test`, tasks execute synchronously in the test process — the
# automated suite never needs a real broker running. Anything else (runserver,
# a real worker, Docker) uses the broker normally.
CELERY_TASK_ALWAYS_EAGER = "test" in sys.argv
CELERY_TASK_EAGER_PROPAGATES = True
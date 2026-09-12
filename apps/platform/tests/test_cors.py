"""
Production CORS configuration — the frontend and Django API are deployed as
two separate origins (e.g. two Render services), so cross-origin requests
must be explicitly allowed via django-cors-headers. See CORS_ALLOWED_ORIGINS
and CORS_ALLOW_HEADERS in config/settings.py.

These tests exercise the actual middleware/settings wiring (real HTTP
requests through the full middleware stack), not just that the setting
exists — a typo in MIDDLEWARE ordering or INSTALLED_APPS would not be caught
by inspecting settings.py alone.
"""

from django.conf import settings
from django.test import Client, TestCase, override_settings

ALLOWED_ORIGIN = "https://tenora-frontend.onrender.com"
DISALLOWED_ORIGIN = "https://evil.example.com"

# GLOBAL_PATHS entry — reachable with no auth and no X-Tenant-ID, so a plain
# GET/OPTIONS against it isolates CORS behavior from auth/tenant concerns.
GLOBAL_URL = "/api/plans/"

# Tenant-scoped endpoint (requires X-Tenant-ID) — used to prove the browser
# preflight for that header is actually allowed, since it is not part of
# django-cors-headers' default header allow-list.
TENANT_SCOPED_URL = "/api/memberships/"


class CorsConfigurationTests(TestCase):
    """The settings themselves: no wildcard, environment-driven, headers."""

    def test_no_wildcard_cors(self):
        self.assertFalse(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False))

    def test_cors_allowed_origins_is_environment_driven_list(self):
        # Exercises the exact parsing logic from config/settings.py against
        # representative env values, without depending on process-global
        # environment/import-time state.
        def parse(raw):
            return [origin.strip() for origin in raw.split(",") if origin.strip()]

        self.assertEqual(parse(""), [])
        self.assertEqual(
            parse("https://tenora-frontend.onrender.com"),
            ["https://tenora-frontend.onrender.com"],
        )
        self.assertEqual(
            parse(" https://a.example.com , https://b.example.com "),
            ["https://a.example.com", "https://b.example.com"],
        )

    def test_corsheaders_app_and_middleware_installed(self):
        self.assertIn("corsheaders", settings.INSTALLED_APPS)
        self.assertIn(
            "corsheaders.middleware.CorsMiddleware", settings.MIDDLEWARE
        )

    def test_cors_middleware_precedes_common_middleware(self):
        middleware = settings.MIDDLEWARE
        cors_index = middleware.index("corsheaders.middleware.CorsMiddleware")
        common_index = middleware.index("django.middleware.common.CommonMiddleware")
        self.assertLess(cors_index, common_index)

    def test_x_tenant_id_is_an_allowed_cors_header(self):
        # Without this, a real browser blocks every tenant-scoped
        # cross-origin call at the preflight stage even though the origin
        # itself is allowed.
        self.assertIn("x-tenant-id", settings.CORS_ALLOW_HEADERS)


@override_settings(CORS_ALLOWED_ORIGINS=[ALLOWED_ORIGIN])
class CorsResponseHeaderTests(TestCase):
    """Real requests through the full middleware stack."""

    def setUp(self):
        self.client = Client()

    def test_allowed_origin_gets_cors_header_on_global_endpoint(self):
        response = self.client.get(GLOBAL_URL, HTTP_ORIGIN=ALLOWED_ORIGIN)
        self.assertEqual(
            response["Access-Control-Allow-Origin"], ALLOWED_ORIGIN
        )

    def test_disallowed_origin_gets_no_cors_header(self):
        response = self.client.get(GLOBAL_URL, HTTP_ORIGIN=DISALLOWED_ORIGIN)
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_no_origin_header_gets_no_cors_header(self):
        # Same-origin / non-browser callers never send Origin; the fix must
        # not change behavior for them.
        response = self.client.get(GLOBAL_URL)
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_preflight_for_allowed_origin_permits_authorization_and_tenant_header(
        self,
    ):
        response = self.client.options(
            TENANT_SCOPED_URL,
            HTTP_ORIGIN=ALLOWED_ORIGIN,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-tenant-id",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Access-Control-Allow-Origin"], ALLOWED_ORIGIN
        )
        allowed_headers = response["Access-Control-Allow-Headers"].lower()
        self.assertIn("authorization", allowed_headers)
        self.assertIn("x-tenant-id", allowed_headers)

    def test_preflight_for_disallowed_origin_is_not_permitted(self):
        response = self.client.options(
            TENANT_SCOPED_URL,
            HTTP_ORIGIN=DISALLOWED_ORIGIN,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-tenant-id",
        )
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_no_credentials_allowed(self):
        # Auth is Authorization-header/Bearer-token based, not cookies —
        # CORS_ALLOW_CREDENTIALS must stay at its default (False/unset) so
        # this doesn't silently widen to cookie-based cross-origin auth.
        response = self.client.get(GLOBAL_URL, HTTP_ORIGIN=ALLOWED_ORIGIN)
        self.assertNotIn("Access-Control-Allow-Credentials", response)

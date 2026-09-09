"""
POST /api/auth/logout/ — server-side session termination.

Stage C3 §0.2. Closes the C2-reported gap where the refresh token stayed
valid after logout: token_blacklist has been installed since Stage A but
only ever exercised by rotation, never by an explicit logout.

The guarantee being added is not "the endpoint returns 200" — it is that
the blacklisted refresh token genuinely stops working at
/api/auth/refresh/ afterward. test_blacklisted_token_rejected_at_refresh
is the one that actually proves it.
"""

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.users.models import User

LOGOUT_URL = "/api/auth/logout/"
REFRESH_URL = "/api/auth/refresh/"
GOOD_PASSWORD = "correct-horse-staple-42"


class LogoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="out@example.com", password=GOOD_PASSWORD
        )

    def _auth(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}"
        )

    def test_valid_refresh_token_is_blacklisted(self):
        self._auth(self.user)
        refresh = RefreshToken.for_user(self.user)

        resp = self.client.post(LOGOUT_URL, {"refresh": str(refresh)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            BlacklistedToken.objects.filter(
                token__jti=refresh["jti"]
            ).exists()
        )

    def test_blacklisted_token_rejected_at_refresh(self):
        # The actual guarantee: after logout, the refresh token is dead.
        self._auth(self.user)
        refresh = RefreshToken.for_user(self.user)

        logout_resp = self.client.post(LOGOUT_URL, {"refresh": str(refresh)})
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

        # A fresh client with no credentials — /api/auth/refresh/ is a
        # global no-auth path, the refresh token is the only credential.
        self.client.credentials()
        refresh_resp = self.client.post(REFRESH_URL, {"refresh": str(refresh)})

        self.assertEqual(refresh_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_malformed_token_returns_400_not_500(self):
        self._auth(self.user)

        resp = self.client.post(LOGOUT_URL, {"refresh": "not-a-real-jwt"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_token_returns_400(self):
        self._auth(self.user)

        resp = self.client.post(LOGOUT_URL, {})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("refresh", resp.data)

    def test_access_token_passed_as_refresh_returns_400(self):
        # Wrong token type — SimpleJWT raises TokenError on construction.
        self._auth(self.user)
        access = AccessToken.for_user(self.user)

        resp = self.client.post(LOGOUT_URL, {"refresh": str(access)})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_blacklisted_token_returns_400(self):
        self._auth(self.user)
        refresh = RefreshToken.for_user(self.user)

        first = self.client.post(LOGOUT_URL, {"refresh": str(refresh)})
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self.client.post(LOGOUT_URL, {"refresh": str(refresh)})
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        refresh = RefreshToken.for_user(self.user)
        # No Authorization header set.

        resp = self.client.post(LOGOUT_URL, {"refresh": str(refresh)})

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_is_a_global_path_no_tenant_header(self):
        # A valid access token alone is enough — no X-Tenant-ID.
        self._auth(self.user)
        refresh = RefreshToken.for_user(self.user)

        resp = self.client.post(LOGOUT_URL, {"refresh": str(refresh)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

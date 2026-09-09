"""
POST /api/auth/google/ — google-signin-spec.md §4.2/§7/§8/§9.

`verify_oauth2_token` is mocked throughout (patched at its import site in
apps.users.services) — the suite must never attempt to hit real Google
servers (spec §11). What's actually being proven: the find-or-create/
auto-link/flip-verified logic downstream of a verified token, that the
audience check is genuinely passed (not just present in the source), and
that every failure mode collapses to one clean 400.
"""

from unittest import mock

import google.auth.exceptions as google_auth_exceptions
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User

GOOGLE_URL = "/api/auth/google/"
GOOD_PASSWORD = "correct-horse-staple-42"

VERIFY_PATH = "apps.users.services.id_token.verify_oauth2_token"


def google_payload(email="new-google-user@example.com", email_verified=True):
    return {
        "email": email,
        "email_verified": email_verified,
        "sub": "1234567890",
        "aud": settings.GOOGLE_OAUTH_CLIENT_ID,
    }


class GoogleSignInTests(APITestCase):
    def test_new_account_is_created_verified_with_unusable_password(self):
        with mock.patch(VERIFY_PATH, return_value=google_payload()):
            resp = self.client.post(GOOGLE_URL, {"credential": "fake-jwt"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

        user = User.objects.get(email="new-google-user@example.com")
        self.assertTrue(user.email_verified)
        self.assertFalse(user.has_usable_password())

    def test_existing_verified_account_auto_links_no_duplicate(self):
        existing = User.objects.create_user(
            email="already@example.com",
            password=GOOD_PASSWORD,
            email_verified=True,
        )

        with mock.patch(
            VERIFY_PATH, return_value=google_payload(email="already@example.com")
        ):
            resp = self.client.post(GOOGLE_URL, {"credential": "fake-jwt"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.filter(email="already@example.com").count(), 1)
        # Still the same account, and its usable password is untouched.
        existing.refresh_from_db()
        self.assertTrue(existing.has_usable_password())

    def test_existing_unverified_password_account_becomes_verified(self):
        User.objects.create_user(
            email="pending@example.com",
            password=GOOD_PASSWORD,
            email_verified=False,
        )

        with mock.patch(
            VERIFY_PATH, return_value=google_payload(email="pending@example.com")
        ):
            resp = self.client.post(GOOGLE_URL, {"credential": "fake-jwt"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="pending@example.com")
        self.assertTrue(user.email_verified)
        # The password flow still works for this account — Google sign-in
        # doesn't strip an existing usable password.
        self.assertTrue(user.check_password(GOOD_PASSWORD))

    def test_invalid_token_returns_400_generic(self):
        with mock.patch(VERIFY_PATH, side_effect=ValueError("bad signature")):
            resp = self.client.post(GOOGLE_URL, {"credential": "garbage"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", resp.data)
        self.assertEqual(User.objects.count(), 0)

    def test_network_failure_returns_400_not_500(self):
        with mock.patch(
            VERIFY_PATH,
            side_effect=google_auth_exceptions.TransportError("no route to Google"),
        ):
            resp = self.client.post(GOOGLE_URL, {"credential": "fake-jwt"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_google_unverified_email_claim_is_rejected(self):
        with mock.patch(
            VERIFY_PATH, return_value=google_payload(email_verified=False)
        ):
            resp = self.client.post(GOOGLE_URL, {"credential": "fake-jwt"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)

    def test_missing_credential_is_a_400_field_error(self):
        resp = self.client.post(GOOGLE_URL, {})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("credential", resp.data)

    def test_audience_is_actually_checked_not_omitted(self):
        with mock.patch(
            VERIFY_PATH, return_value=google_payload()
        ) as mocked_verify:
            self.client.post(GOOGLE_URL, {"credential": "fake-jwt"})

        mocked_verify.assert_called_once()
        _, kwargs = mocked_verify.call_args
        self.assertEqual(kwargs.get("audience"), settings.GOOGLE_OAUTH_CLIENT_ID)

    def test_google_signin_is_a_global_path_no_tenant_header_needed(self):
        with mock.patch(VERIFY_PATH, return_value=google_payload()):
            resp = self.client.post(GOOGLE_URL, {"credential": "fake-jwt"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

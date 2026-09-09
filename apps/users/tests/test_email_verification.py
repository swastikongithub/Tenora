"""
POST /api/auth/verify-email/ and POST /api/auth/resend-verification/ —
email-verification-spec.md §4.4/§4.7/§8/§9.

Mirrors test_logout.py's shape: the guarantee being tested isn't "the
endpoint returns a status code," it's the actual state change (a token
becomes unusable, an account becomes verified) proven by a follow-up request
or a direct model check.
"""

from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import EmailVerificationToken, User
from apps.users.services import EmailVerificationService, _hash

VERIFY_URL = "/api/auth/verify-email/"
RESEND_URL = "/api/auth/resend-verification/"
LOGIN_URL = "/api/auth/login/"
GOOD_PASSWORD = "correct-horse-staple-42"


class EmailVerificationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="pending@example.com", password=GOOD_PASSWORD
        )
        self.addCleanup(cache.clear)

    def test_valid_token_verifies_the_account(self):
        raw = EmailVerificationService.issue_token(self.user)

        resp = self.client.post(VERIFY_URL, {"token": raw})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_token_is_stored_hashed_never_raw(self):
        raw = EmailVerificationService.issue_token(self.user)

        token_row = EmailVerificationToken.objects.get(user=self.user)
        self.assertNotEqual(token_row.token_hash, raw)
        self.assertEqual(token_row.token_hash, _hash(raw))

    def test_unknown_token_returns_400_generic_message(self):
        resp = self.client.post(VERIFY_URL, {"token": "not-a-real-token"})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", resp.data)

    def test_expired_token_returns_400_same_message_as_unknown(self):
        raw = EmailVerificationService.issue_token(self.user)
        EmailVerificationToken.objects.filter(user=self.user).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        expired_resp = self.client.post(VERIFY_URL, {"token": raw})
        unknown_resp = self.client.post(VERIFY_URL, {"token": "garbage"})

        self.assertEqual(expired_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(expired_resp.data, unknown_resp.data)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_used_token_returns_400_same_message_as_unknown(self):
        # Mirrors test_logout.py's test_already_blacklisted_token_returns_400
        # shape exactly: use it once (succeeds), use it again (fails the
        # same generic way).
        raw = EmailVerificationService.issue_token(self.user)

        first = self.client.post(VERIFY_URL, {"token": raw})
        second = self.client.post(VERIFY_URL, {"token": raw})
        unknown_resp = self.client.post(VERIFY_URL, {"token": "garbage"})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second.data, unknown_resp.data)

    def test_missing_token_is_a_400_field_error(self):
        resp = self.client.post(VERIFY_URL, {})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", resp.data)

    def test_verify_email_is_a_global_path_no_tenant_header_needed(self):
        raw = EmailVerificationService.issue_token(self.user)

        resp = self.client.post(VERIFY_URL, {"token": raw})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class ResendVerificationTests(APITestCase):
    def setUp(self):
        self.addCleanup(cache.clear)

    def test_genuine_unverified_account_gets_a_new_token_and_email(self):
        user = User.objects.create_user(
            email="unverified@example.com", password=GOOD_PASSWORD
        )
        mail.outbox.clear()

        resp = self.client.post(RESEND_URL, {"email": "unverified@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("verify-email?token=", mail.outbox[0].body)
        self.assertTrue(
            EmailVerificationToken.objects.filter(
                user=user, used_at__isnull=True
            ).exists()
        )

    def test_response_identical_for_nonexistent_already_verified_and_genuine(self):
        User.objects.create_user(
            email="verified@example.com", password=GOOD_PASSWORD, email_verified=True
        )
        User.objects.create_user(
            email="unverified2@example.com", password=GOOD_PASSWORD
        )

        nonexistent_resp = self.client.post(
            RESEND_URL, {"email": "nobody@example.com"}
        )
        verified_resp = self.client.post(
            RESEND_URL, {"email": "verified@example.com"}
        )
        genuine_resp = self.client.post(
            RESEND_URL, {"email": "unverified2@example.com"}
        )

        self.assertEqual(nonexistent_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(verified_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(genuine_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(nonexistent_resp.data, verified_resp.data)
        self.assertEqual(verified_resp.data, genuine_resp.data)

    def test_already_verified_account_gets_no_new_token(self):
        User.objects.create_user(
            email="already@example.com", password=GOOD_PASSWORD, email_verified=True
        )

        self.client.post(RESEND_URL, {"email": "already@example.com"})

        self.assertFalse(EmailVerificationToken.objects.exists())

    def test_rapid_repeat_resend_invalidates_the_earlier_token(self):
        # §8: only the most recent unused token should be valid.
        user = User.objects.create_user(
            email="repeat@example.com", password=GOOD_PASSWORD
        )
        first_raw = EmailVerificationService.issue_token(user)

        self.client.post(RESEND_URL, {"email": "repeat@example.com"})

        # The first token is now unusable...
        first_attempt = self.client.post(VERIFY_URL, {"token": first_raw})
        self.assertEqual(first_attempt.status_code, status.HTTP_400_BAD_REQUEST)
        # ...but exactly one unused token exists for the newest email sent.
        self.assertEqual(
            EmailVerificationToken.objects.filter(
                user=user, used_at__isnull=True
            ).count(),
            1,
        )

    def test_missing_email_is_a_400_field_error(self):
        resp = self.client.post(RESEND_URL, {})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)


class ThrottlingTests(APITestCase):
    """
    email-verification-spec.md §4.7 — narrowly scoped to exactly these two
    endpoints. Fires past the configured rate and expects a real 429, not
    just trusting the class was attached.
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_register_is_throttled_after_the_configured_rate(self):
        for i in range(10):
            self.client.post(
                "/api/auth/register/",
                {"email": f"throttle{i}@example.com", "password": GOOD_PASSWORD},
            )

        resp = self.client.post(
            "/api/auth/register/",
            {"email": "throttle-over@example.com", "password": GOOD_PASSWORD},
        )

        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_resend_verification_is_throttled_after_the_configured_rate(self):
        for _ in range(5):
            self.client.post(RESEND_URL, {"email": "whoever@example.com"})

        resp = self.client.post(RESEND_URL, {"email": "whoever@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

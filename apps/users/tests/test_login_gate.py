"""
POST /api/auth/login/ — the email-verification gate on
EmailVerifiedTokenObtainPairSerializer (email-verification-spec.md §4.5/§7).

The actual guarantee: an unverified user's rejection is BYTE-IDENTICAL to a
verified user's wrong-password rejection — not just "both are 401." Every
test that touches the failure body asserts on the full `.data`, not merely
the status code.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User

LOGIN_URL = "/api/auth/login/"
GOOD_PASSWORD = "correct-horse-staple-42"
WRONG_PASSWORD = "definitely-not-it-99"


class LoginGateTests(APITestCase):
    def setUp(self):
        self.verified = User.objects.create_user(
            email="verified@example.com",
            password=GOOD_PASSWORD,
            email_verified=True,
        )
        self.unverified = User.objects.create_user(
            email="unverified@example.com",
            password=GOOD_PASSWORD,
            email_verified=False,
        )

    def test_verified_user_with_correct_password_gets_real_tokens(self):
        resp = self.client.post(
            LOGIN_URL, {"email": "verified@example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_unverified_user_with_correct_password_is_rejected(self):
        resp = self.client.post(
            LOGIN_URL, {"email": "unverified@example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)

    def test_unverified_correct_password_and_verified_wrong_password_are_byte_identical(self):
        unverified_resp = self.client.post(
            LOGIN_URL, {"email": "unverified@example.com", "password": GOOD_PASSWORD}
        )
        wrong_password_resp = self.client.post(
            LOGIN_URL, {"email": "verified@example.com", "password": WRONG_PASSWORD}
        )

        self.assertEqual(unverified_resp.status_code, wrong_password_resp.status_code)
        self.assertEqual(unverified_resp.status_code, status.HTTP_401_UNAUTHORIZED)
        # The actual guarantee: same body, not just same status code.
        self.assertEqual(dict(unverified_resp.data), dict(wrong_password_resp.data))

    def test_unverified_user_wrong_password_is_also_identical(self):
        # Every combination of {credentials right/wrong} x {verified/not}
        # that results in a rejection must collapse to the same body.
        unverified_wrong_resp = self.client.post(
            LOGIN_URL, {"email": "unverified@example.com", "password": WRONG_PASSWORD}
        )
        verified_wrong_resp = self.client.post(
            LOGIN_URL, {"email": "verified@example.com", "password": WRONG_PASSWORD}
        )

        self.assertEqual(dict(unverified_wrong_resp.data), dict(verified_wrong_resp.data))

    def test_nonexistent_email_is_also_identical(self):
        nonexistent_resp = self.client.post(
            LOGIN_URL, {"email": "nobody@example.com", "password": GOOD_PASSWORD}
        )
        unverified_resp = self.client.post(
            LOGIN_URL, {"email": "unverified@example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(dict(nonexistent_resp.data), dict(unverified_resp.data))

    def test_does_not_persist_an_outstanding_token_for_a_rejected_unverified_login(self):
        # Plan decision 2: the subclass must not mint (and thereby persist,
        # via BlacklistMixin.for_user) a RefreshToken before the
        # email_verified check runs.
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

        before = OutstandingToken.objects.count()

        self.client.post(
            LOGIN_URL, {"email": "unverified@example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(OutstandingToken.objects.count(), before)

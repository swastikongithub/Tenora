"""
POST /api/auth/register/ — the one unauthenticated endpoint.

Covers spec docs/stage-b1-spec.md §10 "Registration" plus the
email-normalization behaviour of UserManager (lowercase the whole
address on write, and match that on login).
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"

# Long, non-numeric, uncommon — clears every configured validator.
GOOD_PASSWORD = "correct-horse-staple-42"


class RegisterTests(APITestCase):
    def test_valid_registration_creates_hashed_user(self):
        resp = self.client.post(
            REGISTER_URL, {"email": "new@example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(resp.data), {"id", "email"})
        self.assertEqual(resp.data["email"], "new@example.com")

        user = User.objects.get(email="new@example.com")
        self.assertNotEqual(user.password, GOOD_PASSWORD)  # stored as a hash
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertTrue(user.check_password(GOOD_PASSWORD))

    def test_duplicate_email_returns_400(self):
        User.objects.create_user(email="taken@example.com", password=GOOD_PASSWORD)

        resp = self.client.post(
            REGISTER_URL, {"email": "taken@example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)
        self.assertEqual(User.objects.filter(email="taken@example.com").count(), 1)

    def test_duplicate_email_differing_only_in_case_returns_400(self):
        User.objects.create_user(email="mixed@example.com", password=GOOD_PASSWORD)

        resp = self.client.post(
            REGISTER_URL, {"email": "Mixed@Example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)
        self.assertEqual(User.objects.count(), 1)

    def test_email_is_stored_lowercased(self):
        resp = self.client.post(
            REGISTER_URL,
            {"email": "CasedUser@Example.com", "password": GOOD_PASSWORD},
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["email"], "caseduser@example.com")
        self.assertTrue(User.objects.filter(email="caseduser@example.com").exists())

    def test_register_mixed_case_then_login_with_same_string(self):
        # Lowercasing on write would break login if the login lookup stayed
        # case-exact — this asserts UserManager.get_by_natural_key normalizes.
        # Registering alone no longer makes an account login-able
        # (email-verification-spec.md §1) — verify it directly first, the
        # same as a real click-through, so this test still isolates the
        # case-normalization behavior it actually exists to prove.
        self.client.post(
            REGISTER_URL,
            {"email": "Person@Example.com", "password": GOOD_PASSWORD},
        )
        user = User.objects.get(email="person@example.com")
        user.email_verified = True
        user.save(update_fields=["email_verified"])

        resp = self.client.post(
            LOGIN_URL, {"email": "Person@Example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_weak_password_returns_400_with_validator_message(self):
        resp = self.client.post(
            REGISTER_URL, {"email": "weak@example.com", "password": "123"}
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", resp.data)
        self.assertFalse(User.objects.filter(email="weak@example.com").exists())

    def test_no_authentication_required(self):
        # No credentials set on the client at all.
        resp = self.client.post(
            REGISTER_URL, {"email": "anon@example.com", "password": GOOD_PASSWORD}
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_password_is_never_echoed_back(self):
        resp = self.client.post(
            REGISTER_URL, {"email": "quiet@example.com", "password": GOOD_PASSWORD}
        )

        self.assertNotIn("password", resp.data)

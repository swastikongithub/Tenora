"""
bootstrap_superuser management command — the deployment-bootstrap mechanism
for hosts with no shell/SSH access (e.g. Render's Free plan), run by
docker-entrypoint.sh after every migrate. Mirrors the testing approach of
apps/tenants/tests/test_seed_demo_data.py (call_command, real DB rows).

Two branches, each with its own guarantees:
  - create (no user with that email exists): fully active, verified
    superuser, password from the env, never logged.
  - promote (a user with that email already exists — the real deployment
    bug this file now guards against: an existing account, e.g. one that
    signed up normally, used to be left untouched forever with no way to
    grant it platform access short of shell/DB access): is_staff/
    is_superuser/is_active/email_verified all forced True, password and
    every other field left completely alone.
"""

import io
import os
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.users.models import User

EMAIL = "admin@example.com"
PASSWORD = "correct-horse-staple-99"


class BootstrapSuperuserTests(TestCase):
    def test_does_nothing_when_both_env_vars_absent(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DJANGO_SUPERUSER_EMAIL", None)
            os.environ.pop("DJANGO_SUPERUSER_PASSWORD", None)
            call_command("bootstrap_superuser")

        self.assertEqual(User.objects.count(), 0)

    def test_does_nothing_when_only_email_present(self):
        with mock.patch.dict(
            os.environ, {"DJANGO_SUPERUSER_EMAIL": EMAIL}, clear=False
        ):
            os.environ.pop("DJANGO_SUPERUSER_PASSWORD", None)
            call_command("bootstrap_superuser")

        self.assertEqual(User.objects.count(), 0)

    def test_does_nothing_when_only_password_present(self):
        with mock.patch.dict(
            os.environ, {"DJANGO_SUPERUSER_PASSWORD": PASSWORD}, clear=False
        ):
            os.environ.pop("DJANGO_SUPERUSER_EMAIL", None)
            call_command("bootstrap_superuser")

        self.assertEqual(User.objects.count(), 0)

    def test_missing_env_vars_is_a_no_op_even_when_the_email_already_exists(self):
        # An existing user must not be silently promoted just because the
        # command ran — the env vars are the only authorization signal.
        User.objects.create_user(email=EMAIL, password="original-password")

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DJANGO_SUPERUSER_EMAIL", None)
            os.environ.pop("DJANGO_SUPERUSER_PASSWORD", None)
            call_command("bootstrap_superuser")

        user = User.objects.get(email=EMAIL)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.email_verified)

    def test_creates_superuser_with_both_vars_present(self):
        with mock.patch.dict(
            os.environ,
            {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD},
            clear=False,
        ):
            call_command("bootstrap_superuser")

        user = User.objects.get(email=EMAIL)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.email_verified)
        self.assertTrue(user.check_password(PASSWORD))

    def test_email_is_normalized_the_same_way_as_regular_signup(self):
        with mock.patch.dict(
            os.environ,
            {
                "DJANGO_SUPERUSER_EMAIL": "Admin@Example.com",
                "DJANGO_SUPERUSER_PASSWORD": PASSWORD,
            },
            clear=False,
        ):
            call_command("bootstrap_superuser")

        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)

    def test_running_twice_does_not_duplicate_or_error(self):
        env = {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD}
        with mock.patch.dict(os.environ, env, clear=False):
            call_command("bootstrap_superuser")
            call_command("bootstrap_superuser")

        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        user = User.objects.get(email=EMAIL)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.email_verified)

    def test_promoting_an_already_fully_promoted_user_is_a_true_no_op(self):
        # Second run after the account is already fully promoted: same
        # password hash, same primary key — proving it's genuinely a no-op,
        # not a delete-and-recreate that happens to land on the same values.
        env = {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD}
        with mock.patch.dict(os.environ, env, clear=False):
            call_command("bootstrap_superuser")
            user_after_create = User.objects.get(email=EMAIL)
            call_command("bootstrap_superuser")
            user_after_second_run = User.objects.get(email=EMAIL)

        self.assertEqual(user_after_create.pk, user_after_second_run.pk)
        self.assertEqual(user_after_create.password, user_after_second_run.password)

    def test_does_not_overwrite_an_existing_users_password(self):
        User.objects.create_user(email=EMAIL, password="original-password")
        original_hash = User.objects.get(email=EMAIL).password

        with mock.patch.dict(
            os.environ,
            {
                "DJANGO_SUPERUSER_EMAIL": EMAIL,
                "DJANGO_SUPERUSER_PASSWORD": "a-different-password",
            },
            clear=False,
        ):
            call_command("bootstrap_superuser")

        user = User.objects.get(email=EMAIL)
        self.assertTrue(user.check_password("original-password"))
        self.assertFalse(user.check_password("a-different-password"))
        self.assertEqual(user.password, original_hash)

    def test_promotes_an_existing_normal_user_to_root(self):
        # The real deployment bug this fixes: an existing account (e.g. one
        # that signed up normally through the app) must become the intended
        # first operator on the next deploy, not be silently left as an
        # ordinary tenant user forever.
        existing = User.objects.create_user(email=EMAIL, password="original-password")
        self.assertFalse(existing.is_staff)
        self.assertFalse(existing.is_superuser)

        with mock.patch.dict(
            os.environ,
            {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD},
            clear=False,
        ):
            call_command("bootstrap_superuser")

        user = User.objects.get(email=EMAIL)
        self.assertEqual(user.pk, existing.pk)  # the same row, promoted — not recreated
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        # Password untouched even though promotion also happened.
        self.assertTrue(user.check_password("original-password"))

    def test_promotion_sets_email_verified_true_when_previously_false(self):
        # A password-login-eligible operator needs email_verified=True — the
        # production login gate (EmailVerifiedTokenObtainPairSerializer)
        # refuses an unverified account regardless of is_staff/is_superuser.
        User.objects.create_user(email=EMAIL, password="original-password")
        self.assertFalse(User.objects.get(email=EMAIL).email_verified)

        with mock.patch.dict(
            os.environ,
            {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD},
            clear=False,
        ):
            call_command("bootstrap_superuser")

        self.assertTrue(User.objects.get(email=EMAIL).email_verified)

    def test_promotion_never_reads_or_uses_the_provided_password(self):
        # DJANGO_SUPERUSER_PASSWORD must be present (it's the authorization
        # signal, alongside the email), but on the promote branch its VALUE
        # is never consulted — proven here by using a password that isn't
        # even the existing user's, and confirming the existing one still
        # authenticates while the provided one does not.
        User.objects.create_user(email=EMAIL, password="original-password")

        with mock.patch.dict(
            os.environ,
            {
                "DJANGO_SUPERUSER_EMAIL": EMAIL,
                "DJANGO_SUPERUSER_PASSWORD": "totally-unrelated-value",
            },
            clear=False,
        ):
            call_command("bootstrap_superuser")

        user = User.objects.get(email=EMAIL)
        self.assertTrue(user.is_staff)  # promotion still happened
        self.assertTrue(user.check_password("original-password"))
        self.assertFalse(user.check_password("totally-unrelated-value"))

    def test_password_is_never_written_to_stdout_on_create(self):
        out = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD},
            clear=False,
        ):
            call_command("bootstrap_superuser", stdout=out)

        self.assertNotIn(PASSWORD, out.getvalue())

    def test_password_is_never_written_to_stdout_on_promote(self):
        User.objects.create_user(email=EMAIL, password="original-password")
        out = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD},
            clear=False,
        ):
            call_command("bootstrap_superuser", stdout=out)

        self.assertNotIn(PASSWORD, out.getvalue())
        self.assertNotIn("original-password", out.getvalue())

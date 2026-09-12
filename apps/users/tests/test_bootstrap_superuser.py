"""
bootstrap_superuser management command — the deployment-bootstrap mechanism
for hosts with no shell/SSH access (e.g. Render's Free plan), run by
docker-entrypoint.sh after every migrate. Mirrors the testing approach of
apps/tenants/tests/test_seed_demo_data.py (call_command, real DB rows), plus
the two guarantees that matter for a superuser bootstrap specifically:
never overwrite an existing password, and never leak the password to logs.
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

    def test_does_not_overwrite_an_existing_users_password(self):
        User.objects.create_user(email=EMAIL, password="original-password")

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

    def test_does_not_elevate_an_existing_non_staff_user(self):
        # Spec: create only if the email doesn't already exist — an existing
        # row is left completely alone, not "topped up" to superuser.
        User.objects.create_user(email=EMAIL, password="original-password")

        with mock.patch.dict(
            os.environ,
            {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD},
            clear=False,
        ):
            call_command("bootstrap_superuser")

        user = User.objects.get(email=EMAIL)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_password_is_never_written_to_stdout(self):
        out = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"DJANGO_SUPERUSER_EMAIL": EMAIL, "DJANGO_SUPERUSER_PASSWORD": PASSWORD},
            clear=False,
        ):
            call_command("bootstrap_superuser", stdout=out)

        self.assertNotIn(PASSWORD, out.getvalue())

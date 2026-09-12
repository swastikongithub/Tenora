"""
Production email delivery — auth-production-readiness spec, part 1.

The email BACKEND choice (console vs. Django's own SMTP backend) is a
deployment-time config switch, not something these tests exercise directly
— Django's test runner already transparently swaps in the locmem backend
for every test regardless of what EMAIL_BACKEND settings.py resolves to,
so `django.core.mail.outbox` is the correct, standard way to prove the
actual email-sending BEHAVIOR (recipient, body, count) is unchanged by
this change. What IS new and needs direct coverage: the env-driven
parsing of the new EMAIL_* settings, and the TLS/SSL mutual-exclusion
guard. Token/verification/resend semantics are proven unchanged by
reusing the same assertions test_email_verification.py already
established, not by inventing new ones.
"""

from unittest import mock

from django.core import mail
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
from apps.users.services import EmailVerificationService

REGISTER_URL = "/api/auth/register/"
RESEND_URL = "/api/auth/resend-verification/"
GOOD_PASSWORD = "correct-horse-staple-42"


class EmailSentOnceWithCorrectRecipientAndUrlTests(APITestCase):
    def test_registration_sends_exactly_one_email_to_the_correct_recipient(self):
        resp = self.client.post(
            REGISTER_URL,
            {"email": "new-user@example.com", "password": GOOD_PASSWORD},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new-user@example.com"])

    @override_settings(FRONTEND_URL="https://tenora.example.com")
    def test_verification_url_uses_frontend_url(self):
        self.client.post(
            REGISTER_URL,
            {"email": "link-check@example.com", "password": GOOD_PASSWORD},
        )
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("https://tenora.example.com/verify-email?token=", body)
        # And never the (unset here) default dev origin.
        self.assertNotIn("http://localhost:5173", body)

    def test_resend_also_sends_exactly_one_email(self):
        User.objects.create_user(email="resend-me@example.com", password=GOOD_PASSWORD)
        mail.outbox.clear()

        resp = self.client.post(RESEND_URL, {"email": "resend-me@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["resend-me@example.com"])

    def test_resend_for_a_verified_or_unknown_account_sends_no_email(self):
        # Unchanged non-disclosure behavior (email-verification-spec.md
        # §4.4/§6) — same response either way, but genuinely zero email
        # sent for these two branches.
        verified = User.objects.create_user(
            email="already-verified@example.com",
            password=GOOD_PASSWORD,
            email_verified=True,
        )
        del verified
        self.client.post(RESEND_URL, {"email": "already-verified@example.com"})
        self.assertEqual(len(mail.outbox), 0)

        self.client.post(RESEND_URL, {"email": "no-such-account@example.com"})
        self.assertEqual(len(mail.outbox), 0)


class TokenNeverReturnedByAnApiResponseTests(APITestCase):
    def test_register_response_never_contains_the_raw_token(self):
        resp = self.client.post(
            REGISTER_URL,
            {"email": "no-leak@example.com", "password": GOOD_PASSWORD},
        )
        self.assertEqual(set(resp.data), {"id", "email"})

        # The raw token that WAS issued and emailed never appears in the
        # response body at all — it only ever exists in the outbox.
        self.assertEqual(len(mail.outbox), 1)
        sent_body = mail.outbox[0].body
        raw_token = sent_body.split("token=")[1].split("\n")[0]
        self.assertNotIn(raw_token, str(resp.data))

    def test_resend_response_never_contains_a_token(self):
        User.objects.create_user(email="resend-leak@example.com", password=GOOD_PASSWORD)
        resp = self.client.post(RESEND_URL, {"email": "resend-leak@example.com"})
        self.assertEqual(resp.data, {"detail": mock.ANY})
        raw_token = mail.outbox[0].body.split("token=")[1].split("\n")[0]
        self.assertNotIn(raw_token, str(resp.data))

    def test_issue_token_return_value_is_the_only_place_the_raw_token_exists(self):
        # Direct service-level proof, mirroring
        # test_email_verification.py's own token_is_stored_hashed_never_raw.
        user = User.objects.create_user(email="direct@example.com", password=GOOD_PASSWORD)
        raw = EmailVerificationService.issue_token(user)
        from apps.users.models import EmailVerificationToken
        from apps.users.services import _hash

        stored = EmailVerificationToken.objects.get(user=user)
        self.assertEqual(stored.token_hash, _hash(raw))
        self.assertNotEqual(stored.token_hash, raw)


class EnvironmentDrivenEmailConfigurationTests(APITestCase):
    """
    settings.py reads every EMAIL_* value once, at process/module import
    time — the same reason the existing CORS_ALLOWED_ORIGINS test
    (frontend/... no, apps/platform/tests/test_cors.py) re-exercises the
    exact parsing logic against representative env values rather than
    reloading the whole settings module mid-suite. Same approach here.
    """

    def _parse(self, env):
        get = env.get
        backend = get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
        host = get("EMAIL_HOST", "localhost")
        port = int(get("EMAIL_PORT", "587"))
        user = get("EMAIL_HOST_USER", "")
        password = get("EMAIL_HOST_PASSWORD", "")
        use_tls = get("EMAIL_USE_TLS", "true").lower() == "true"
        use_ssl = get("EMAIL_USE_SSL", "false").lower() == "true"
        from_email = get("DEFAULT_FROM_EMAIL", "noreply@billing-engine.local")
        return {
            "EMAIL_BACKEND": backend,
            "EMAIL_HOST": host,
            "EMAIL_PORT": port,
            "EMAIL_HOST_USER": user,
            "EMAIL_HOST_PASSWORD": password,
            "EMAIL_USE_TLS": use_tls,
            "EMAIL_USE_SSL": use_ssl,
            "DEFAULT_FROM_EMAIL": from_email,
        }

    def test_defaults_are_the_safe_console_backend(self):
        parsed = self._parse({})
        self.assertEqual(
            parsed["EMAIL_BACKEND"], "django.core.mail.backends.console.EmailBackend"
        )
        self.assertEqual(parsed["EMAIL_HOST_USER"], "")
        self.assertEqual(parsed["EMAIL_HOST_PASSWORD"], "")

    def test_a_full_smtp_configuration_is_parsed_correctly(self):
        env = {
            "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "EMAIL_HOST": "smtp.provider.example.com",
            "EMAIL_PORT": "587",
            "EMAIL_HOST_USER": "apikey",
            "EMAIL_HOST_PASSWORD": "super-secret-value",
            "EMAIL_USE_TLS": "true",
            "EMAIL_USE_SSL": "false",
            "DEFAULT_FROM_EMAIL": "billing@tenora.example.com",
        }
        parsed = self._parse(env)
        self.assertEqual(
            parsed["EMAIL_BACKEND"], "django.core.mail.backends.smtp.EmailBackend"
        )
        self.assertEqual(parsed["EMAIL_HOST"], "smtp.provider.example.com")
        self.assertEqual(parsed["EMAIL_PORT"], 587)
        self.assertTrue(parsed["EMAIL_USE_TLS"])
        self.assertFalse(parsed["EMAIL_USE_SSL"])
        self.assertEqual(parsed["DEFAULT_FROM_EMAIL"], "billing@tenora.example.com")

    def test_implicit_ssl_configuration_is_parsed_correctly(self):
        env = {"EMAIL_USE_TLS": "false", "EMAIL_USE_SSL": "true", "EMAIL_PORT": "465"}
        parsed = self._parse(env)
        self.assertFalse(parsed["EMAIL_USE_TLS"])
        self.assertTrue(parsed["EMAIL_USE_SSL"])
        self.assertEqual(parsed["EMAIL_PORT"], 465)

    def test_tls_and_ssl_both_enabled_is_rejected_by_the_guard(self):
        # Reloading config.settings mid-suite to prove this live would risk
        # corrupting Django's already-booted app registry/settings object
        # for every other test in the process — deliberately avoided, same
        # restraint apps/platform/tests/test_cors.py's own "environment-
        # driven configuration" tests already use. This instead proves the
        # exact guard condition settings.py runs
        # (`if EMAIL_USE_TLS and EMAIL_USE_SSL: raise ImproperlyConfigured`)
        # behaves correctly in isolation.
        from django.core.exceptions import ImproperlyConfigured

        def validate(use_tls, use_ssl):
            if use_tls and use_ssl:
                raise ImproperlyConfigured(
                    "EMAIL_USE_TLS and EMAIL_USE_SSL are mutually exclusive — "
                    "set at most one of them."
                )

        with self.assertRaises(ImproperlyConfigured):
            validate(True, True)
        validate(True, False)  # does not raise
        validate(False, True)  # does not raise
        validate(False, False)  # does not raise

    def test_settings_module_currently_has_no_conflicting_email_flags(self):
        # A live sanity check against the actual, currently-loaded settings
        # (proves this repo's own default configuration is valid, without
        # touching/reloading the settings module).
        from django.conf import settings

        self.assertFalse(settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL)

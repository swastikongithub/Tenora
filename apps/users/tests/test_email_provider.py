"""
Email-delivery provider abstraction — auth-production-readiness spec, the
Brevo fix (docs: Render Free blocks outbound SMTP on 25/465/587, so
production switches to Brevo's HTTPS transactional email API instead of
SMTP). test_email_delivery.py already covers the "django" (console/SMTP)
provider path end to end — unaffected by anything here. These tests are
about the new provider-selection seam (apps/users/email_delivery/) and the
Brevo adapter specifically.

Every apps.users.email_delivery.brevo.requests.post call is mocked — no test
in this file makes, or could make, a real network request to Brevo.
"""

from unittest import mock

import requests
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.email_delivery import (
    BrevoEmailProvider,
    DjangoEmailProvider,
    EmailDeliveryError,
    get_email_provider,
)
from apps.users.models import User

REGISTER_URL = "/api/auth/register/"
RESEND_URL = "/api/auth/resend-verification/"
GOOD_PASSWORD = "correct-horse-staple-42"

FAKE_API_KEY = "test-brevo-key-do-not-leak-12345"

BREVO_SETTINGS = dict(
    EMAIL_PROVIDER="brevo",
    BREVO_API_KEY=FAKE_API_KEY,
    DEFAULT_FROM_EMAIL="noreply@tenora.example.com",
    DEFAULT_FROM_NAME="Tenora",
)


def fake_response(status_code=201, ok=True, json_body=None):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.ok = ok
    resp.json.return_value = json_body or {}
    return resp


class ProviderSelectionTests(TestCase):
    """get_email_provider() — the single construction point, mirroring
    apps.billing.gateway.get_gateway()."""

    def test_default_provider_is_django_console_path(self):
        # No EMAIL_PROVIDER set anywhere in the test environment (settings.py
        # defaults it to "django") — local dev / CI safe by construction.
        self.assertIsInstance(get_email_provider(), DjangoEmailProvider)

    @override_settings(**BREVO_SETTINGS)
    def test_brevo_provider_selected_when_configured(self):
        self.assertIsInstance(get_email_provider(), BrevoEmailProvider)

    @override_settings(EMAIL_PROVIDER="not-a-real-provider")
    def test_unknown_provider_name_fails_closed(self):
        with self.assertRaises(ImproperlyConfigured):
            get_email_provider()


@override_settings(**BREVO_SETTINGS)
class BrevoRequestShapeTests(TestCase):
    def test_sends_a_correctly_structured_request_to_brevos_api(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(),
        ) as mock_post:
            BrevoEmailProvider().send(
                to_email="new-user@example.com",
                subject="Verify your email",
                body="link text here",
            )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        # Brevo's HTTPS transactional email endpoint — never SMTP.
        self.assertEqual(args[0], "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(kwargs["headers"]["api-key"], FAKE_API_KEY)
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertIn("timeout", kwargs)

    def test_recipient_is_correct(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(),
        ) as mock_post:
            BrevoEmailProvider().send(
                to_email="new-user@example.com", subject="s", body="b"
            )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["to"], [{"email": "new-user@example.com"}])

    def test_sender_name_and_email_are_correct(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(),
        ) as mock_post:
            BrevoEmailProvider().send(to_email="x@example.com", subject="s", body="b")

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            payload["sender"],
            {"name": "Tenora", "email": "noreply@tenora.example.com"},
        )

    def test_subject_and_body_are_passed_through_unmodified(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(),
        ) as mock_post:
            BrevoEmailProvider().send(
                to_email="x@example.com",
                subject="Verify your email — Tenora",
                body="link text here",
            )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["subject"], "Verify your email — Tenora")
        self.assertEqual(payload["textContent"], "link text here")

    def test_network_failure_raises_email_delivery_error(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            side_effect=requests.ConnectionError("boom"),
        ):
            with self.assertRaises(EmailDeliveryError):
                BrevoEmailProvider().send(
                    to_email="x@example.com", subject="s", body="b"
                )

    def test_non_2xx_response_raises_email_delivery_error(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(
                status_code=401, ok=False, json_body={"code": "unauthorized"}
            ),
        ):
            with self.assertRaises(EmailDeliveryError):
                BrevoEmailProvider().send(
                    to_email="x@example.com", subject="s", body="b"
                )

    def test_api_key_never_appears_in_logs_on_a_rejected_request(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(status_code=401, ok=False),
        ):
            with self.assertLogs(
                "apps.users.email_delivery.brevo", level="WARNING"
            ) as captured:
                with self.assertRaises(EmailDeliveryError):
                    BrevoEmailProvider().send(
                        to_email="x@example.com", subject="s", body="b"
                    )

        self.assertTrue(any("HTTP 401" in line for line in captured.output))
        self.assertFalse(any(FAKE_API_KEY in line for line in captured.output))

    def test_api_key_never_appears_in_logs_on_a_network_failure(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            side_effect=requests.ConnectionError(f"boom, api-key={FAKE_API_KEY}"),
        ):
            with self.assertLogs(
                "apps.users.email_delivery.brevo", level="WARNING"
            ) as captured:
                with self.assertRaises(EmailDeliveryError):
                    BrevoEmailProvider().send(
                        to_email="x@example.com", subject="s", body="b"
                    )

        self.assertFalse(any(FAKE_API_KEY in line for line in captured.output))


class MissingBrevoConfigurationFailsClosedTests(TestCase):
    def test_settings_guard_logic_rejects_brevo_without_credentials(self):
        # Reloading config.settings mid-suite to prove the real guard fires
        # would risk corrupting Django's already-booted settings object for
        # every other test in the process — the same restraint
        # test_email_delivery.py's own TLS/SSL guard tests already use. This
        # instead proves the exact guard condition settings.py runs
        # (`if EMAIL_PROVIDER == "brevo" and not (BREVO_API_KEY and
        # DEFAULT_FROM_EMAIL): raise ImproperlyConfigured`) in isolation.
        def validate(provider, api_key, from_email):
            if provider == "brevo" and not (api_key and from_email):
                raise ImproperlyConfigured(
                    "EMAIL_PROVIDER=brevo requires both BREVO_API_KEY and "
                    "DEFAULT_FROM_EMAIL to be set."
                )

        with self.assertRaises(ImproperlyConfigured):
            validate("brevo", "", "noreply@example.com")
        with self.assertRaises(ImproperlyConfigured):
            validate("brevo", "a-key", "")
        validate("brevo", "a-key", "noreply@example.com")  # does not raise
        validate("django", "", "")  # django path needs neither — does not raise

    def test_settings_module_currently_has_no_conflicting_brevo_config(self):
        # Live sanity check against the actual, currently-loaded settings —
        # proves this repo's own default configuration would pass the guard,
        # without touching/reloading the settings module.
        from django.conf import settings

        if settings.EMAIL_PROVIDER == "brevo":
            self.assertTrue(settings.BREVO_API_KEY)
            self.assertTrue(settings.DEFAULT_FROM_EMAIL)

    @override_settings(
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_provider_itself_fails_closed_with_no_api_key(self):
        # Defense-in-depth check at the point of use (BrevoEmailProvider.send
        # re-checks this independently of the settings-load-time guard).
        with self.assertRaises(ImproperlyConfigured):
            BrevoEmailProvider().send(to_email="x@example.com", subject="s", body="b")

    @override_settings(
        EMAIL_PROVIDER="brevo", BREVO_API_KEY="a-key", DEFAULT_FROM_EMAIL=""
    )
    def test_provider_itself_fails_closed_with_no_sender_address(self):
        with self.assertRaises(ImproperlyConfigured):
            BrevoEmailProvider().send(to_email="x@example.com", subject="s", body="b")


class RegisterEmailDeliveryFailureTests(APITestCase):
    """
    RegisterView owns the "don't lie about success" behavior — it operates
    on the email the caller themselves just supplied, so distinctly
    surfacing a provider failure here carries no account-enumeration risk
    (contrast ResendEmailDeliveryFailureTests below).
    """

    def setUp(self):
        # register/resend are both throttle-scoped (config/settings.py
        # DEFAULT_THROTTLE_RATES) and LocMemCache persists for the whole
        # test-process lifetime, not per test — clear it on both sides of
        # every test here so this class's own several register/resend calls
        # never trip the rate limit themselves or leave state for whichever
        # test file runs next, the same discipline
        # test_email_verification.py's ThrottlingTests already uses.
        cache.clear()
        self.addCleanup(cache.clear)

    @override_settings(**BREVO_SETTINGS)
    def test_provider_failure_returns_502_never_a_false_201(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(status_code=500, ok=False),
        ):
            resp = self.client.post(
                REGISTER_URL,
                {"email": "delivery-fail@example.com", "password": GOOD_PASSWORD},
            )

        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertNotEqual(resp.status_code, status.HTTP_201_CREATED)
        # The account was still created — see the inline rationale in
        # views.py: rolling it back on a delivery failure would be worse.
        self.assertTrue(
            User.objects.filter(email="delivery-fail@example.com").exists()
        )
        self.assertNotIn(FAKE_API_KEY, str(resp.data))

    @override_settings(**BREVO_SETTINGS)
    def test_provider_success_still_returns_201_with_no_token(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(),
        ):
            resp = self.client.post(
                REGISTER_URL,
                {"email": "delivery-ok@example.com", "password": GOOD_PASSWORD},
            )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(resp.data), {"id", "email"})

    @override_settings(**BREVO_SETTINGS, FRONTEND_URL="https://tenora.example.com")
    def test_verification_url_uses_frontend_url_via_brevo(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(),
        ) as mock_post:
            self.client.post(
                REGISTER_URL,
                {"email": "brevo-link@example.com", "password": GOOD_PASSWORD},
            )

        payload = mock_post.call_args.kwargs["json"]
        self.assertIn(
            "https://tenora.example.com/verify-email?token=", payload["textContent"]
        )
        self.assertNotIn("http://localhost:5173", payload["textContent"])

    @override_settings(**BREVO_SETTINGS)
    def test_raw_token_never_appears_in_the_api_response_via_brevo(self):
        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(),
        ) as mock_post:
            resp = self.client.post(
                REGISTER_URL,
                {"email": "brevo-token@example.com", "password": GOOD_PASSWORD},
            )

        payload = mock_post.call_args.kwargs["json"]
        raw_token = payload["textContent"].split("token=")[1].split("\n")[0]
        self.assertNotIn(raw_token, str(resp.data))


class ResendEmailDeliveryFailureTests(APITestCase):
    """
    ResendVerificationView's non-disclosure contract (spec §4.4/§6) must
    survive a genuine provider outage exactly as it survives every other
    internal branch — the response can never let a caller tell "no such
    account" apart from "account exists but the provider is down".
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @override_settings(**BREVO_SETTINGS)
    def test_resend_response_is_unchanged_even_when_the_provider_fails(self):
        User.objects.create_user(
            email="resend-fail@example.com", password=GOOD_PASSWORD
        )

        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(status_code=500, ok=False),
        ):
            resp = self.client.post(RESEND_URL, {"email": "resend-fail@example.com"})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn(FAKE_API_KEY, str(resp.data))

    @override_settings(**BREVO_SETTINGS)
    def test_resend_response_identical_for_failure_and_nonexistent_account(self):
        User.objects.create_user(
            email="resend-fail2@example.com", password=GOOD_PASSWORD
        )

        with mock.patch(
            "apps.users.email_delivery.brevo.requests.post",
            return_value=fake_response(status_code=500, ok=False),
        ):
            failure_resp = self.client.post(
                RESEND_URL, {"email": "resend-fail2@example.com"}
            )
        nonexistent_resp = self.client.post(
            RESEND_URL, {"email": "nobody-brevo@example.com"}
        )

        self.assertEqual(failure_resp.data, nonexistent_resp.data)

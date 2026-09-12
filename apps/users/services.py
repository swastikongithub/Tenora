import hashlib
import logging
import secrets
from datetime import timedelta

import google.auth.exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.users.email_delivery import EmailDeliveryError, get_email_provider
from apps.users.models import EmailVerificationToken, User

logger = logging.getLogger(__name__)


class EmailAlreadyRegistered(Exception):
    """Raised when a registration collides with an existing user.email."""


class UserService:
    """
    All user mutations go through here, not through serializers or views
    — same seam as SubscriptionService in apps/billing/services.py.
    """

    @staticmethod
    def register(email, password):
        # The UNIQUE(email) constraint is the real guarantee; the
        # serializer's pre-check is only a UX nicety. Catch IntegrityError
        # OUTSIDE the atomic block that raised it — once the error escapes,
        # the surrounding transaction is broken and any further query on it
        # raises TransactionManagementError.
        try:
            with transaction.atomic():
                return User.objects.create_user(email=email, password=password)
        except IntegrityError:
            raise EmailAlreadyRegistered()


# email-verification-spec.md §4.2: left open in the prior evaluation, picked
# concretely here rather than left unset. A module constant, not a Django
# setting — same style as apps/billing/services.py's PERIOD_LENGTH.
TOKEN_TTL = timedelta(hours=24)


class InvalidOrExpiredToken(Exception):
    """
    Raised for a not-found, expired, OR already-used token — deliberately
    one exception for all three. The view turns this into a single generic
    400; the caller must never be able to distinguish "expired" from
    "already used" from "never existed" (spec §4.4/§7 — no benefit to the
    caller, and distinguishing them is a minor information leak about
    token/account state).
    """


def _hash(raw_token):
    # Deterministic (unsalted) SHA-256, not password-style hashing — the
    # token is a 256-bit secrets.token_urlsafe() value with no accompanying
    # identifier in the verify-email request, so the lookup has to find the
    # row directly by its hash. Salting defends against *guessable*
    # low-entropy secrets (passwords); it buys nothing for an already-
    # unguessable random token, and would make direct lookup impossible.
    # Same pattern real systems use for opaque high-entropy API tokens.
    return hashlib.sha256(raw_token.encode()).hexdigest()


class EmailVerificationService:
    """
    All EmailVerificationToken mutations go through here — same seam as
    UserService / SubscriptionService. Tokens are DB-backed and single-use
    (spec §1), mirroring the refresh-token-blacklist pattern already proven
    in this codebase (Stage C3 §0.2).
    """

    @staticmethod
    def issue_token(user):
        """
        Create a new token for `user` and return the RAW value — the only
        moment it ever exists outside a hash. Never persisted, never
        returned by any API response after this.
        """
        raw_token = secrets.token_urlsafe(32)
        EmailVerificationToken.objects.create(
            user=user,
            token_hash=_hash(raw_token),
            expires_at=timezone.now() + TOKEN_TTL,
        )
        return raw_token

    @staticmethod
    def send_verification_email(user, raw_token):
        # Plain text — HTML templating would be effort spent on nothing for
        # a link-plus-two-sentences email. This method owns the CONTENT
        # (subject, body, and building the verification URL from
        # FRONTEND_URL) exactly as before; it now hands that content to
        # get_email_provider() rather than calling Django's send_mail
        # directly, so it never knows or cares whether the active provider
        # is the local console backend or Brevo's HTTPS API (auth-
        # production-readiness spec — the Brevo fix). Raises
        # EmailDeliveryError, unhandled, on a genuine delivery failure — see
        # apps/users/views.py RegisterView and .resend() below for how each
        # caller handles that.
        link = f"{settings.FRONTEND_URL}/verify-email?token={raw_token}"
        get_email_provider().send(
            to_email=user.email,
            subject="Verify your email — Multi-Tenant SaaS Billing Engine",
            body=(
                "Welcome! Confirm your email address to activate your "
                f"account:\n\n{link}\n\n"
                "This link expires in 24 hours. If you didn't create this "
                "account, you can ignore this message."
            ),
        )

    @staticmethod
    def verify(raw_token):
        """
        Mark the token used and the user verified, atomically. Raises
        InvalidOrExpiredToken for a not-found, expired, or already-used
        token — one generic failure, never distinguishable (spec §4.4).
        """
        try:
            candidate = EmailVerificationToken.objects.get(
                token_hash=_hash(raw_token)
            )
        except EmailVerificationToken.DoesNotExist:
            raise InvalidOrExpiredToken()

        if candidate.expires_at <= timezone.now():
            raise InvalidOrExpiredToken()

        with transaction.atomic():
            # Conditional UPDATE, not a pre-check-then-write: 0 rows affected
            # means another request already consumed this token between our
            # GET above and here (or it was already used earlier) — the DB
            # decides atomically, no SELECT FOR UPDATE needed. Same
            # "the constraint/atomic write is the real guarantee" principle
            # as membership creation and webhook idempotency elsewhere in
            # this project.
            updated = EmailVerificationToken.objects.filter(
                pk=candidate.pk, used_at__isnull=True
            ).update(used_at=timezone.now())
            if not updated:
                raise InvalidOrExpiredToken()

            User.objects.filter(pk=candidate.user_id).update(email_verified=True)

    @staticmethod
    def resend(email):
        """
        Look up a genuine, unverified account for `email` and issue+send a
        fresh token — or silently do nothing. The caller (the view) always
        returns the identical response regardless of which happened; this
        method never signals which branch ran, so there is nothing for a
        caller to accidentally leak (spec §4.4/§6: never reveal account
        existence or verification status).
        """
        normalized = User.objects.normalize_email(email)
        try:
            user = User.objects.get(email=normalized)
        except User.DoesNotExist:
            return

        if user.email_verified:
            return

        # Invalidate every prior unused token first (spec §8: rapid repeat
        # requests must leave only the newest token valid, not accumulate
        # additional valid ones) by marking them used — the same "used"
        # state a real verification leaves behind, so verify() rejects them
        # identically either way.
        EmailVerificationToken.objects.filter(
            user=user, used_at__isnull=True
        ).update(used_at=timezone.now())

        raw_token = EmailVerificationService.issue_token(user)
        try:
            EmailVerificationService.send_verification_email(user, raw_token)
        except EmailDeliveryError:
            # spec §4.4/§6 non-disclosure: resend's response to the caller
            # is identical no matter what happens internally — including a
            # genuine provider outage — so nothing here can let a caller
            # distinguish "no such account" from "account exists but the
            # email provider is down" from the response alone. The token
            # issued above is still valid regardless; a real user can just
            # try resend again once the provider recovers. Logged, not
            # swallowed silently, so an operator can see it.
            logger.warning(
                "resend-verification: email delivery failed for user %s", user.id
            )


class GoogleSignInFailed(Exception):
    """
    Raised for every Google sign-in failure mode — bad signature, wrong or
    missing audience, expired token, a network error reaching Google's
    public keys, or a token whose own email_verified claim is False. One
    exception for all of them, so the view produces one generic 400 without
    distinguishing reasons — the same non-disclosure discipline as every
    other auth error in this project (login, verify-email).
    """


class GoogleAuthService:
    """
    google-signin-spec.md §1/§4.2. Verifies a Google-issued ID token directly
    via the `google-auth` library rather than a heavy OAuth framework (see
    the spec's own rationale against django-allauth/dj-rest-auth) and
    resolves it to a local User — created or auto-linked by email, never a
    duplicate. Mutations stay here, not in the view — same seam as
    UserService / EmailVerificationService.
    """

    @staticmethod
    def authenticate_credential(raw_credential):
        try:
            idinfo = id_token.verify_oauth2_token(
                raw_credential,
                google_requests.Request(),
                audience=settings.GOOGLE_OAUTH_CLIENT_ID,
            )
        except (ValueError, google_auth_exceptions.GoogleAuthError):
            # ValueError: bad signature, wrong/missing audience, expired —
            # verify_oauth2_token's documented failure mode.
            # GoogleAuthError (base class, covers TransportError): a network
            # failure fetching Google's public certs (spec §8) — surfaced as
            # the same clean failure, never a 500.
            raise GoogleSignInFailed()

        # The whole feature's premise is "verified by Google" (spec §1) — if
        # Google's own token says this email isn't verified (occasionally
        # true for some federated/workspace accounts), that premise doesn't
        # hold for this token. Not spelled out in the spec's literal text;
        # added because the design's justification depends on it.
        if idinfo.get("email_verified") is not True:
            raise GoogleSignInFailed()

        email = User.objects.normalize_email(idinfo["email"])
        user, created = User.objects.get_or_create(
            email=email, defaults={"email_verified": True}
        )

        if created:
            # The standard Django idiom for "this account cannot
            # authenticate via the password flow" — prevents any confusion
            # about a blank or guessable password on a Google-only account.
            user.set_unusable_password()
            user.save(update_fields=["password"])
        elif not user.email_verified:
            # spec §8: a password account that registered but never clicked
            # its verification link becomes verified by this alternate proof
            # of ownership.
            user.email_verified = True
            user.save(update_fields=["email_verified"])

        return user

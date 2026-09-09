"""
The JWT-issuance seam — kept out of views.py (a generic-APIView file) since
this is a serializer-driven TokenObtainPairView subclass, a different shape.

email-verification-spec.md §4.5: gates password login behind
User.email_verified without adding a distinguishable error. Wired in place
of the stock TokenObtainPairView in config/urls.py.
"""

from django.contrib.auth.models import update_last_login
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenObtainSerializer,
)
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView


class EmailVerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Deliberately does NOT call TokenObtainPairSerializer.validate() first.
    That method authenticates *and* mints a RefreshToken — and because
    rest_framework_simplejwt.token_blacklist is installed,
    RefreshToken.for_user() immediately persists a real OutstandingToken row
    (BlacklistMixin.for_user) the moment it's called. Minting before the
    email_verified check would leave a live, DB-persisted (if never
    transmitted) refresh token behind for every rejected unverified-login
    attempt — harmless since it's never sent to the client, but a pointless
    write on a login that's supposed to fail closed.

    So: call the grandparent TokenObtainSerializer.validate() instead — the
    part that actually runs authenticate() and the active-user rule, with no
    minting — check email_verified, and only then replicate
    TokenObtainPairSerializer.validate()'s own minting lines. The exception
    class, the reused error-message string, and the error code
    ("no_active_account") are identical to the stock wrong-password failure
    either way, so this changes nothing observable — see
    test_login_gate.py's byte-for-byte body comparison.
    """

    def validate(self, attrs):
        TokenObtainSerializer.validate(self, attrs)

        if not self.user.email_verified:
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        refresh = self.get_token(self.user)
        data = {"refresh": str(refresh), "access": str(refresh.access_token)}

        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)

        return data


class EmailVerifiedTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailVerifiedTokenObtainPairSerializer

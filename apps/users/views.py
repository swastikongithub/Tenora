from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.serializers import (
    GoogleSignInSerializer,
    LogoutSerializer,
    MeSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    UserSerializer,
    VerifyEmailSerializer,
)
from apps.users.email_delivery import EmailDeliveryError
from apps.users.services import (
    EmailAlreadyRegistered,
    EmailVerificationService,
    GoogleAuthService,
    GoogleSignInFailed,
    InvalidOrExpiredToken,
    UserService,
)

# One generic message for every verify-email failure (not-found, expired, or
# already-used) — spec §4.4/§7: the response must never let a caller tell
# these apart.
INVALID_TOKEN_MESSAGE = "This verification link is invalid or has expired."

# Identical regardless of whether the email exists, is already verified, or a
# token was actually sent — spec §4.4/§6 non-disclosure.
RESEND_MESSAGE = (
    "If an account with that email exists and isn’t verified yet, "
    "we’ve sent a new verification link."
)


class RegisterView(APIView):
    """
    POST /api/auth/register/ — { "email", "password" } -> 201 { id, email }.

    The one unauthenticated endpoint that creates state. Registering leaves
    the account unverified — see EmailVerificationService — until a real
    emailed link is used at POST /api/auth/verify-email/.
    """

    # Explicit override — the project default is IsAuthenticated
    # (config/settings.py REST_FRAMEWORK).
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = UserService.register(
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
            )
        except EmailAlreadyRegistered:
            # Same 400 field error the serializer pre-check produces, so
            # the constraint path and the pre-check path are
            # indistinguishable to the client.
            return Response(
                {"email": ["A user with this email already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The account exists the moment registration succeeds (spec §4.8) —
        # a deliberate, pre-existing invariant (see RegisterPage.tsx's own
        # docstring on the frontend) that this change does not reverse.
        # issue_token()'s DB write is not rolled back if the email below
        # fails to send: doing so would mean a registration whose only
        # problem was an email provider hiccup silently un-registers the
        # account, which is worse than leaving a valid, still-usable
        # verification token in place for the client to retry via
        # /api/auth/resend-verification/.
        raw_token = EmailVerificationService.issue_token(user)
        try:
            EmailVerificationService.send_verification_email(user, raw_token)
        except EmailDeliveryError:
            # Never claim success (a 201) when delivery genuinely failed —
            # unlike ResendVerificationView, register operates on the email
            # address the caller themselves just supplied, so there is no
            # account-enumeration concern in surfacing this distinctly.
            return Response(
                {
                    "detail": (
                        "Your account was created, but we couldn't send the "
                        "verification email. Use the resend option to try "
                        "again."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    """
    POST /api/auth/verify-email/ — { "token" } -> 200, or 400 with one
    generic message for invalid/expired/already-used (spec §4.4).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            EmailVerificationService.verify(serializer.validated_data["token"])
        except InvalidOrExpiredToken:
            return Response(
                {"detail": INVALID_TOKEN_MESSAGE}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(status=status.HTTP_200_OK)


class ResendVerificationView(APIView):
    """
    POST /api/auth/resend-verification/ — { "email" } -> always 200, always
    the same body, regardless of whether the account exists, is already
    verified, or a token was genuinely sent (spec §4.4/§6).
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "resend-verification"

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        EmailVerificationService.resend(serializer.validated_data["email"])

        return Response({"detail": RESEND_MESSAGE}, status=status.HTTP_200_OK)


class GoogleSignInView(APIView):
    """
    POST /api/auth/google/ — { "credential" } -> 200 { access, refresh },
    same shape as /api/auth/login/'s success response.

    A plain APIView issuing tokens through its own logic (google-signin-spec.md
    §3) — deliberately NOT routed through EmailVerifiedTokenObtainPairSerializer
    (apps/users/auth.py). That serializer's email_verified gate exists for
    password logins, where verification is a separate, deferred step; a
    Google-authenticated user is resolved as verified by construction in
    GoogleAuthService itself (creation sets it immediately; an existing
    unverified account is flipped verified as part of resolving this sign-in) —
    so re-running that gate here would be checking a property this code path
    just established, not applying an independent boundary.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = GoogleSignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = GoogleAuthService.authenticate_credential(
                serializer.validated_data["credential"]
            )
        except GoogleSignInFailed:
            return Response(
                {"detail": "Google sign-in failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)}
        )


class MeView(APIView):
    """
    GET /api/users/me/ — { id, email, is_staff } for the requesting user.

    Global path (see GLOBAL_PATHS): identity, not tenant-scoped data, so
    it must not require X-Tenant-ID. The tenant list the frontend also
    needs on load lives at /api/tenants/me/, deliberately kept separate.
    `is_staff` (added via MeSerializer, not the shared UserSerializer) is
    what lets the frontend decide whether to show the platform-admin
    dashboard — docs/platform-admin-spec.md §4.4.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class LogoutView(APIView):
    """
    POST /api/auth/logout/ — { "refresh" } -> 200, blacklisting that token.

    Global path: a logout has no tenant context. The token_blacklist app
    (installed since Stage A for rotation) gets its first real logout use
    here — after this call the refresh token genuinely fails at
    /api/auth/refresh/, closing the "refresh token stays valid after
    logout" gap from Stage C2.

    Bad input is always a 400, never a 500: the client clears its local
    state regardless of this response, but the endpoint must degrade
    gracefully on a malformed, expired, or already-blacklisted token.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            _, created = RefreshToken(
                serializer.validated_data["refresh"]
            ).blacklist()
        except TokenError:
            # Malformed / expired / wrong-type token. RefreshToken() itself
            # verifies signature and expiry on construction.
            return Response(
                {"detail": "Token is invalid or expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not created:
            # blacklist() is get_or_create under the hood — a False here
            # means this token was already blacklisted.
            return Response(
                {"detail": "Token is already blacklisted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(status=status.HTTP_200_OK)

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    """Output only. Never exposes the password hash."""

    class Meta:
        model = User
        fields = ["id", "email"]


class MeSerializer(UserSerializer):
    """
    GET /api/users/me/ only. Adds `is_staff` so the frontend can decide
    whether to show the platform-admin dashboard at all
    (docs/platform-admin-spec.md §4.4), and — since Operator Control Plane
    Phase 4 — `is_superuser`, for the same reason one tier down: the Root-only
    operator controls must not render for a Staff-tier viewer
    (docs/operator-control-plane-spec.md §D).

    Both are UX signals only. The real boundaries are IsPlatformStaff and
    IsPlatformRoot server-side, which answer the same question from the
    database on every request regardless of what the client believes.

    Deliberately a MeView-scoped subclass, NOT fields added to
    UserSerializer: RegisterView shares that base serializer and its
    response shape (and the test pinning it) stays exactly {id, email} —
    a fresh signup has no business being told its own platform flags.
    Neither flag is a new concept: both already gate Django admin.
    """

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["is_staff", "is_superuser"]


class RegisterSerializer(serializers.Serializer):
    """
    Validates input shape only — creation goes through UserService.
    A plain Serializer (not ModelSerializer) so unknown body keys are
    silently dropped rather than bound.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        # Normalize the input the same way UserManager stores it, then
        # compare exactly — one rule on both sides (see UserManager
        # .normalize_email). The DB constraint stays the real guarantee
        # (see UserService); this pre-check is only a UX nicety.
        normalized = User.objects.normalize_email(value)
        if User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class LogoutSerializer(serializers.Serializer):
    """
    Input shape only for POST /api/auth/logout/. A missing `refresh` key
    is a 400 field error here; a well-formed-but-invalid token is handled
    in the view (it needs SimpleJWT to tell it apart from a good one).
    """

    refresh = serializers.CharField()


class VerifyEmailSerializer(serializers.Serializer):
    """Input shape only for POST /api/auth/verify-email/."""

    token = serializers.CharField()


class ResendVerificationSerializer(serializers.Serializer):
    """
    Input shape only for POST /api/auth/resend-verification/. A plain
    EmailField (not validated against existing users here) — whether the
    address exists or is already verified is EmailVerificationService's
    concern, not this serializer's; the view returns the same response
    either way (spec §4.4/§6 non-disclosure).
    """

    email = serializers.EmailField()


class GoogleSignInSerializer(serializers.Serializer):
    """Input shape only for POST /api/auth/google/."""

    credential = serializers.CharField()

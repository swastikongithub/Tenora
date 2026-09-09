from rest_framework import serializers

from apps.tenants.models import Membership, Tenant


class TenantSerializer(serializers.ModelSerializer):
    """Output only."""

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "created_at", "is_active"]


class TenantCreateSerializer(serializers.Serializer):
    """
    Input shape only — creation goes through TenantService. Plain
    Serializer, so a body carrying tenant_id/role/etc. cannot bind.
    """

    name = serializers.CharField(max_length=255)
    slug = serializers.SlugField()


class MembershipSerializer(serializers.ModelSerializer):
    """Output only. Flattens the joined user's email for convenience."""

    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "email", "role", "created_at"]


class MembershipCreateSerializer(serializers.Serializer):
    """
    Input shape only. `email` is the sole field — there is deliberately
    NO `role` field, so `{"role": "OWNER"}` in the body binds to nothing.
    """

    email = serializers.EmailField()

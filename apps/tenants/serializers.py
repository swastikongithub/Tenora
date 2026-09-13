from rest_framework import serializers

from apps.tenants.models import Invitation, Membership, Tenant


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
        fields = ["id", "email", "role", "status", "created_at"]


class MembershipCreateSerializer(serializers.Serializer):
    """
    Input shape only. `email` is the sole field — there is deliberately
    NO `role` field, so `{"role": "OWNER"}` in the body binds to nothing.
    """

    email = serializers.EmailField()


class InvitationCreateSerializer(serializers.Serializer):
    """Input shape only. No role, no tenant: an invitation is always for a
    resident seat in the X-Tenant-ID workspace."""

    email = serializers.EmailField()
    unit_id = serializers.UUIDField(required=False, allow_null=True)
    message = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class InvitationRespondSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["accept", "decline"])


class InvitationSerializer(serializers.ModelSerializer):
    """Output only. Shown to the owner who sent it and to the invited user —
    both of whom may legitimately see every field here."""

    tenant_id = serializers.UUIDField(read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    invited_by_email = serializers.EmailField(source="invited_by.email", default=None, read_only=True)
    unit_id = serializers.UUIDField(read_only=True, allow_null=True)
    unit_identifier = serializers.CharField(source="unit.identifier", default=None, read_only=True)
    property_name = serializers.CharField(source="unit.property.name", default=None, read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "tenant_id",
            "tenant_name",
            "email",
            "role",
            "status",
            "unit_id",
            "unit_identifier",
            "property_name",
            "message",
            "invited_by_email",
            "created_at",
            "expires_at",
            "responded_at",
        ]

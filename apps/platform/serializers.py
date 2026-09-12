from rest_framework import serializers

from apps.billing.models import Plan, ReconciliationDiscrepancy, Subscription, WebhookEvent
from apps.tenants.models import Tenant
from apps.users.models import User


class PlatformTenantSerializer(serializers.ModelSerializer):
    """
    Output only. One row per tenant for the platform-admin tenant list —
    deliberately NOT scoped to any tenant (docs/platform-admin-spec.md §4.3).

    `member_count` is read straight off an annotation the view attaches
    (`Count("memberships")`), never a Python-side loop over related rows.

    `subscription` is a small {plan_name, status} summary, or null for a
    tenant with none — using the same `except Subscription.DoesNotExist`
    idiom CurrentSubscriptionView already relies on, not a hasattr shortcut
    that would swallow the real exception class.
    """

    member_count = serializers.IntegerField(read_only=True)
    subscription = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "created_at", "member_count", "subscription"]

    def get_subscription(self, tenant):
        try:
            sub = tenant.subscription
        except Subscription.DoesNotExist:
            return None
        return {"plan_name": sub.plan.name, "status": sub.status}


class PlatformPlanSerializer(serializers.ModelSerializer):
    """
    Output only. Unlike the tenant-facing PlanSerializer (apps.billing.serializers),
    this is deliberately a SEPARATE serializer, not a shared/extended one — it
    exposes exactly the fields the tenant-facing one omits on purpose
    (`is_active`, `external_plan_id`), for an audience (platform staff) that
    needs to see inactive/unsynced plans too.

    `subscriber_count` is a real annotation the view attaches
    (`Count("subscriptions")`), matching PlatformTenantSerializer's
    `member_count` convention above.
    """

    subscriber_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "code",
            "price_cents",
            "currency",
            "interval",
            "is_active",
            "external_plan_id",
            "subscriber_count",
        ]


class PlatformWebhookEventSerializer(serializers.ModelSerializer):
    """
    Output only. SANITIZED — docs/operator-control-plane-spec.md §B: exactly
    Tenora's own normalized fields, never `raw_payload`. A gateway's raw event
    payload can embed customer contact and payment-instrument metadata; Phase 1
    exposes only this fixed, normalized field set on both the list and detail
    read, with no exception.

    `tenant` is resolved by the view (apps.platform.services
    .resolve_tenants_for_external_subscription_ids) and handed in via
    `context["tenant_map"]` — a batch lookup, not a per-row query here.
    """

    tenant = serializers.SerializerMethodField()

    class Meta:
        model = WebhookEvent
        fields = [
            "id",
            "external_event_id",
            "event_type",
            "external_subscription_id",
            "tenant",
            "period_start",
            "period_end",
            "event_created_at",
            "received_at",
            "processed",
        ]

    def get_tenant(self, obj):
        return self.context.get("tenant_map", {}).get(obj.external_subscription_id)


class PlatformReconciliationDiscrepancySerializer(serializers.ModelSerializer):
    """Output only. `tenant` is a small {id, name, slug} summary, read off the
    view's `select_related("tenant")` — no extra query per row."""

    tenant = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationDiscrepancy
        fields = [
            "id",
            "tenant",
            "subscription_id",
            "external_subscription_id",
            "category",
            "local_status",
            "provider_status",
            "detail",
            "detected_at",
        ]

    def get_tenant(self, obj):
        return {
            "id": str(obj.tenant_id),
            "name": obj.tenant.name,
            "slug": obj.tenant.slug,
        }


class PlatformUserSerializer(serializers.ModelSerializer):
    """
    Output only. Never the password hash. Deliberately a separate serializer
    from apps.users.serializers.UserSerializer/MeSerializer — this audience
    (platform staff, about ANY user) needs the platform-relevant flags those
    serializers don't expose (is_superuser, is_active, email_verified,
    date_joined); RegisterView/MeView's response shapes are untouched.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "is_staff",
            "is_superuser",
            "is_active",
            "email_verified",
            "date_joined",
        ]


class PlatformUserDetailSerializer(PlatformUserSerializer):
    """
    GET /api/platform/users/detail/?id= only. Adds `memberships` — which
    tenants this user belongs to and with what role — built by the view the
    same way MyTenantsView already flattens {**TenantSerializer(tenant).data,
    "role": ...} for "tenants I belong to" (apps.tenants.views), reused here
    for "tenants THIS user belongs to". Not apps.tenants.serializers
    .MembershipSerializer — that serializer answers the opposite direction
    ("members of one fixed tenant, with each row's own email"), not this one.
    """

    memberships = serializers.SerializerMethodField()

    class Meta(PlatformUserSerializer.Meta):
        fields = PlatformUserSerializer.Meta.fields + ["memberships"]

    def get_memberships(self, obj):
        # Precomputed by the view (one query) and handed in via context —
        # same batch-then-serialize shape as PlatformWebhookEventSerializer's
        # tenant_map above, not a per-instance query.
        return self.context.get("memberships", [])

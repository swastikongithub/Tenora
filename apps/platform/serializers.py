from rest_framework import serializers

from apps.billing.models import Subscription
from apps.tenants.models import Tenant


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

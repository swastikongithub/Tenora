"""
Platform-admin read-time helpers — docs/operator-control-plane-spec.md §B.

Phase 1 is read-only: nothing here mutates anything. This module exists (rather
than inlining the lookup into each view) because the webhook-event tenant
resolution below is shared by two call sites (the webhook-events list and the
tenant-detail "recent events" panel).
"""

from apps.billing.models import Subscription, SubscriptionCheckout


def resolve_tenants_for_external_subscription_ids(external_subscription_ids):
    """
    Batch-resolve {external_subscription_id: {id, name, slug}} for a set of gateway
    subscription ids — Subscription checked first, then SubscriptionCheckout,
    the exact same match order apps.billing.services.WebhookProcessingService's
    own handlers already use to find "which tenant does this event belong to".

    Exactly two queries total, regardless of how many ids are passed in — a
    deliberate batch, not a per-row lookup in a list serializer (the same
    real-annotation-not-a-Python-loop instinct apps/platform/views.py already
    applies to PlatformTenantListView's member_count).
    """
    ids = [i for i in dict.fromkeys(external_subscription_ids) if i]
    if not ids:
        return {}

    result = {}
    for sub in Subscription.objects.filter(
        external_subscription_id__in=ids
    ).select_related("tenant"):
        result[sub.external_subscription_id] = {
            "id": str(sub.tenant_id),
            "name": sub.tenant.name,
            "slug": sub.tenant.slug,
        }

    remaining = [i for i in ids if i not in result]
    if remaining:
        for checkout in SubscriptionCheckout.objects.filter(
            external_subscription_id__in=remaining
        ).select_related("tenant"):
            result[checkout.external_subscription_id] = {
                "id": str(checkout.tenant_id),
                "name": checkout.tenant.name,
                "slug": checkout.tenant.slug,
            }

    return result

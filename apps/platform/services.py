"""
Platform-admin services — docs/operator-control-plane-spec.md §B.

Phase 1 additions here are read-time helpers only. Phase 2 adds AuditService
— the two explicit write paths every operator mutation records through.
"""

import logging

from apps.billing.models import Subscription, SubscriptionCheckout
from apps.platform.models import AuditEvent

logger = logging.getLogger(__name__)


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


class AuditService:
    """
    docs/operator-control-plane-spec.md §B "Audit semantics: critical vs.
    observational" — two explicit write paths, so the choice is visible at
    every call site (never a boolean flag threaded through a shared method).

    Both methods take the same keyword-only shape:
        actor, action, target_type, target_id, summary, metadata=None
    `metadata` is small, useful before/after values only — never a
    password, a secret, or a raw gateway webhook payload. That discipline is
    enforced by convention and tests at each call site, not by this service.
    """

    @staticmethod
    def record_critical(*, actor, action, target_type, target_id, summary, metadata=None):
        """
        For a financial or control-state mutation. MUST be called inside the
        same `transaction.atomic()` block as the mutation it describes — see
        apps/platform/views.py's subscription PATCH for the pattern. No
        exception is caught here: a DB failure propagates out of this call
        and rolls back the whole enclosing transaction, including the
        mutation that was about to be considered successful. This is the
        deliberate trade the spec makes — a critical mutation must never
        silently succeed with no audit record.
        """
        AuditEvent.objects.create(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            summary=summary,
            metadata=metadata or {},
            is_critical=True,
        )

    @staticmethod
    def record_observational(*, actor, action, target_type, target_id, summary, metadata=None):
        """
        For a non-critical, observational action (a fallback sweep trigger;
        a future raw-payload view). Best-effort — logged and swallowed on
        failure, the same "never raises" contract
        apps.billing.services.ProrationService.record_for_plan_change
        already uses. The action's own real effects (e.g. WebhookEvent rows
        marked processed) are already durably recorded elsewhere regardless
        of whether this row lands, so a failure here must never block or
        undo the caller.
        """
        try:
            AuditEvent.objects.create(
                actor=actor,
                action=action,
                target_type=target_type,
                target_id=str(target_id),
                summary=summary,
                metadata=metadata or {},
                is_critical=False,
            )
        except Exception:  # noqa: BLE001 — contract is "never raises", see docstring
            logger.exception(
                "audit: observational record failed — action=%s target=%s:%s",
                action,
                target_type,
                target_id,
            )

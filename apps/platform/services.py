"""
Platform-admin services — docs/operator-control-plane-spec.md §B.

Phase 1 additions here are read-time helpers only. Phase 2 adds AuditService
— the two explicit write paths every operator mutation records through.
Phase 3 adds PlanManagementService, the one genuinely new domain capability
in this design (spec §B reuse table).
"""

import logging

from django.conf import settings
from django.db import transaction

from apps.billing.models import Plan, Subscription, SubscriptionCheckout
from apps.billing.services import PlanSyncService
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


class PlanLocked(Exception):
    """
    An edit tried to change a field that is frozen because the Plan is already
    externally provisioned — docs/operator-control-plane-spec.md §B "Plan
    management — `external_plan_id` as a platform-level lock marker".

    Carries the offending field names so the view can return them as DRF field
    errors rather than one opaque detail string.
    """

    def __init__(self, fields):
        self.fields = sorted(fields)
        joined = ", ".join(self.fields)
        super().__init__(
            "These fields are locked once the plan is synced to the payment "
            f"gateway: {joined}."
        )


class PlanManagementService:
    """
    Phase 3 — docs/operator-control-plane-spec.md §B: "plan creation... the one
    genuinely new domain service in this design", plus the thin edit/archive
    and the audit wrapper around the REUSED, unmodified
    `PlanSyncService.sync_plan`.

    Lives in `apps.platform`, not `apps.billing`, for a layering reason: every
    method here writes an `AuditEvent`, and `apps.billing` must not import the
    platform audit model — billing is the domain the control plane observes,
    not a dependent of it. `apps.platform` already depends on `apps.billing`
    (views, serializers, the resolver above); the reverse edge does not exist
    and this service does not create one.

    Per the spec's "where the atomic wrapping lives": a new platform-only
    service owns its own `transaction.atomic()` and its own critical audit
    write internally — one service call is one atomic unit. (The subscription
    override is the other shape: a reused service wrapped by the view.)

    `actor` is always passed explicitly — never read from thread-local or
    global state, the same discipline `TenantScopedManager.for_tenant(tenant)`
    applies to tenant.
    """

    #: The only fields an operator may change once `external_plan_id` is set.
    #: Everything else on a locked Plan — `price_cents`, `currency`,
    #: `interval`, `code` — is frozen: a price change is a NEW Plan with the
    #: old one archived, never an in-place mutation of a row that
    #: subscriptions, checkouts and proration records already reference.
    #: Platform policy, enforced regardless of what any adapter's provider
    #: would technically permit (spec §B).
    MUTABLE_WHEN_LOCKED = frozenset({"name", "is_active"})

    @staticmethod
    @transaction.atomic
    def create_plan(*, actor, name, code, price_cents, currency, interval):
        """
        Create a Plan and its critical audit row in one transaction. The plan
        is created UNSYNCED (`external_plan_id` is None) — provisioning it at
        the gateway is a separate, explicit operator action (`sync_plan`), so
        creating a plan never has an external side effect.
        """
        plan = Plan.objects.create(
            name=name,
            code=code,
            price_cents=price_cents,
            currency=currency,
            interval=interval,
        )
        AuditService.record_critical(
            actor=actor,
            action="plan.created",
            target_type="Plan",
            target_id=plan.id,
            summary=f"Created plan {plan.code} ({plan.name})",
            metadata={
                "code": plan.code,
                "name": plan.name,
                "price_cents": plan.price_cents,
                "currency": plan.currency,
                "interval": plan.interval,
            },
        )
        return plan

    @staticmethod
    @transaction.atomic
    def update_plan(*, actor, plan, changes):
        """
        Apply `changes` (a dict of already-validated field -> value) to `plan`,
        with the lock rule enforced here, in the service — not in the
        serializer, which cannot see whether THIS plan is locked without
        reaching for instance state, and not in the view, which would put a
        business rule outside the service layer (CLAUDE.md).

        Raises `PlanLocked` naming every offending field, before anything is
        written, when the plan is externally provisioned and the change touches
        a frozen field. A no-op change (every value already equal) writes
        nothing and records nothing — an audit row that describes no change
        would be noise in the very log an operator reads to find real ones.
        """
        if plan.external_plan_id is not None:
            frozen = {
                field
                for field in changes
                if field not in PlanManagementService.MUTABLE_WHEN_LOCKED
            }
            if frozen:
                raise PlanLocked(frozen)

        before = {field: getattr(plan, field) for field in changes}
        applied = {f: v for f, v in changes.items() if before[f] != v}
        if not applied:
            return plan

        for field, value in applied.items():
            setattr(plan, field, value)
        plan.save(update_fields=sorted(applied))

        # One audit row per request. `is_active` going False/True is the
        # archive/restore action the spec lists in its own right, so it names
        # the action when it changed; any other edit is a plain `plan.updated`.
        if "is_active" in applied:
            archived = applied["is_active"] is False
            action = "plan.archived" if archived else "plan.restored"
            summary = f"{'Archived' if archived else 'Restored'} plan {plan.code}"
        else:
            changed = ", ".join(sorted(applied))
            action = "plan.updated"
            summary = f"Updated plan {plan.code} ({changed})"

        AuditService.record_critical(
            actor=actor,
            action=action,
            target_type="Plan",
            target_id=plan.id,
            summary=summary,
            metadata={
                "code": plan.code,
                "changed": sorted(applied),
                "before": {f: before[f] for f in applied},
                "after": dict(applied),
            },
        )
        return plan

    @staticmethod
    def sync_plan(*, actor, plan):
        """
        Provision `plan` at the configured payment gateway and record it.

        The gateway call itself is `PlanSyncService.sync_plan`, REUSED
        UNMODIFIED (spec §B reuse table) — this method adds only the audit and
        the already-synced short-circuit. It is deliberately NOT
        `@transaction.atomic`: the spec's "honest exception — plan sync" says
        the external create cannot sit inside the same transaction as the local
        write (it has no idempotency key, and the reused service is not
        transaction-wrapped around it). The audit write is attempted
        immediately after a successful sync; if that write fails the request
        surfaces as an error, but the already-committed external plan id cannot
        be unwound. Stated plainly rather than overclaiming atomicity the
        reused service does not support.

        Returns (plan, created): `created` is False when the plan already had an
        `external_plan_id` — a no-op that makes no gateway call and records
        nothing, so a double-clicked sync button cannot create a second gateway
        plan or a second audit row.
        """
        if plan.external_plan_id:
            return plan, False

        external_plan_id = PlanSyncService.sync_plan(plan)
        AuditService.record_critical(
            actor=actor,
            action="plan.synced",
            target_type="Plan",
            target_id=plan.id,
            summary=f"Synced plan {plan.code} to the payment gateway",
            metadata={
                "code": plan.code,
                # The gateway's own id for this plan — an identifier, not a
                # credential and not a payload. Nothing else from the gateway
                # response is recorded.
                "external_plan_id": external_plan_id,
                "payment_gateway": getattr(settings, "PAYMENT_GATEWAY", ""),
            },
        )
        return plan, True

    @staticmethod
    def record_sync_failure(*, actor, plan, exc):
        """
        A gateway sync that raised. Observational, best-effort (never raises):
        nothing changed locally, so this row is not the only record of a state
        change, and a failure to write it must not turn a failed sync into a
        different, misleading error.

        Records the exception's CLASS NAME only — never `str(exc)`, which for a
        provider SDK can carry the gateway's full error body back with it. The
        traceback goes to the application log, where it belongs, not into an
        audit row an operator reads in the browser.
        """
        AuditService.record_observational(
            actor=actor,
            action="plan.sync_failed",
            target_type="Plan",
            target_id=plan.id,
            summary=f"Gateway sync failed for plan {plan.code}",
            metadata={
                "code": plan.code,
                "error_type": type(exc).__name__,
                "payment_gateway": getattr(settings, "PAYMENT_GATEWAY", ""),
            },
        )

"""
Plan limits — property-billing plan §17.

    Basic   max 2 workspaces per owner    max 10 active residents per workspace
    Pro     max 20 workspaces per owner   max 20 active residents per workspace

The numbers live on `Plan` (`max_workspaces`, `max_members_per_workspace`) and
are enforced here, server-side, by the services that create workspaces,
invitations and memberships. The UI only displays what `usage_for_*` returns.

Which plan applies — reconciled with the EXISTING subscription architecture,
where a subscription belongs to one workspace (Subscription.tenant is
OneToOne):

  * A workspace's member limit comes from that workspace's own subscription,
    when it is in an entitled state (TRIALING / ACTIVE / PAST_DUE).
  * An owner's workspace limit is the most generous `max_workspaces` among the
    entitled subscriptions of workspaces they actively own.
  * With no entitled subscription (a brand-new owner who has not subscribed
    yet, or a lapsed one) the DEFAULT limits apply — Basic's numbers, from
    settings.PROPERTY_DEFAULT_PLAN_LIMITS. That is what lets a new account
    create its first workspace in order to subscribe at all.

Counting semantics (identical in every caller and in the UI):

  * workspaces used = the owner's ACTIVE OWNER memberships in workspaces that
    are not closed;
  * members used = ACTIVE MEMBER (resident) memberships — the owner's own seat
    is not counted;
  * pending, unexpired invitations RESERVE a seat when created (so an owner
    cannot mint unlimited invitations); declined, cancelled and expired ones
    release it. Accepting converts the reservation into a membership, so
    acceptance checks active members only.

Concurrency: callers hold a row lock (the owner's User row for workspace
creation, the Tenant row for invitations/acceptance) across count + insert, so
two simultaneous requests cannot both pass a check that only one should.

Downgrades never delete anything: an over-limit workspace simply cannot grow
until it is back under the limit (§17.4).
"""

from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from apps.billing.models import Subscription
from apps.tenants.models import Invitation, Membership

ENTITLED_STATUSES = (
    Subscription.Status.TRIALING,
    Subscription.Status.ACTIVE,
    Subscription.Status.PAST_DUE,
)


class WorkspaceLimitReached(Exception):
    def __init__(self, used, limit):
        super().__init__(f"Workspace limit reached ({used}/{limit}).")
        self.used = used
        self.limit = limit


class MemberLimitReached(Exception):
    def __init__(self, used, limit):
        super().__init__(f"Member limit reached ({used}/{limit}).")
        self.used = used
        self.limit = limit


@dataclass(frozen=True)
class Limits:
    max_workspaces: int
    max_members_per_workspace: int
    plan_code: str | None
    plan_name: str | None


def _default_limits():
    cfg = getattr(settings, "PROPERTY_DEFAULT_PLAN_LIMITS", {})
    return Limits(
        max_workspaces=int(cfg.get("max_workspaces", 2)),
        max_members_per_workspace=int(cfg.get("max_members_per_workspace", 10)),
        plan_code=None,
        plan_name=None,
    )


def _limits_from_plan(plan):
    return Limits(
        max_workspaces=plan.max_workspaces,
        max_members_per_workspace=plan.max_members_per_workspace,
        plan_code=plan.code,
        plan_name=plan.name,
    )


class PlanLimitService:
    @staticmethod
    def workspace_limits(tenant):
        sub = (
            Subscription.objects.for_tenant(tenant)
            .filter(status__in=ENTITLED_STATUSES)
            .select_related("plan")
            .first()
        )
        return _limits_from_plan(sub.plan) if sub else _default_limits()

    @staticmethod
    def account_limits(user):
        owned_tenant_ids = Membership.objects.filter(
            user=user,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        ).values("tenant_id")
        subs = Subscription.objects.filter(
            tenant_id__in=owned_tenant_ids, status__in=ENTITLED_STATUSES
        ).select_related("plan")
        best = max(subs, key=lambda s: s.plan.max_workspaces, default=None)
        return _limits_from_plan(best.plan) if best else _default_limits()

    @staticmethod
    def owned_workspace_count(user):
        return Membership.objects.filter(
            user=user,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
            tenant__closed_at__isnull=True,
        ).count()

    @staticmethod
    def active_member_count(tenant):
        return (
            Membership.objects.for_tenant(tenant)
            .filter(role=Membership.Role.MEMBER, status=Membership.Status.ACTIVE)
            .count()
        )

    @staticmethod
    def pending_invitation_count(tenant, now=None):
        now = now or timezone.now()
        return (
            Invitation.objects.for_tenant(tenant)
            .filter(status=Invitation.Status.PENDING, expires_at__gt=now)
            .count()
        )

    # --- enforcement (caller holds the relevant row lock) ------------------

    @staticmethod
    def assert_can_create_workspace(user):
        limits = PlanLimitService.account_limits(user)
        used = PlanLimitService.owned_workspace_count(user)
        if used >= limits.max_workspaces:
            raise WorkspaceLimitReached(used, limits.max_workspaces)

    @staticmethod
    def assert_can_invite(tenant):
        limits = PlanLimitService.workspace_limits(tenant)
        used = PlanLimitService.active_member_count(
            tenant
        ) + PlanLimitService.pending_invitation_count(tenant)
        if used >= limits.max_members_per_workspace:
            raise MemberLimitReached(used, limits.max_members_per_workspace)

    @staticmethod
    def assert_can_activate_member(tenant):
        limits = PlanLimitService.workspace_limits(tenant)
        used = PlanLimitService.active_member_count(tenant)
        if used >= limits.max_members_per_workspace:
            raise MemberLimitReached(used, limits.max_members_per_workspace)

    # --- read models for the UI -------------------------------------------

    @staticmethod
    def usage_for_workspace(tenant):
        limits = PlanLimitService.workspace_limits(tenant)
        active = PlanLimitService.active_member_count(tenant)
        pending = PlanLimitService.pending_invitation_count(tenant)
        return {
            "plan_code": limits.plan_code,
            "plan_name": limits.plan_name,
            "members": {
                "active": active,
                "pending_invitations": pending,
                "used": active + pending,
                "limit": limits.max_members_per_workspace,
            },
        }

    @staticmethod
    def usage_for_account(user):
        limits = PlanLimitService.account_limits(user)
        owned = (
            Membership.objects.filter(
                user=user,
                role=Membership.Role.OWNER,
                status=Membership.Status.ACTIVE,
                tenant__closed_at__isnull=True,
            )
            .select_related("tenant")
            .order_by("tenant__created_at")
        )
        return {
            "plan_code": limits.plan_code,
            "plan_name": limits.plan_name,
            "workspaces": {
                "used": owned.count(),
                "limit": limits.max_workspaces,
            },
            "owned_workspaces": [
                {
                    "id": str(m.tenant_id),
                    "name": m.tenant.name,
                    **PlanLimitService.usage_for_workspace(m.tenant),
                }
                for m in owned
            ],
        }

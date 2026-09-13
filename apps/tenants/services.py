from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.platform.services import AuditService
from apps.properties.models import Resident
from apps.tenants.limits import PlanLimitService
from apps.tenants.models import Invitation, Membership, Tenant
from apps.users.models import User


class SlugAlreadyTaken(Exception):
    """Raised when a tenant slug collides with an existing Tenant."""


class UserNotFound(Exception):
    """Raised when an invitation targets an email with no (active) User row."""


class AlreadyAMember(Exception):
    """Raised when an invitation targets a user already active in the tenant."""


class InvitationAlreadyPending(Exception):
    """The user already has a pending invitation to this workspace."""


class InvitationNotFound(Exception):
    """No invitation with this id addressed to this user / in this workspace."""


class InvitationNotPending(Exception):
    """The invitation was already answered, cancelled, or has expired."""

    def __init__(self, status):
        super().__init__(f"This invitation is {status.lower()}.")
        self.status = status


class WorkspaceUnavailable(Exception):
    """The workspace is suspended or closed; it cannot gain members."""


class LastOwnerCannotLeave(Exception):
    """Leaving would leave the workspace without an active owner."""


class MembershipNotRemovable(Exception):
    """Owners cannot be removed by this action; only resident memberships."""


class InvalidOwnershipTransfer(Exception):
    """The transfer target must be an active resident member of this workspace."""


class WorkspaceNotEmpty(Exception):
    """A workspace can only be closed once it has no other active members."""


def _owners(tenant):
    return [
        m.user
        for m in Membership.objects.for_tenant(tenant)
        .filter(role=Membership.Role.OWNER, status=Membership.Status.ACTIVE)
        .select_related("user")
    ]


def _audit(*, actor, tenant, action, target_type, target_id, summary, metadata=None):
    AuditService.record_critical(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary[:255],
        metadata={"tenant_id": str(tenant.id), **(metadata or {})},
    )


def _display_name(user):
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.email


class TenantService:
    """
    Tenant lifecycle. Mirrors the one-class-per-aggregate shape of
    apps/billing/services.py.
    """

    @staticmethod
    def create_tenant(user, name, slug):
        """
        Create the Tenant and the requesting user's OWNER Membership in a
        single atomic block. The OWNER row is built inline rather than via
        MembershipService: different rule (OWNER, brand-new tenant, no
        possible duplicate) and it must share this transaction.

        Property-billing plan §17.1: the owner's workspace limit is checked
        while holding a row lock on the owner's User row, so two concurrent
        creations by the same account serialise and cannot both squeeze past
        the last free slot. Raises apps.tenants.limits.WorkspaceLimitReached.
        """
        try:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=user.pk)
                PlanLimitService.assert_can_create_workspace(user)
                tenant = Tenant.objects.create(name=name, slug=slug)
                membership = Membership.objects.create(
                    user=user, tenant=tenant, role=Membership.Role.OWNER
                )
        except IntegrityError:
            # Caught OUTSIDE the atomic block that raised it.
            raise SlugAlreadyTaken()
        return tenant, membership

    @staticmethod
    def tenants_for_user(user):
        """
        Every ACTIVE Membership the user holds, tenant pre-joined. Deliberately
        NOT for_tenant() — this query spans tenants by definition ("which
        tenants am I in"). One query, no per-tenant loop. A membership the user
        left, or was removed from, is not a workspace they are in.
        """
        return Membership.objects.select_related("tenant").filter(
            user=user, status=Membership.Status.ACTIVE
        )

    @staticmethod
    def close_workspace(*, actor, tenant):
        """
        An owner closes a workspace they no longer operate (plan §27.4 "workspace
        closure"). Only once no other active member remains; pending invitations
        are cancelled; the owner's own membership ends. Nothing is deleted —
        properties, bills and receipts stay for the platform admin's history.
        """
        with transaction.atomic():
            tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
            others = (
                Membership.objects.for_tenant(tenant)
                .filter(status=Membership.Status.ACTIVE)
                .exclude(user=actor)
            )
            if others.exists():
                raise WorkspaceNotEmpty()
            now = timezone.now()
            Invitation.objects.for_tenant(tenant).filter(
                status=Invitation.Status.PENDING
            ).update(status=Invitation.Status.CANCELLED, responded_at=now)
            Membership.objects.for_tenant(tenant).filter(user=actor).update(
                status=Membership.Status.LEFT, ended_at=now
            )
            tenant.closed_at = now
            tenant.save(update_fields=["closed_at"])
            _audit(
                actor=actor,
                tenant=tenant,
                action="workspace.closed",
                target_type="Tenant",
                target_id=tenant.id,
                summary=f"Closed workspace {tenant.name}",
            )
        return tenant


class MembershipService:
    """
    Membership lifecycle for an EXISTING membership. There is deliberately no
    way to create an active membership for another person here: that happens
    only in InvitationService.respond, when the invited user accepts.
    """

    @staticmethod
    def _member_exists(tenant, user):
        # Named method so tests can patch it to force the check-then-insert
        # race; the real guarantee is the locked re-check in
        # InvitationService.create plus UNIQUE(user, tenant).
        return (
            Membership.objects.for_tenant(tenant)
            .filter(user=user, status=Membership.Status.ACTIVE)
            .exists()
        )

    @staticmethod
    def _end(membership, status):
        membership.status = status
        membership.ended_at = timezone.now()
        membership.save(update_fields=["status", "ended_at"])
        Resident.objects.for_tenant(membership.tenant).filter(user=membership.user).update(
            status=Resident.Status.INACTIVE
        )

    @staticmethod
    def leave(*, user, tenant):
        """The authenticated user leaves the workspace (plan §27.1). Their
        account, and every historical bill/receipt naming them, is untouched."""
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            membership = (
                Membership.objects.for_tenant(tenant)
                .select_for_update()
                .get(user=user, status=Membership.Status.ACTIVE)
            )
            if membership.role == Membership.Role.OWNER:
                other_owners = (
                    Membership.objects.for_tenant(tenant)
                    .filter(role=Membership.Role.OWNER, status=Membership.Status.ACTIVE)
                    .exclude(pk=membership.pk)
                )
                if not other_owners.exists():
                    raise LastOwnerCannotLeave()
            MembershipService._end(membership, Membership.Status.LEFT)
            for owner in _owners(tenant):
                NotificationService.notify(
                    recipient=owner,
                    kind=Notification.Kind.MEMBER_LEFT,
                    tenant=tenant,
                    title=f"{_display_name(user)} left {tenant.name}",
                    body="Their billing history in this workspace is kept.",
                    data={"membership_id": str(membership.id)},
                )
            _audit(
                actor=user,
                tenant=tenant,
                action="membership.left",
                target_type="Membership",
                target_id=membership.id,
                summary=f"{user.email} left {tenant.name}",
            )
        return membership

    @staticmethod
    def remove(*, actor, tenant, membership):
        with transaction.atomic():
            membership = Membership.objects.for_tenant(tenant).select_for_update().get(
                pk=membership.pk
            )
            if membership.role != Membership.Role.MEMBER:
                raise MembershipNotRemovable()
            if membership.status != Membership.Status.ACTIVE:
                return membership
            MembershipService._end(membership, Membership.Status.REMOVED)
            NotificationService.notify(
                recipient=membership.user,
                kind=Notification.Kind.MEMBERSHIP_ENDED,
                tenant=tenant,
                title=f"Your membership of {tenant.name} has ended",
                body="Your past bills and receipts remain on record with the owner.",
            )
            _audit(
                actor=actor,
                tenant=tenant,
                action="membership.removed",
                target_type="Membership",
                target_id=membership.id,
                summary=f"Removed {membership.user.email} from {tenant.name}",
            )
        return membership

    @staticmethod
    def transfer_ownership(*, actor, tenant, target):
        """
        Hand the workspace to an active resident member (plan §27.4: the safe
        alternative to orphaning a workspace). The target's own account
        workspace limit applies — becoming an owner consumes one of their slots.
        """
        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            target = Membership.objects.for_tenant(tenant).select_for_update().get(
                pk=target.pk
            )
            if (
                target.role != Membership.Role.MEMBER
                or target.status != Membership.Status.ACTIVE
                or target.user_id == actor.id
            ):
                raise InvalidOwnershipTransfer()
            User.objects.select_for_update().get(pk=target.user_id)
            PlanLimitService.assert_can_create_workspace(target.user)
            current = (
                Membership.objects.for_tenant(tenant)
                .select_for_update()
                .get(user=actor, status=Membership.Status.ACTIVE)
            )
            target.role = Membership.Role.OWNER
            target.save(update_fields=["role"])
            current.role = Membership.Role.MEMBER
            current.save(update_fields=["role"])
            _audit(
                actor=actor,
                tenant=tenant,
                action="membership.ownership_transferred",
                target_type="Membership",
                target_id=target.id,
                summary=f"Transferred ownership of {tenant.name} to {target.user.email}",
                metadata={"from_user_id": str(actor.id), "to_user_id": str(target.user_id)},
            )
        return target


class InvitationService:
    """
    Consent-based membership (plan §4.4 / §43.7):

        owner creates invitation  ->  PENDING (+ notification, seat reserved)
        invited user accepts      ->  ACTIVE membership + Resident profile
        invited user declines     ->  DECLINED (seat released)
        owner cancels / expiry    ->  CANCELLED / EXPIRED (seat released)
    """

    EXPIRY = timedelta(days=14)

    @staticmethod
    def _expire_stale(queryset, now):
        queryset.filter(status=Invitation.Status.PENDING, expires_at__lte=now).update(
            status=Invitation.Status.EXPIRED
        )

    @staticmethod
    def create(*, tenant, inviter, email, unit=None, message=""):
        try:
            user = User.objects.get(
                email=User.objects.normalize_email(email), is_active=True
            )
        except User.DoesNotExist:
            raise UserNotFound()

        # UX pre-check only; the locked re-check below is the guarantee.
        if MembershipService._member_exists(tenant, user):
            raise AlreadyAMember()

        now = timezone.now()
        try:
            with transaction.atomic():
                locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
                if not locked.is_active or locked.closed_at is not None:
                    raise WorkspaceUnavailable()
                if (
                    Membership.objects.for_tenant(tenant)
                    .filter(user=user, status=Membership.Status.ACTIVE)
                    .exists()
                ):
                    raise AlreadyAMember()
                InvitationService._expire_stale(
                    Invitation.objects.for_tenant(tenant), now
                )
                if (
                    Invitation.objects.for_tenant(tenant)
                    .filter(invited_user=user, status=Invitation.Status.PENDING)
                    .exists()
                ):
                    raise InvitationAlreadyPending()
                PlanLimitService.assert_can_invite(tenant)
                with transaction.atomic():
                    invitation = Invitation.objects.create(
                        tenant=tenant,
                        invited_user=user,
                        invited_by=inviter,
                        email=user.email,
                        role=Membership.Role.MEMBER,
                        unit=unit,
                        message=message,
                        expires_at=now + InvitationService.EXPIRY,
                    )
                context = f" for unit {unit.identifier}, {unit.property.name}" if unit else ""
                NotificationService.notify(
                    recipient=user,
                    kind=Notification.Kind.INVITATION_RECEIVED,
                    tenant=tenant,
                    title=f"{tenant.name} invited you to join as a resident",
                    body=(
                        f"Invitation{context}. Accept to see your bills and receipts; "
                        "nothing changes until you do."
                    ),
                    data={"invitation_id": str(invitation.id)},
                )
                _audit(
                    actor=inviter,
                    tenant=tenant,
                    action="invitation.created",
                    target_type="Invitation",
                    target_id=invitation.id,
                    summary=f"Invited {user.email} to {tenant.name}",
                )
        except IntegrityError:
            # Two concurrent invitations for the same user: the partial unique
            # constraint rejected the second one. Caught outside the atomic block.
            raise InvitationAlreadyPending()
        return invitation

    @staticmethod
    def cancel(*, actor, tenant, invitation_id):
        with transaction.atomic():
            try:
                invitation = (
                    Invitation.objects.for_tenant(tenant)
                    .select_for_update()
                    .get(pk=invitation_id)
                )
            except Invitation.DoesNotExist:
                raise InvitationNotFound()
            if invitation.status != Invitation.Status.PENDING:
                raise InvitationNotPending(invitation.status)
            invitation.status = Invitation.Status.CANCELLED
            invitation.responded_at = timezone.now()
            invitation.save(update_fields=["status", "responded_at"])
            NotificationService.notify(
                recipient=invitation.invited_user,
                kind=Notification.Kind.INVITATION_CANCELLED,
                tenant=tenant,
                title=f"Your invitation to {tenant.name} was withdrawn",
                data={"invitation_id": str(invitation.id)},
            )
            _audit(
                actor=actor,
                tenant=tenant,
                action="invitation.cancelled",
                target_type="Invitation",
                target_id=invitation.id,
                summary=f"Cancelled invitation for {invitation.email}",
            )
        return invitation

    @staticmethod
    def for_tenant(tenant):
        now = timezone.now()
        InvitationService._expire_stale(Invitation.objects.for_tenant(tenant), now)
        return (
            Invitation.objects.for_tenant(tenant)
            .select_related("tenant", "invited_by", "unit", "unit__property")
            .order_by("-created_at")
        )

    @staticmethod
    def for_user(user):
        now = timezone.now()
        InvitationService._expire_stale(Invitation.objects.filter(invited_user=user), now)
        return (
            Invitation.objects.filter(invited_user=user)
            .select_related("tenant", "invited_by", "unit", "unit__property")
            .order_by("-created_at")
        )

    @staticmethod
    def respond(*, user, invitation_id, accept):
        """
        The invited user's decision. Authorized by `invited_user == user` in the
        lookup itself: someone else's invitation id is simply not found.

        Idempotent: accepting an already-accepted invitation (a double click, a
        retried request) returns it unchanged; the same for declining twice.
        """
        now = timezone.now()
        # Persist expiry BEFORE the decision transaction: marking it inside that
        # block and then refusing would roll the EXPIRED status back.
        InvitationService._expire_stale(
            Invitation.objects.filter(pk=invitation_id, invited_user=user), now
        )
        with transaction.atomic():
            try:
                invitation = (
                    Invitation.objects.select_for_update()
                    .select_related("tenant")
                    .get(pk=invitation_id, invited_user=user)
                )
            except Invitation.DoesNotExist:
                raise InvitationNotFound()

            target_status = Invitation.Status.ACCEPTED if accept else Invitation.Status.DECLINED
            if invitation.status == target_status:
                return invitation
            if invitation.status == Invitation.Status.PENDING and invitation.expires_at <= now:
                raise InvitationNotPending(Invitation.Status.EXPIRED)
            if invitation.status != Invitation.Status.PENDING:
                raise InvitationNotPending(invitation.status)

            tenant = Tenant.objects.select_for_update().get(pk=invitation.tenant_id)

            if not accept:
                invitation.status = Invitation.Status.DECLINED
                invitation.responded_at = now
                invitation.save(update_fields=["status", "responded_at"])
                for owner in _owners(tenant):
                    NotificationService.notify(
                        recipient=owner,
                        kind=Notification.Kind.INVITATION_DECLINED,
                        tenant=tenant,
                        title=f"{user.email} declined the invitation to {tenant.name}",
                        data={"invitation_id": str(invitation.id)},
                    )
                _audit(
                    actor=user,
                    tenant=tenant,
                    action="invitation.declined",
                    target_type="Invitation",
                    target_id=invitation.id,
                    summary=f"{user.email} declined the invitation to {tenant.name}",
                )
                return invitation

            if not tenant.is_active or tenant.closed_at is not None:
                raise WorkspaceUnavailable()
            PlanLimitService.assert_can_activate_member(tenant)

            membership = Membership.objects.for_tenant(tenant).filter(user=user).first()
            if membership is None:
                membership = Membership.objects.create(
                    user=user, tenant=tenant, role=Membership.Role.MEMBER
                )
            else:
                # A returning resident: the same row is reactivated, so
                # UNIQUE(user, tenant) never needs relaxing and history stays
                # attached to one membership.
                membership.status = Membership.Status.ACTIVE
                membership.ended_at = None
                if membership.role != Membership.Role.OWNER:
                    membership.role = Membership.Role.MEMBER
                membership.save(update_fields=["status", "ended_at", "role"])

            resident, created = Resident.objects.get_or_create(
                tenant=tenant,
                user=user,
                defaults={"display_name": _display_name(user), "phone": user.phone},
            )
            if not created and resident.status != Resident.Status.ACTIVE:
                resident.status = Resident.Status.ACTIVE
                resident.save(update_fields=["status", "updated_at"])

            invitation.status = Invitation.Status.ACCEPTED
            invitation.responded_at = now
            invitation.save(update_fields=["status", "responded_at"])

            usage = PlanLimitService.usage_for_workspace(tenant)["members"]
            for owner in _owners(tenant):
                NotificationService.notify(
                    recipient=owner,
                    kind=Notification.Kind.INVITATION_ACCEPTED,
                    tenant=tenant,
                    title=f"{_display_name(user)} joined {tenant.name}",
                    body="They are now an active resident and can be given a lease.",
                    data={"invitation_id": str(invitation.id), "resident_id": str(resident.id)},
                )
                if usage["used"] >= usage["limit"]:
                    NotificationService.notify(
                        recipient=owner,
                        kind=Notification.Kind.PLAN_LIMIT,
                        tenant=tenant,
                        title=f"{tenant.name} has reached its member limit",
                        body=f"{usage['used']} of {usage['limit']} resident seats are in use.",
                        dedupe_key=f"member-limit:{tenant.id}:{usage['limit']}:{usage['used']}",
                    )
            _audit(
                actor=user,
                tenant=tenant,
                action="invitation.accepted",
                target_type="Invitation",
                target_id=invitation.id,
                summary=f"{user.email} accepted the invitation to {tenant.name}",
                metadata={"membership_id": str(membership.id)},
            )
        return invitation

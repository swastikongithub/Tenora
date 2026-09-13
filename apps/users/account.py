"""
Account lifecycle — profile, password, and account deletion (property-billing
plan §27.3–27.5). Distinct from leaving a workspace (MembershipService.leave):
deletion ends the Tenora identity itself.

Deletion is anonymize-and-deactivate, never a hard DELETE of the User row:

  * bills, payments, receipts, leases, meter readings and audit rows keep a
    valid foreign key — financial history is never cascaded away;
  * issued bills and receipts keep the name/email snapshot they were issued
    with (financial-document retention); the live Resident profile, the User
    row and notifications lose the personal data;
  * the email is freed, so the person may register again later as a genuinely
    NEW account that inherits no membership, ownership, token or state.

Refused (nothing changes) when it would break an invariant:

  * the user still actively OWNS a workspace — deleting would orphan it; they
    must transfer ownership or close the workspace first;
  * the user is the last active platform root (the operator-control-plane
    last-root invariant).

Access ends immediately: `is_active=False` makes SimpleJWT reject every access
token on its next use, and every outstanding refresh token is blacklisted.
Idempotent: a second call for an already-deleted account is a no-op.
"""

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.notifications.models import Notification
from apps.platform.permissions import ROOT_Q, is_platform_root
from apps.platform.services import AuditService
from apps.properties.models import Resident
from apps.tenants.models import Invitation, Membership
from apps.users.models import User


class ConfirmationMismatch(Exception):
    pass


class OwnsWorkspaces(Exception):
    def __init__(self, workspaces):
        super().__init__("Transfer or close owned workspaces first.")
        self.workspaces = workspaces


class LastRootAccount(Exception):
    pass


class InvalidCurrentPassword(Exception):
    pass


class AccountService:
    PROFILE_FIELDS = ("first_name", "last_name", "phone")

    @staticmethod
    def update_profile(*, user, changes):
        fields = [f for f in AccountService.PROFILE_FIELDS if f in changes]
        for field in fields:
            setattr(user, field, changes[field].strip())
        if fields:
            user.save(update_fields=fields)
        return user

    @staticmethod
    def change_password(*, user, current_password, new_password):
        """A Google-only account (no usable password) may set its first password
        without a current one; every other account must prove the current one."""
        if user.has_usable_password() and not user.check_password(current_password or ""):
            raise InvalidCurrentPassword()
        validate_password(new_password, user=user)
        user.set_password(new_password)
        user.save(update_fields=["password"])
        AuditService.record_critical(
            actor=user,
            action="account.password_changed",
            target_type="User",
            target_id=user.id,
            summary="Changed account password",
        )
        return user

    @staticmethod
    def deletion_blockers(user):
        owned = list(
            Membership.objects.filter(
                user=user, role=Membership.Role.OWNER, status=Membership.Status.ACTIVE
            ).select_related("tenant")
        )
        return [{"id": str(m.tenant_id), "name": m.tenant.name} for m in owned]

    @staticmethod
    def delete_account(*, user, confirmation):
        if user.deleted_at is not None:
            return user
        if (confirmation or "").strip().lower() != user.email.lower():
            raise ConfirmationMismatch()
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user.pk)
            if user.deleted_at is not None:
                return user
            blockers = AccountService.deletion_blockers(user)
            if blockers:
                raise OwnsWorkspaces(blockers)
            if is_platform_root(user):
                # Lock every root row so two roots cannot delete themselves at once.
                roots = list(User.objects.select_for_update().filter(ROOT_Q).values_list("pk", flat=True))
                if set(roots) == {user.pk}:
                    raise LastRootAccount()

            now = timezone.now()
            original_email = user.email
            memberships = Membership.objects.filter(user=user, status=Membership.Status.ACTIVE)
            ended = memberships.count()
            memberships.update(status=Membership.Status.LEFT, ended_at=now)
            Invitation.objects.filter(invited_user=user, status=Invitation.Status.PENDING).update(
                status=Invitation.Status.CANCELLED, responded_at=now
            )
            Resident.objects.filter(user=user).update(
                status=Resident.Status.INACTIVE, display_name="Deleted account", phone=""
            )
            Notification.objects.filter(recipient=user).delete()

            for token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=token)

            user.email = f"deleted-{user.pk.hex}@deleted.invalid"
            user.first_name = ""
            user.last_name = ""
            user.phone = ""
            user.is_active = False
            user.is_staff = False
            user.is_superuser = False
            user.email_verified = False
            user.deleted_at = now
            user.set_unusable_password()
            user.save()

            AuditService.record_critical(
                actor=user,
                action="account.deleted",
                target_type="User",
                target_id=user.id,
                summary="Account deleted (anonymized; financial history retained)",
                # The original address is deliberately NOT recorded here — the
                # audit trail must not become the one place the identity survives.
                metadata={"memberships_ended": ended, "had_email_domain": original_email.split("@")[-1]},
            )
        return user

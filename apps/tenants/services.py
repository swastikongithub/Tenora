from django.db import IntegrityError, transaction

from apps.tenants.models import Membership, Tenant
from apps.users.models import User


class SlugAlreadyTaken(Exception):
    """Raised when a tenant slug collides with an existing Tenant."""


class UserNotFound(Exception):
    """Raised when member-add targets an email with no User row."""


class AlreadyAMember(Exception):
    """Raised when member-add targets a user already in the tenant."""


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
        """
        try:
            with transaction.atomic():
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
        Every Membership the user holds, tenant pre-joined. Deliberately
        NOT for_tenant() — this query spans tenants by definition
        ("which tenants am I in"). One query, no per-tenant loop.
        """
        return Membership.objects.select_related("tenant").filter(user=user)


class MembershipService:
    """Member-add for POST /api/memberships/. OWNER-only, MEMBER-only."""

    @staticmethod
    def _member_exists(tenant, user):
        # Named method so tests can patch it to force the check-then-insert
        # race that exercises the IntegrityError path.
        return Membership.objects.for_tenant(tenant).filter(user=user).exists()

    @staticmethod
    def add_member(tenant, email):
        try:
            # Normalize the same way UserManager stores it, so the lookup
            # is reliably case-insensitive end to end.
            user = User.objects.get(email=User.objects.normalize_email(email))
        except User.DoesNotExist:
            raise UserNotFound()

        # Pre-check is a UX convenience only. UNIQUE(user, tenant) is the
        # real guarantee — spec §A.4.16.
        if MembershipService._member_exists(tenant, user):
            raise AlreadyAMember()

        try:
            with transaction.atomic():
                return Membership.objects.create(
                    user=user, tenant=tenant, role=Membership.Role.MEMBER
                )
        except IntegrityError:
            # Caught OUTSIDE the atomic block that raised it. The `with`
            # opened a savepoint; it has been rolled back by the time we
            # reach here, so the surrounding transaction stays usable —
            # this is also what makes the handler work inside TestCase's
            # per-test transaction. Both this path and the pre-check path
            # raise AlreadyAMember, so the view returns an identical 400.
            raise AlreadyAMember()

from rest_framework.permissions import BasePermission

from apps.tenants.models import Membership


class IsTenantMember(BasePermission):
    """
    Baseline check: the request has a resolved tenant/membership at
    all. TenantJWTAuthentication already guarantees this for any
    tenant-scoped path, so this mostly exists as a defensive,
    explicit statement of intent on the view — and as a place to
    fail loudly if authentication config ever changes.
    """

    message = "This endpoint requires a resolved tenant context."

    def has_permission(self, request, view):
        return getattr(request, "membership", None) is not None


class IsTenantOwner(BasePermission):
    """
    Restricts an action to OWNER-role members of the current tenant.
    Deliberately reads role from request.membership (resolved once,
    at authentication time) rather than re-querying — avoids a
    second trip to the DB and avoids any risk of the permission
    check using a different membership row than authentication did.
    """

    message = "Only the tenant owner can perform this action."

    def has_permission(self, request, view):
        membership = getattr(request, "membership", None)
        return membership is not None and membership.role == Membership.Role.OWNER

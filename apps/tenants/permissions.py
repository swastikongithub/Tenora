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


# Property-billing plan §43.14: authorization is phrased as CAPABILITIES granted
# to a role, not as `role == OWNER` scattered across views. Today there are two
# roles; a future Property Manager or Accountant is one more entry here (e.g.
# {"property.manage", "billing.manage"}), with no view rewritten.
#
# `billing.view_own` is the resident capability: every resident-visible query
# additionally filters on the authenticated user's own Resident profile, so the
# capability never widens what a resident can read — it only admits them.
ROLE_CAPABILITIES = {
    Membership.Role.OWNER: frozenset(
        {
            "workspace.manage",
            "members.manage",
            "property.manage",
            "billing.manage",
            "payments.manage",
            "reports.view",
            "subscription.view",
            "subscription.manage",
        }
    ),
    Membership.Role.MEMBER: frozenset({"billing.view_own"}),
}


def has_capability(membership, capability):
    if membership is None or membership.status != Membership.Status.ACTIVE:
        return False
    return capability in ROLE_CAPABILITIES.get(membership.role, frozenset())


def RequiresCapability(capability):
    """Build a DRF permission class requiring one workspace capability."""

    class _RequiresCapability(BasePermission):
        message = "Your role in this workspace does not allow this action."

        def has_permission(self, request, view):
            return has_capability(getattr(request, "membership", None), capability)

    _RequiresCapability.__name__ = f"Requires[{capability}]"
    return _RequiresCapability

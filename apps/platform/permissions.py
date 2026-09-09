from rest_framework.permissions import BasePermission


class IsPlatformStaff(BasePermission):
    """
    The real boundary for the platform-admin endpoints — the one deliberate
    exception to this project's tenant-isolation architecture (see
    docs/platform-admin-spec.md §1).

    Structurally this mirrors IsTenantOwner's shape (a message + a single
    has_permission check), but it deliberately lives in apps/platform/, not
    apps/tenants/permissions.py: it checks a platform-wide flag on the user
    (`is_staff`, already the gate for Django admin) and reads nothing
    tenant- or membership-derived. Grouping it with IsTenantOwner /
    IsTenantMember would imply a tenant-permission relationship that does
    not exist here.

    Reusing `is_staff` rather than inventing a new field is correct: it
    already means "this person can reach privileged, platform-level tooling."
    That is the same concept, not two meanings forced into one flag — the
    opposite of the is_active / email_verified situation the
    email-verification stage correctly kept separate.
    """

    message = "This endpoint is restricted to platform staff."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)

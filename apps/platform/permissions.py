from django.db.models import Q
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


# The Root predicate, written once — docs/operator-control-plane-spec.md §E:
# "Root = emergency/root authority, checked as `is_staff AND is_superuser`
# (both flags, deliberately, as defense in depth — a superuser somehow missing
# `is_staff` should not silently retain platform access)", plus `is_active`,
# which the self-lockout invariant is phrased over (§E "Self-lockout /
# last-root invariant").
#
# Two shapes of the SAME rule, because two callers need two shapes: a Python
# predicate for the permission class (which has a user object in hand) and an
# ORM Q for the invariant guard (which has to count rows). They are kept
# adjacent, and a test asserts they agree on every combination of the three
# flags — a drift between them would either lock the platform out or let the
# last Root be demoted.
ROOT_Q = Q(is_staff=True, is_superuser=True, is_active=True)


def is_platform_root(user) -> bool:
    return bool(
        user
        and getattr(user, "is_staff", False)
        and getattr(user, "is_superuser", False)
        and getattr(user, "is_active", False)
    )


class IsPlatformRoot(BasePermission):
    """
    The narrow Root tier — docs/operator-control-plane-spec.md §B: reserved
    for actions that change *who has power* or lock out an entire tenant.
    Exactly three things reach for it: user role management, tenant
    suspend/reactivate, and the raw gateway payload view.

    Deliberately a SEPARATE class from IsPlatformStaff rather than a flag on
    it: the two tiers answer different questions, and a Root-gated view should
    name the Root class in its own permission list, where a reader sees it.
    Root implies Staff (a Root user satisfies IsPlatformStaff too), so a view
    may list either, never both.

    Staff-tier work never needs this. An operator can run the entire control
    plane — plans, subscription overrides, every sweep, every read except the
    raw payload — under an `is_staff`-only account indefinitely (§B).
    """

    message = "This action is restricted to root operators."

    def has_permission(self, request, view):
        return is_platform_root(request.user)

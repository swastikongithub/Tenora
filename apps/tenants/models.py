import uuid

from django.conf import settings
from django.db import models

from apps.tenants.managers import TenantScopedManager


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    # Set when the workspace's owner CLOSES it (property-billing plan §27.4).
    # Deliberately distinct from `is_active`, which is the platform operator's
    # suspension flag: a closed workspace has no active memberships left at all,
    # so nobody can resolve it — its financial history stays in place for the
    # platform admin, and nothing is deleted.
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    """
    The join between a User and a Tenant. This is the single row that
    answers "does this user have any right to act as this tenant, and
    with what role" — TenantJWTAuthentication resolves exactly this
    row on every tenant-scoped request.
    """

    class Role(models.TextChoices):
        # OWNER is the workspace owner — the Tenora customer. MEMBER is, in the
        # property-billing domain, a RESIDENT: the stored value is kept as
        # MEMBER so every existing row, test and client keeps working, and the
        # UI labels it "Resident". Capabilities are mapped per role in
        # apps.tenants.permissions.ROLE_CAPABILITIES, so a future delegated
        # role (property manager, accountant) is a new choice plus a new
        # capability set, not a rewrite of every permission check.
        OWNER = "OWNER", "Owner"
        MEMBER = "MEMBER", "Member"

    class Status(models.TextChoices):
        # Only ACTIVE resolves in TenantJWTAuthentication and only ACTIVE
        # counts toward a plan's member limit. LEFT / REMOVED rows are kept
        # (never hard-deleted) because leases, bills and receipts reference the
        # person; the row is also what a later re-invitation reactivates, so
        # UNIQUE(user, tenant) never has to be relaxed.
        ACTIVE = "ACTIVE", "Active"
        LEFT = "LEFT", "Left"
        REMOVED = "REMOVED", "Removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Membership is unambiguously tenant-owned data (spec §A.2.9). The
    # manager only *adds* for_tenant(); .get()/.filter() are untouched,
    # so the lookup in TenantJWTAuthentication keeps working.
    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant"], name="unique_membership"
            )
        ]
        indexes = [
            models.Index(fields=["tenant"]),
            models.Index(fields=["tenant", "status", "role"]),
        ]

    def __str__(self):
        return f"{self.user} @ {self.tenant} ({self.role})"


class Invitation(models.Model):
    """
    A consent-based invitation to join a workspace as a resident
    (property-billing plan §4.4). Creating one grants NOTHING: the invited
    user has no access until they accept it themselves, and accepting is the
    only path by which an owner's action results in an ACTIVE membership.

    Always targets an existing account (`invited_user`), because the in-app
    notification IS the control point — an invitation nobody can see could
    never be accepted. `email` is a snapshot for display.

    Expiry is evaluated against `expires_at` at read/act time rather than by a
    scheduler, so correctness never depends on a worker running; a stale
    PENDING row past its expiry is reported and treated as EXPIRED everywhere.

    UNIQUE(tenant, invited_user) WHERE status = PENDING is the duplicate-
    invitation guarantee — a constraint, not a pre-check.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="invitations"
    )
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="invitations_received",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=10, choices=Membership.Role.choices, default=Membership.Role.MEMBER
    )
    # Optional context shown to the invitee ("Unit 203, Sunrise Apartments").
    # It grants nothing on acceptance — a lease is the owner's separate act.
    unit = models.ForeignKey(
        "properties.Unit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    message = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)

    objects = TenantScopedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "invited_user"],
                condition=models.Q(status="PENDING"),
                name="unique_pending_invitation",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["invited_user", "status"]),
        ]

    def __str__(self):
        return f"invitation {self.email} → {self.tenant} ({self.status})"

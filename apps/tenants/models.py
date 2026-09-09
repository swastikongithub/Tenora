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
        OWNER = "OWNER", "Owner"
        MEMBER = "MEMBER", "Member"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
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
        indexes = [models.Index(fields=["tenant"])]

    def __str__(self):
        return f"{self.user} @ {self.tenant} ({self.role})"

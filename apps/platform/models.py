import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """
    An immutable record of one operator action — docs
    /operator-control-plane-spec.md §B "Audit semantics: critical vs.
    observational". Written through exactly two paths
    (apps.platform.services.AuditService.record_critical /
    .record_observational), never created ad hoc elsewhere.

    Plain snapshot fields (`target_type`/`target_id` as strings), not a
    GenericForeignKey — the same instinct this codebase already applies to
    its other audit tables (e.g. `ReconciliationDiscrepancy`'s
    `local_status`/`provider_status`): no dependency on `contenttypes`, no
    coupling to a target model's own lifecycle, and a target row deleted
    later still leaves a legible row here.

    `actor` is `SET_NULL`, not `PROTECT`/`CASCADE`: removing a user account
    must never destroy the audit trail of what they did, nor be blocked by
    it — the action is still fully described by
    `action`/`target_type`/`target_id`/`summary` even with `actor=None`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=32)
    target_id = models.CharField(max_length=64)
    summary = models.CharField(max_length=255)
    # Small, useful before/after values only — never a password, a secret,
    # or a raw gateway webhook payload. See AuditService for the write-time
    # discipline; enforced by convention and tests, not a DB constraint.
    metadata = models.JSONField(default=dict, blank=True)
    is_critical = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["actor"]),
            models.Index(fields=["action"]),
            models.Index(fields=["target_type"]),
        ]

    def __str__(self):
        return f"{self.action} — {self.summary}"

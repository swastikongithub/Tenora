"""
In-app notifications (property-billing plan §25, §43.6).

A notification belongs to exactly one user (`recipient`) and is only ever read
through a query filtered on the authenticated user — never by id alone — so it
cannot become a cross-user leak. It is written in the SAME transaction as the
business event it describes, so an invitation or a published bill can never
exist without its notification (or vice versa). External delivery (email/SMS)
is deliberately absent: billing correctness never depends on it.
"""

import uuid

from django.conf import settings
from django.db import models

from apps.tenants.models import Tenant


class Notification(models.Model):
    class Kind(models.TextChoices):
        INVITATION_RECEIVED = "INVITATION_RECEIVED", "Invitation received"
        INVITATION_ACCEPTED = "INVITATION_ACCEPTED", "Invitation accepted"
        INVITATION_DECLINED = "INVITATION_DECLINED", "Invitation declined"
        INVITATION_CANCELLED = "INVITATION_CANCELLED", "Invitation cancelled"
        MEMBER_LEFT = "MEMBER_LEFT", "Member left"
        MEMBERSHIP_ENDED = "MEMBERSHIP_ENDED", "Membership ended"
        BILL_PUBLISHED = "BILL_PUBLISHED", "Bill published"
        BILL_DUE_SOON = "BILL_DUE_SOON", "Bill due soon"
        BILL_OVERDUE = "BILL_OVERDUE", "Bill overdue"
        BILL_CORRECTED = "BILL_CORRECTED", "Bill corrected"
        BILL_CANCELLED = "BILL_CANCELLED", "Bill cancelled"
        PAYMENT_RECORDED = "PAYMENT_RECORDED", "Payment recorded"
        PAYMENT_VOIDED = "PAYMENT_VOIDED", "Payment voided"
        RECEIPT_ISSUED = "RECEIPT_ISSUED", "Receipt issued"
        OVERDUE_SUMMARY = "OVERDUE_SUMMARY", "Overdue summary"
        CYCLE_INCOMPLETE = "CYCLE_INCOMPLETE", "Billing cycle incomplete"
        PLAN_LIMIT = "PLAN_LIMIT", "Plan limit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    # The workspace the event happened in, for context and for routing the
    # client to the right workspace. Never an authorization input.
    tenant = models.ForeignKey(
        Tenant, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=255)
    body = models.CharField(max_length=1000, blank=True)
    # Small routing hints only (invitation_id, bill_id, receipt_id) — never
    # another person's data beyond what the recipient may already see.
    data = models.JSONField(default=dict, blank=True)
    # Idempotency for generated reminders ("overdue:<bill>:31_60"): a second run
    # of the reminder sweep collides here instead of notifying twice.
    dedupe_key = models.CharField(max_length=128, null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedupe_key"],
                condition=models.Q(dedupe_key__isnull=False),
                name="unique_notification_dedupe",
            )
        ]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "read_at"]),
        ]
        ordering = ["-created_at"]


class NotificationPreference(models.Model):
    """Per-user in-app preferences. Invitations are deliberately not mutable:
    the notification is the only place an invitation can be accepted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    billing = models.BooleanField(default=True)
    payments = models.BooleanField(default=True)
    membership = models.BooleanField(default=True)
    # Stored for a future delivery channel; nothing sends email today.
    email_enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

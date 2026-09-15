from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.models import Notification, NotificationPreference

K = Notification.Kind

# Which preference switch silences which kind. A kind absent from this map
# (an invitation the user must be able to answer) cannot be muted.
PREFERENCE_FOR_KIND = {
    K.INVITATION_ACCEPTED: "membership",
    K.INVITATION_DECLINED: "membership",
    K.INVITATION_CANCELLED: "membership",
    K.MEMBER_LEFT: "membership",
    K.MEMBERSHIP_ENDED: "membership",
    K.BILL_PUBLISHED: "billing",
    K.BILL_DUE_SOON: "billing",
    K.BILL_OVERDUE: "billing",
    K.BILL_CORRECTED: "billing",
    K.BILL_CANCELLED: "billing",
    K.OVERDUE_SUMMARY: "billing",
    K.CYCLE_INCOMPLETE: "billing",
    K.PLAN_LIMIT: "billing",
    K.PAYMENT_RECORDED: "payments",
    K.PAYMENT_VOIDED: "payments",
    K.RECEIPT_ISSUED: "payments",
    K.ONLINE_PAYMENT_UNAPPLIED: "payments",
}


class NotificationService:
    @staticmethod
    def preferences_for(user):
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        return prefs

    @staticmethod
    def update_preferences(*, user, changes):
        prefs = NotificationService.preferences_for(user)
        for field in ("billing", "payments", "membership", "email_enabled"):
            if field in changes:
                setattr(prefs, field, bool(changes[field]))
        prefs.save()
        return prefs

    @staticmethod
    def notify(*, recipient, kind, title, body="", tenant=None, data=None, dedupe_key=None):
        """
        Create one in-app notification, inside the caller's transaction.

        Returns the Notification, or None when the recipient muted this
        category, is deactivated, or `dedupe_key` was already used for them (a
        reminder that has already been sent). The dedupe insert runs in its own
        savepoint so a collision never breaks the caller's transaction.
        """
        if recipient is None or not recipient.is_active:
            return None
        pref_field = PREFERENCE_FOR_KIND.get(kind)
        if pref_field is not None:
            prefs = NotificationPreference.objects.filter(user=recipient).first()
            if prefs is not None and not getattr(prefs, pref_field):
                return None
        try:
            with transaction.atomic():
                return Notification.objects.create(
                    recipient=recipient,
                    tenant=tenant,
                    kind=kind,
                    title=title[:255],
                    body=body[:1000],
                    data=data or {},
                    dedupe_key=dedupe_key,
                )
        except IntegrityError:
            return None

    @staticmethod
    def for_user(user):
        return Notification.objects.filter(recipient=user)

    @staticmethod
    def mark_read(*, user, ids=None, all_unread=False):
        qs = Notification.objects.filter(recipient=user, read_at__isnull=True)
        if not all_unread:
            qs = qs.filter(id__in=ids or [])
        return qs.update(read_at=timezone.now())

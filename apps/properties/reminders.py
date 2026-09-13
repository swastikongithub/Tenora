"""
Billing reminders (plan §25.2 / §43.6): due-soon, overdue, the owner's overdue
summary, and the incomplete-cycle nudge — all in-app.

Idempotent by construction: every notification carries a `dedupe_key`, and
`Notification(recipient, dedupe_key)` is unique, so running the sweep twice on
the same day (a manual trigger racing the scheduled task) notifies nobody
twice. A bill that moves into a later aging bucket gets one new reminder per
bucket, not one per run.

Entry points: `manage.py send_billing_reminders`, the Celery task
`properties.send_billing_reminders`, and the owner's "Send reminders" action
(scoped to their own workspace). Billing state is never changed here.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.properties import aging
from apps.properties.models import Bill, BillingCycle, Meter, MeterReading
from apps.tenants.models import Membership

DUE_SOON_DAYS = 3


@dataclass
class ReminderResult:
    due_soon: int = 0
    overdue: int = 0
    owner_summaries: int = 0
    cycle_incomplete: int = 0
    workspaces: set = field(default_factory=set)

    def as_dict(self):
        return {
            "due_soon": self.due_soon,
            "overdue": self.overdue,
            "owner_summaries": self.owner_summaries,
            "cycle_incomplete": self.cycle_incomplete,
        }


def _owners(tenant_id):
    return [
        m.user
        for m in Membership.objects.filter(
            tenant_id=tenant_id, role=Membership.Role.OWNER, status=Membership.Status.ACTIVE
        ).select_related("user")
    ]


def send_billing_reminders(*, today=None, tenant=None):
    today = today or aging.server_today()
    result = ReminderResult()
    bills = Bill.objects.filter(status__in=aging.OPEN_STATUSES).select_related(
        "resident__user", "tenant"
    )
    cycles = BillingCycle.objects.filter(status=BillingCycle.Status.OPEN, period_end__lt=today)
    if tenant is not None:
        bills = bills.filter(tenant=tenant)
        cycles = cycles.filter(tenant=tenant)

    overdue_by_tenant = {}
    for bill in bills:
        if not aging.is_open(bill):
            continue
        days = aging.overdue_days(bill, today)
        due = bill.total_cents - bill.amount_paid_cents
        if days == 0 and bill.due_date - today <= timedelta(days=DUE_SOON_DAYS):
            if NotificationService.notify(
                recipient=bill.resident.user,
                kind=Notification.Kind.BILL_DUE_SOON,
                tenant=bill.tenant,
                title=f"Your {bill.period_start:%B %Y} bill is due {bill.due_date:%d %b}",
                body=f"Unit {bill.unit_identifier}.",
                data={"bill_id": str(bill.id)},
                dedupe_key=f"due-soon:{bill.id}",
            ):
                result.due_soon += 1
        elif days > 0:
            bucket = aging.bucket_for_days(days)
            if NotificationService.notify(
                recipient=bill.resident.user,
                kind=Notification.Kind.BILL_OVERDUE,
                tenant=bill.tenant,
                title=f"Your {bill.period_start:%B %Y} bill is overdue",
                body=f"{days} day(s) past the due date.",
                data={"bill_id": str(bill.id), "overdue_days": days},
                dedupe_key=f"overdue:{bill.id}:{bucket}",
            ):
                result.overdue += 1
            entry = overdue_by_tenant.setdefault(bill.tenant_id, {"tenant": bill.tenant, "count": 0, "amount": 0})
            entry["count"] += 1
            entry["amount"] += due

    for tenant_id, entry in overdue_by_tenant.items():
        for owner in _owners(tenant_id):
            if NotificationService.notify(
                recipient=owner,
                kind=Notification.Kind.OVERDUE_SUMMARY,
                tenant=entry["tenant"],
                title=f"{entry['count']} overdue bill(s) in {entry['tenant'].name}",
                body="Open Billing → Aging to see who owes what.",
                data={"overdue_count": entry["count"], "overdue_cents": entry["amount"]},
                dedupe_key=f"overdue-summary:{tenant_id}:{today.isoformat()}",
            ):
                result.owner_summaries += 1

    for cycle in cycles.select_related("tenant"):
        drafts = cycle.bills.filter(status=Bill.Status.DRAFT).count()
        meters = Meter.objects.filter(tenant=cycle.tenant, is_active=True, unit__leases__status="ACTIVE").distinct()
        read = (
            MeterReading.objects.filter(
                meter__in=meters, reading_date__gte=cycle.period_start, reading_date__lte=cycle.period_end
            )
            .values("meter_id")
            .distinct()
            .count()
        )
        missing = meters.count() - read
        if drafts == 0 and missing <= 0:
            continue
        for owner in _owners(cycle.tenant_id):
            if NotificationService.notify(
                recipient=owner,
                kind=Notification.Kind.CYCLE_INCOMPLETE,
                tenant=cycle.tenant,
                title=f"{cycle.period_start:%B %Y} billing is incomplete",
                body=f"{max(missing, 0)} meter reading(s) missing, {drafts} draft bill(s) unpublished.",
                data={"cycle_id": str(cycle.id)},
                dedupe_key=f"cycle-incomplete:{cycle.id}:{today.isoformat()}",
            ):
                result.cycle_incomplete += 1
    return result

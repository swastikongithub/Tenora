"""
Billing aging (plan §43.2) — one deterministic rule used by every surface:
owner billing, resident bill detail, platform views, reports, and tests.

    open bill      = status PUBLISHED or PARTIALLY_PAID, with amount due > 0
    overdue_days   = max(0, today - due_date)   for an open bill, else 0
    bucket         = CURRENT (0) | 1_30 | 31_60 | 61_90 | 90_PLUS

`today` is the SERVER's date (`timezone.localdate()`, UTC per settings), passed
in explicitly so tests can pin it. The browser clock is never consulted.
"""

from django.utils import timezone

BUCKETS = ("CURRENT", "1_30", "31_60", "61_90", "90_PLUS")
BUCKET_LABELS = {
    "CURRENT": "Current",
    "1_30": "1–30 days",
    "31_60": "31–60 days",
    "61_90": "61–90 days",
    "90_PLUS": "90+ days",
}
OPEN_STATUSES = ("PUBLISHED", "PARTIALLY_PAID")


def server_today():
    return timezone.localdate()


def is_open(bill):
    return bill.status in OPEN_STATUSES and bill.total_cents - bill.amount_paid_cents > 0


def overdue_days(bill, today):
    if not is_open(bill):
        return 0
    return max((today - bill.due_date).days, 0)


def bucket_for_days(days):
    if days <= 0:
        return "CURRENT"
    if days <= 30:
        return "1_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "90_PLUS"


def display_status(bill, today):
    """The status a person should see: OVERDUE is derived, never stored."""
    if is_open(bill) and overdue_days(bill, today) > 0:
        return "OVERDUE"
    return bill.status


def aging_report(bills, today):
    """Bucket totals + per-bill rows for an iterable of bills (any scope)."""
    totals = {b: 0 for b in BUCKETS}
    counts = {b: 0 for b in BUCKETS}
    rows = []
    for bill in bills:
        if not is_open(bill):
            continue
        days = overdue_days(bill, today)
        bucket = bucket_for_days(days)
        due = bill.total_cents - bill.amount_paid_cents
        totals[bucket] += due
        counts[bucket] += 1
        rows.append((bill, days, bucket, due))
    rows.sort(key=lambda r: (-r[1], r[0].due_date))
    return {
        "total_outstanding_cents": sum(totals.values()),
        "total_overdue_cents": sum(v for k, v in totals.items() if k != "CURRENT"),
        "buckets": [
            {"key": b, "label": BUCKET_LABELS[b], "amount_cents": totals[b], "count": counts[b]}
            for b in BUCKETS
        ],
        "rows": rows,
    }

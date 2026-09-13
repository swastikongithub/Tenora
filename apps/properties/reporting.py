"""
Read models for property billing — every number here is derived from real bill,
payment, lease and reading rows at request time (plan §16 "Reporting": no cached
aggregate tables). Each function takes base querysets, so owner views pass
`...for_tenant(request.tenant)` and platform views pass cross-workspace
querysets: one definition of "billed", "collected" and "overdue" for both.

Definitions:
    issued bill   status PUBLISHED, PARTIALLY_PAID or PAID (never DRAFT/CANCELLED)
    billed        sum(total_cents) of issued bills in the period
    collected     sum(amount_paid_cents) of those bills
    outstanding   billed - collected
    overdue       outstanding on open bills past their due date (see aging.py)
"""

import calendar
from datetime import date

from django.db.models import Sum

from apps.properties import aging
from apps.properties.models import Bill, BillLineItem, Lease, Payment

ISSUED = ("PUBLISHED", "PARTIALLY_PAID", "PAID")


def month_start(d):
    return date(d.year, d.month, 1)


def shift_month(d, months):
    index = d.year * 12 + (d.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def period_from_param(value, today):
    """'YYYY-MM' -> (start, end); anything else -> the current month."""
    try:
        year, month = (int(p) for p in (value or "").split("-"))
        start = date(year, month, 1)
    except (ValueError, TypeError):
        start = month_start(today)
    return start, date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


def period_summary(bills_qs, period_start, today, residents_count=None):
    bills = list(
        bills_qs.filter(period_start=period_start, status__in=ISSUED).only(
            "id", "status", "total_cents", "amount_paid_cents", "due_date"
        )
    )
    billed = sum(b.total_cents for b in bills)
    collected = sum(b.amount_paid_cents for b in bills)
    overdue = sum(
        b.total_cents - b.amount_paid_cents for b in bills if aging.overdue_days(b, today) > 0
    )
    units = (
        BillLineItem.objects.filter(bill__in=[b.id for b in bills], type=BillLineItem.Type.ELECTRICITY)
        .aggregate(s=Sum("quantity"))["s"]
    )
    drafts = bills_qs.filter(period_start=period_start, status=Bill.Status.DRAFT).count()
    return {
        "period": period_start.strftime("%Y-%m"),
        "billed_cents": billed,
        "collected_cents": collected,
        "outstanding_cents": billed - collected,
        "overdue_cents": overdue,
        "residents": residents_count,
        "bills_issued": len(bills),
        "bills_draft": drafts,
        "bills_paid": sum(1 for b in bills if b.status == Bill.Status.PAID),
        "bills_unpaid": sum(1 for b in bills if b.status != Bill.Status.PAID),
        "electricity_units": str(units or 0),
    }


def aging_summary(bills_qs, today):
    open_bills = bills_qs.filter(status__in=aging.OPEN_STATUSES).select_related(
        "resident", "unit", "property"
    )
    return aging.aging_report(open_bills, today)


def monthly_series(bills_qs, payments_qs, today, months=12):
    """Billed / collected / outstanding / electricity per billing month, plus
    cash received per calendar month (payments by payment_date)."""
    first = shift_month(month_start(today), -(months - 1))
    rows = {}
    for m in range(months):
        start = shift_month(first, m)
        rows[start] = {
            "period": start.strftime("%Y-%m"),
            "billed_cents": 0,
            "collected_cents": 0,
            "outstanding_cents": 0,
            "rent_billed_cents": 0,
            "electricity_billed_cents": 0,
            "other_billed_cents": 0,
            "electricity_units": 0,
            "cash_received_cents": 0,
        }
    bills = bills_qs.filter(status__in=ISSUED, period_start__gte=first)
    for b in bills.only("period_start", "total_cents", "amount_paid_cents"):
        row = rows.get(b.period_start)
        if row is None:
            continue
        row["billed_cents"] += b.total_cents
        row["collected_cents"] += b.amount_paid_cents
        row["outstanding_cents"] += b.total_cents - b.amount_paid_cents
    lines = BillLineItem.objects.filter(bill__in=bills).values(
        "bill__period_start", "type", "amount_cents", "quantity"
    )
    for line in lines:
        row = rows.get(line["bill__period_start"])
        if row is None:
            continue
        if line["type"] == BillLineItem.Type.RENT:
            row["rent_billed_cents"] += line["amount_cents"]
        elif line["type"] == BillLineItem.Type.ELECTRICITY:
            row["electricity_billed_cents"] += line["amount_cents"]
            row["electricity_units"] += line["quantity"] or 0
        else:
            row["other_billed_cents"] += line["amount_cents"]
    for p in payments_qs.filter(status=Payment.Status.COMPLETED, payment_date__gte=first).only(
        "payment_date", "amount_cents"
    ):
        row = rows.get(month_start(p.payment_date))
        if row is not None:
            row["cash_received_cents"] += p.amount_cents
    out = list(rows.values())
    for row in out:
        row["electricity_units"] = str(row["electricity_units"])
    return out


def electricity_by_unit(bills_qs, period_start):
    totals = {}
    lines = (
        BillLineItem.objects.filter(
            bill__in=bills_qs.filter(status__in=ISSUED, period_start=period_start),
            type=BillLineItem.Type.ELECTRICITY,
        )
        .select_related("bill")
        .order_by("bill__property_name", "bill__unit_identifier")
    )
    for line in lines:
        key = (line.bill.property_name, line.bill.unit_identifier)
        row = totals.setdefault(
            key,
            {"property_name": key[0], "unit_identifier": key[1], "units": 0, "amount_cents": 0},
        )
        row["units"] += line.quantity or 0
        row["amount_cents"] += line.amount_cents
    out = list(totals.values())
    for row in out:
        row["units"] = str(row["units"])
    return out


def occupancy(units_qs, tenant_lease_qs):
    total = units_qs.exclude(status="INACTIVE").count()
    occupied = tenant_lease_qs.filter(status=Lease.Status.ACTIVE).values("unit_id").distinct().count()
    return {"units": total, "occupied_units": occupied}

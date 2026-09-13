"""
Bill / payment / receipt list filters, shared by the owner views and the
platform-admin views so both accept the same query parameters with the same
meaning. A malformed value narrows to nothing rather than erroring (the same
rule apps.platform.utils.parse_uuid_or_none applies to platform filters).
"""

from datetime import timedelta

from django.db.models import Q

from apps.platform.utils import parse_uuid_or_none
from apps.properties import aging
from apps.properties.reporting import period_from_param

BILL_STATUSES = {"DRAFT", "PUBLISHED", "PARTIALLY_PAID", "PAID", "CANCELLED"}
AGING_RANGES = {"1_30": (1, 30), "31_60": (31, 60), "61_90": (61, 90), "90_PLUS": (91, None)}


def _uuid_filter(qs, params, param, field):
    raw = params.get(param)
    if not raw:
        return qs
    value = parse_uuid_or_none(raw)
    return qs.filter(**{field: value}) if value else qs.none()


def filter_bills(qs, params, today):
    for param, field in (
        ("tenant", "tenant_id"),
        ("property", "property_id"),
        ("unit", "unit_id"),
        ("resident", "resident_id"),
        ("cycle", "cycle_id"),
    ):
        qs = _uuid_filter(qs, params, param, field)

    period = params.get("period")
    if period:
        start, _ = period_from_param(period, today)
        qs = qs.filter(period_start=start) if start.strftime("%Y-%m") == period else qs.none()

    status = params.get("status")
    if status == "OVERDUE":
        qs = qs.filter(status__in=aging.OPEN_STATUSES, due_date__lt=today)
    elif status == "UNPAID":
        qs = qs.filter(status__in=aging.OPEN_STATUSES)
    elif status in BILL_STATUSES:
        qs = qs.filter(status=status)
    elif status:
        qs = qs.none()

    payment_status = params.get("payment_status")
    if payment_status == "PAID":
        qs = qs.filter(status="PAID")
    elif payment_status == "PARTIALLY_PAID":
        qs = qs.filter(status="PARTIALLY_PAID")
    elif payment_status == "UNPAID":
        qs = qs.filter(status="PUBLISHED")
    elif payment_status:
        qs = qs.none()

    overdue = params.get("overdue")
    if overdue in ("1", "true"):
        qs = qs.filter(status__in=aging.OPEN_STATUSES, due_date__lt=today)
    elif overdue in ("0", "false"):
        qs = qs.exclude(status__in=aging.OPEN_STATUSES, due_date__lt=today)

    bucket = params.get("aging")
    if bucket == "CURRENT":
        qs = qs.filter(status__in=aging.OPEN_STATUSES, due_date__gte=today)
    elif bucket in AGING_RANGES:
        low, high = AGING_RANGES[bucket]
        qs = qs.filter(status__in=aging.OPEN_STATUSES, due_date__lte=today - timedelta(days=low))
        if high is not None:
            qs = qs.filter(due_date__gte=today - timedelta(days=high))
    elif bucket:
        qs = qs.none()

    search = (params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(resident_name__icontains=search)
            | Q(unit_identifier__icontains=search)
            | Q(bill_number__icontains=search)
            | Q(property_name__icontains=search)
        )
    return qs


def filter_payments(qs, params):
    for param, field in (
        ("tenant", "tenant_id"),
        ("bill", "bill_id"),
        ("resident", "resident_id"),
        ("property", "bill__property_id"),
    ):
        qs = _uuid_filter(qs, params, param, field)
    status = params.get("status")
    if status in ("COMPLETED", "VOIDED"):
        qs = qs.filter(status=status)
    elif status:
        qs = qs.none()
    method = params.get("method")
    if method:
        qs = qs.filter(method=method)
    search = (params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(bill__resident_name__icontains=search)
            | Q(reference__icontains=search)
            | Q(bill__bill_number__icontains=search)
        )
    return qs


def filter_receipts(qs, params):
    for param, field in (
        ("tenant", "tenant_id"),
        ("bill", "bill_id"),
        ("resident", "bill__resident_id"),
        ("property", "bill__property_id"),
    ):
        qs = _uuid_filter(qs, params, param, field)
    search = (params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(receipt_number__icontains=search) | Q(resident_name__icontains=search)
        )
    return qs

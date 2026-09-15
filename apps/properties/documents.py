"""
PDF bills and receipts (plan §26, Phase P10).

Rendering only. Every financial figure printed here is read from what the bill
already stores — its snapshot columns (names, totals, amount paid), its line
items (rent, readings, multiplier, units, rate, amount), its correction rows,
its payments and the receipt's own snapshot columns. Nothing is recalculated
from the current lease, tariff, meter or resident, so a PDF downloaded next year
shows exactly what was issued, plus any audited corrections and payments since.

The issuer block (workspace display name and contact details) is the one piece
read from current `WorkspaceSettings`, the same as the web receipt: it is
contact information, not an amount.

Amounts print as "INR 13,780.00": the standard PDF fonts have no rupee glyph,
and embedding a font for one character is not worth a binary asset. The
document is generated with `invariant=1` (no creation timestamp or random id),
so the same stored data always produces the same bytes.
"""

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.properties.models import Bill, BillLineItem, Payment

_STYLES = getSampleStyleSheet()
TITLE = ParagraphStyle("TenoraTitle", parent=_STYLES["Title"], alignment=0, fontSize=18, spaceAfter=2)
HEADING = ParagraphStyle("TenoraHeading", parent=_STYLES["Heading3"], spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("TenoraBody", parent=_STYLES["BodyText"], fontSize=9.5, leading=12)
SMALL = ParagraphStyle("TenoraSmall", parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor("#555555"))

# Column widths below sum to 174mm: A4 (210mm) minus the 18mm side margins.
GRID = TableStyle(
    [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#333333")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
)


def money(cents, currency):
    """Integer minor units -> "INR 13,780.00" (negative as "-INR 50.00").
    Pure integer arithmetic: no float ever touches an amount."""
    cents = int(cents)
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    return f"{sign}{currency} {whole:,}.{fraction:02d}"


def rate(minor_per_unit, currency):
    """A Decimal rate in minor units per unit -> "INR 8.00"; keeps up to four
    significant decimals of a fractional paisa rate without rounding it."""
    major = minor_per_unit / 100
    text = f"{major:,.6f}".rstrip("0")
    whole, _, frac = text.partition(".")
    return f"{currency} {whole}.{frac.ljust(2, '0')}"


def decimal(value):
    return f"{value:,.3f}" if value is not None else "-"


def day(value):
    return value.strftime("%d %b %Y") if value else "-"


def _p(text, style=BODY):
    return Paragraph(escape(str(text)), style)


def _key_values(rows):
    table = Table([[_p(k, SMALL), _p(v)] for k, v in rows], colWidths=[35 * mm, 139 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _issuer_block(issuer):
    lines = [issuer["name"]]
    lines += [issuer[k] for k in ("address", "contact_email", "contact_phone") if issuer.get(k)]
    return [_p(line, SMALL) for line in lines]


def _build(story, title):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title,
        author="Tenora",
        invariant=1,
    )
    doc.build(story)
    return buffer.getvalue()


def _line_details(line, currency):
    if line.type == BillLineItem.Type.ELECTRICITY and line.closing_reading_value is not None:
        parts = [
            f"Meter {line.meter_number}" if line.meter_number else "Meter",
            f"{decimal(line.opening_reading_value)} ({day(line.opening_reading_date)}) to "
            f"{decimal(line.closing_reading_value)} ({day(line.closing_reading_date)})",
        ]
        if line.multiplier is not None and line.multiplier != 1:
            parts.append(f"multiplier x{line.multiplier.normalize()}")
        if line.quantity is not None:
            parts.append(f"{decimal(line.quantity)} units")
        if line.unit_price_cents is not None:
            parts.append(f"at {rate(line.unit_price_cents, currency)}/unit")
        return "; ".join(parts)
    if line.quantity is not None and line.unit_price_cents is not None and line.quantity != 1:
        return f"{decimal(line.quantity)} x {rate(line.unit_price_cents, currency)}"
    return ""


def render_bill_pdf(bill, issuer):
    """`bill` must be issued (published_at set) and fetched with its line items,
    payments and corrections; `issuer` is the dict the receipt view builds."""
    currency = bill.currency
    status = Bill.Status(bill.status).label
    story = [
        *_issuer_block(issuer),
        Spacer(1, 6 * mm),
        _p(f"Bill {bill.bill_number}", TITLE),
        _p(f"{bill.period_start:%B %Y} - {status}", BODY),
        Spacer(1, 4 * mm),
        _key_values(
            [
                ("Billed to", bill.resident_name),
                ("Email", bill.resident_email),
                ("Property", bill.property_name),
                ("Unit", bill.unit_identifier),
                ("Billing period", f"{day(bill.period_start)} to {day(bill.period_end)}"),
                ("Issued", day(bill.published_at.date()) if bill.published_at else "-"),
                ("Due date", day(bill.due_date)),
            ]
        ),
        _p("Charges", HEADING),
    ]

    rows = [["Item", "Details", "Amount"]]
    for line in bill.line_items.all():
        rows.append(
            [
                _p(line.description or BillLineItem.Type(line.type).label),
                _p(_line_details(line, currency), SMALL),
                money(line.amount_cents, currency),
            ]
        )
    charges = Table(rows, colWidths=[50 * mm, 92 * mm, 32 * mm], repeatRows=1)
    charges.setStyle(GRID)
    story.append(charges)

    totals = [
        ("Subtotal", bill.subtotal_cents),
        ("Adjustments and discounts", bill.adjustments_cents),
        ("Total", bill.total_cents),
        ("Paid", bill.amount_paid_cents),
        ("Amount due", bill.amount_due_cents),
    ]
    totals_table = Table(
        [[label, money(value, currency)] for label, value in totals],
        colWidths=[60 * mm, 40 * mm],
        hAlign="RIGHT",
    )
    totals_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9.5),
                ("FONT", (0, 2), (-1, 2), "Helvetica-Bold", 10),
                ("FONT", (0, 4), (-1, 4), "Helvetica-Bold", 10),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("LINEABOVE", (0, 2), (-1, 2), 0.6, colors.HexColor("#333333")),
            ]
        )
    )
    story += [Spacer(1, 2 * mm), totals_table]

    payments = list(bill.payments.all())
    if payments:
        story.append(_p("Payments", HEADING))
        rows = [["Date", "Method", "Receipt", "Amount"]]
        for payment in payments:
            receipt = getattr(payment, "receipt", None)
            voided = payment.status == Payment.Status.VOIDED
            rows.append(
                [
                    day(payment.payment_date),
                    Payment.Method(payment.method).label + (" (voided)" if voided else ""),
                    receipt.receipt_number if receipt else "-",
                    money(payment.amount_cents, payment.currency),
                ]
            )
        table = Table(rows, colWidths=[30 * mm, 50 * mm, 62 * mm, 32 * mm], repeatRows=1)
        table.setStyle(GRID)
        story.append(table)

    corrections = list(bill.corrections.all())
    if corrections:
        story.append(_p("Corrections", HEADING))
        rows = [["Date", "Reason", "Change"]]
        for correction in corrections:
            rows.append(
                [
                    day(correction.created_at.date()),
                    _p(correction.reason, SMALL),
                    money(correction.amount_delta_cents, currency),
                ]
            )
        table = Table(rows, colWidths=[30 * mm, 112 * mm, 32 * mm], repeatRows=1)
        table.setStyle(GRID)
        story.append(table)

    if bill.status == Bill.Status.CANCELLED:
        story += [Spacer(1, 4 * mm), _p(f"This bill was cancelled. {bill.cancellation_reason}".strip())]

    story += [
        Spacer(1, 8 * mm),
        _p("Amounts are shown as issued, including any recorded corrections and payments.", SMALL),
    ]
    if issuer.get("footer"):
        story.append(_p(issuer["footer"], SMALL))
    return _build(story, f"Bill {bill.bill_number}")


def render_receipt_pdf(receipt, issuer):
    """`receipt` fetched with its payment."""
    payment = receipt.payment
    story = [
        *_issuer_block(issuer),
        Spacer(1, 6 * mm),
        _p(f"Receipt {receipt.receipt_number}", TITLE),
        Spacer(1, 4 * mm),
        _key_values(
            [
                ("Received from", receipt.resident_name),
                ("Amount", money(receipt.amount_cents, receipt.currency)),
                ("Method", Payment.Method(receipt.payment_method).label),
                ("Payment date", day(payment.payment_date)),
                ("Reference", payment.reference or "-"),
                ("For bill", receipt.bill_number or "-"),
                ("Property", receipt.property_name),
                ("Unit", receipt.unit_identifier),
                ("Issued", day(receipt.issued_at.date())),
            ]
        ),
    ]
    if payment.status == Payment.Status.VOIDED:
        story += [
            Spacer(1, 4 * mm),
            _p(f"This payment was voided on {day(payment.voided_at.date() if payment.voided_at else None)}. "
               f"{payment.void_reason}".strip()),
        ]
    story += [Spacer(1, 8 * mm), _p("Thank you for your payment.", BODY)]
    if issuer.get("footer"):
        story.append(_p(issuer["footer"], SMALL))
    return _build(story, f"Receipt {receipt.receipt_number}")

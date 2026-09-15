"""PDF bills and receipts: who may download them, and that they print the bill
as issued — never a recalculation from current lease, tariff or meter data."""

import base64
import re
import zlib
from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.properties.documents import money, rate
from apps.properties.services import BillCorrectionService, LeaseService, PaymentService, TariffService
from apps.properties.tests.factories import Scenario, add_resident, bearer


def pdf_text(content):
    """The text-drawing operators of every page stream, decoded (reportlab
    writes ASCII85 + Flate streams)."""
    chunks = []
    for match in re.finditer(rb"<<([^<>]*)>>\s*stream\r?\n(.*?)endstream", content, re.S):
        head, body = match.group(1), match.group(2).strip()
        if b"ASCII85Decode" in head:
            body = base64.a85decode(body[:-2] if body.endswith(b"~>") else body)
        if b"FlateDecode" in head:
            body = zlib.decompress(body)
        chunks.append(body)
    return b"\n".join(chunks).decode("latin-1")


class FormattingTests(APITestCase):
    def test_money_uses_integer_minor_units(self):
        self.assertEqual(money(1_378_000, "INR"), "INR 13,780.00")
        self.assertEqual(money(5, "INR"), "INR 0.05")
        self.assertEqual(money(-50_000, "INR"), "-INR 500.00")

    def test_rate_keeps_fractional_paisa(self):
        self.assertEqual(rate(Decimal("800"), "INR"), "INR 8.00")
        self.assertEqual(rate(Decimal("812.5000"), "INR"), "INR 8.125")
        self.assertEqual(rate(Decimal("0.0100"), "INR"), "INR 0.0001")


class BillPdfTests(APITestCase):
    def setUp(self):
        self.a = Scenario(slug="sunrise")
        self.bill = self.a.march_bill()
        self.payment, _ = self.a.pay(self.bill, 378_000, reference="UPI-778")
        self.receipt = self.payment.receipt

    def get(self, url):
        return self.client.get(url)

    def test_owner_downloads_the_issued_bill(self):
        bearer(self.client, self.a.owner, self.a.tenant)
        resp = self.get(f"/api/bills/{self.bill.id}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertEqual(resp["Content-Disposition"], f'attachment; filename="{self.bill.bill_number}.pdf"')
        self.assertEqual(resp["Cache-Control"], "private, no-store")
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        self.assertTrue(resp.content.startswith(b"%PDF-"))
        text = pdf_text(resp.content)
        for expected in (
            self.bill.bill_number,
            "INR 12,000.00",  # rent
            "INR 1,280.00",  # 160 units x INR 8
            "INR 500.00",  # maintenance
            "INR 13,780.00",  # total
            "INR 3,780.00",  # paid
            "INR 10,000.00",  # due
            "12,450.000",
            "12,610.000",
            self.receipt.receipt_number,
        ):
            self.assertIn(expected, text)

    def test_accept_header_for_pdf_is_honoured(self):
        bearer(self.client, self.a.owner, self.a.tenant)
        resp = self.client.get(f"/api/bills/{self.bill.id}/pdf/", HTTP_ACCEPT="application/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF-"))

    def test_the_resident_downloads_their_own_bill_and_receipt(self):
        bearer(self.client, self.a.user, self.a.tenant)
        self.assertEqual(self.get(f"/api/bills/{self.bill.id}/pdf/").status_code, 200)
        receipt = self.get(f"/api/receipts/{self.receipt.id}/pdf/")
        self.assertEqual(receipt.status_code, 200)
        text = pdf_text(receipt.content)
        for expected in (self.receipt.receipt_number, "INR 3,780.00", "UPI-778", self.bill.bill_number):
            self.assertIn(expected, text)

    def test_another_resident_in_the_same_workspace_gets_404(self):
        other, _ = add_resident(self.a.tenant, self.a.owner, "priya@example.com", first_name="Priya")
        bearer(self.client, other, self.a.tenant)
        self.assertEqual(self.get(f"/api/bills/{self.bill.id}/pdf/").status_code, 404)
        self.assertEqual(self.get(f"/api/receipts/{self.receipt.id}/pdf/").status_code, 404)

    def test_another_workspace_gets_404(self):
        b = Scenario(slug="green-valley")
        bearer(self.client, b.owner, b.tenant)
        self.assertEqual(self.get(f"/api/bills/{self.bill.id}/pdf/").status_code, 404)
        self.assertEqual(self.get(f"/api/receipts/{self.receipt.id}/pdf/").status_code, 404)

    def test_unauthenticated_is_refused(self):
        resp = self.client.get(f"/api/bills/{self.bill.id}/pdf/", HTTP_X_TENANT_ID=str(self.a.tenant.id))
        self.assertEqual(resp.status_code, 401)

    def test_a_draft_has_no_pdf(self):
        b = Scenario(slug="draft-valley")
        draft = b.march_bill(publish=False)
        bearer(self.client, b.owner, b.tenant)
        resp = self.get(f"/api/bills/{draft.id}/pdf/")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "BILL_NOT_ISSUED")
        bearer(self.client, b.user, b.tenant)
        self.assertEqual(self.get(f"/api/bills/{draft.id}/pdf/").status_code, 404)

    def test_later_rent_and_tariff_changes_do_not_change_the_issued_bill(self):
        bearer(self.client, self.a.owner, self.a.tenant)
        before = self.get(f"/api/bills/{self.bill.id}/pdf/").content

        LeaseService.update(actor=self.a.owner, lease=self.a.lease, changes={"monthly_rent_cents": 1_300_000})
        TariffService.create(
            actor=self.a.owner, tenant=self.a.tenant, rate_per_unit_cents=Decimal("1000"), effective_from=date(2026, 3, 1)
        )
        after = self.get(f"/api/bills/{self.bill.id}/pdf/").content
        self.assertEqual(before, after)
        self.assertNotIn("INR 13,000.00", pdf_text(after))

    def test_corrections_and_voided_payments_are_shown_not_hidden(self):
        BillCorrectionService.adjust_amount(
            actor=self.a.owner, bill=self.bill, amount_delta_cents=-50_000, reason="Maintenance waived for March"
        )
        PaymentService.void(actor=self.a.owner, payment=self.payment, reason="Bounced")
        bearer(self.client, self.a.owner, self.a.tenant)
        text = pdf_text(self.get(f"/api/bills/{self.bill.id}/pdf/").content)
        self.assertIn("Maintenance waived for March", text)
        self.assertIn("-INR 500.00", text)
        self.assertIn("INR 13,280.00", text)  # corrected total
        self.assertIn("\\(voided\\)", text)
        receipt_text = pdf_text(self.get(f"/api/receipts/{self.receipt.id}/pdf/").content)
        self.assertIn("voided", receipt_text)

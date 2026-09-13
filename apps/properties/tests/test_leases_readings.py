import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from apps.properties.models import Lease, MeterReadingCorrection, Unit
from apps.properties.services import (
    DomainError,
    LeaseService,
    MeterReadingService,
    UnitService,
)
from apps.properties.tests.factories import Scenario, add_resident, bearer

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

MEDIA = tempfile.mkdtemp(prefix="tenora-test-media-")


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


class LeaseTests(TestCase):
    def test_active_lease_marks_unit_occupied_and_blocks_overlap(self):
        s = Scenario()
        s.unit.refresh_from_db()
        self.assertEqual(s.unit.status, Unit.Status.OCCUPIED)
        _, other = add_resident(s.tenant, s.owner, "aman@example.com")
        with self.assertRaises(DomainError) as ctx:
            LeaseService.create(
                actor=s.owner, tenant=s.tenant, unit=s.unit, resident=other,
                start_date=date(2026, 6, 1), monthly_rent_cents=1,
            )
        self.assertEqual(ctx.exception.code, "LEASE_OVERLAP")

    def test_ending_lease_frees_unit_for_a_non_overlapping_lease(self):
        s = Scenario()
        LeaseService.end(actor=s.owner, lease=s.lease, end_date=date(2026, 5, 31))
        s.unit.refresh_from_db()
        self.assertEqual(s.unit.status, Unit.Status.VACANT)
        _, other = add_resident(s.tenant, s.owner, "aman@example.com")
        with self.assertRaises(DomainError):
            LeaseService.create(
                actor=s.owner, tenant=s.tenant, unit=s.unit, resident=other,
                start_date=date(2026, 5, 15), monthly_rent_cents=1,
            )
        lease = LeaseService.create(
            actor=s.owner, tenant=s.tenant, unit=s.unit, resident=other,
            start_date=date(2026, 6, 1), monthly_rent_cents=1,
        )
        self.assertEqual(lease.status, Lease.Status.ACTIVE)

    def test_inactive_resident_cannot_get_lease(self):
        s = Scenario()
        s.resident.status = "INACTIVE"
        s.resident.save()
        unit2 = UnitService.create(actor=s.owner, tenant=s.tenant, prop=s.property, identifier="204")
        with self.assertRaises(DomainError) as ctx:
            LeaseService.create(
                actor=s.owner, tenant=s.tenant, unit=unit2, resident=s.resident,
                start_date=date(2026, 1, 1), monthly_rent_cents=1,
            )
        self.assertEqual(ctx.exception.code, "RESIDENT_INACTIVE")

    def test_duplicate_unit_identifier_in_property(self):
        s = Scenario()
        with self.assertRaises(DomainError) as ctx:
            UnitService.create(actor=s.owner, tenant=s.tenant, prop=s.property, identifier="203")
        self.assertEqual(ctx.exception.code, "DUPLICATE_UNIT")


class MeterReadingTests(APITestCase):
    def test_chronology_is_enforced_both_ways(self):
        s = Scenario()
        s.reading(date(2026, 2, 1), "100")
        s.reading(date(2026, 4, 1), "300")
        with self.assertRaises(DomainError) as ctx:
            s.reading(date(2026, 3, 1), "50")
        self.assertEqual(ctx.exception.code, "READING_BELOW_PREVIOUS")
        with self.assertRaises(DomainError) as ctx:
            s.reading(date(2026, 3, 1), "400")
        self.assertEqual(ctx.exception.code, "READING_ABOVE_NEXT")
        s.reading(date(2026, 3, 1), "200")

    def test_duplicate_reading_same_day(self):
        s = Scenario()
        s.reading(date(2026, 2, 1), "100")
        with self.assertRaises(DomainError) as ctx:
            s.reading(date(2026, 2, 1), "100")
        self.assertEqual(ctx.exception.code, "DUPLICATE_READING")

    def test_future_reading_refused(self):
        s = Scenario()
        with self.assertRaises(DomainError):
            s.reading(date(2099, 1, 1), "1")

    def test_correction_preserves_original_and_reports_affected_bills(self):
        s = Scenario()
        bill = s.march_bill()
        closing = bill.line_items.get(type="ELECTRICITY").closing_reading
        correction, affected = MeterReadingService.correct(
            actor=s.owner, reading=closing, corrected_value=Decimal("12600"), reason="Typo"
        )
        self.assertEqual(correction.original_value, Decimal("12610"))
        self.assertEqual(MeterReadingCorrection.objects.count(), 1)
        self.assertEqual([b.id for b in affected], [bill.id])
        bill.refresh_from_db()
        self.assertEqual(bill.total_cents, 1_378_000)  # the issued bill is unchanged

    @override_settings(MEDIA_ROOT=MEDIA)
    def test_proof_type_is_sniffed_not_trusted(self):
        s = Scenario()
        fake = SimpleUploadedFile("meter.png", b"<script>alert(1)</script>", content_type="image/png")
        with self.assertRaises(DomainError) as ctx:
            MeterReadingService.record(
                actor=s.owner, tenant=s.tenant, meter=s.meter, reading_date=date(2026, 2, 1),
                reading_value=Decimal("1"), proof=fake,
            )
        self.assertEqual(ctx.exception.code, "PROOF_TYPE_UNSUPPORTED")

    @override_settings(MEDIA_ROOT=MEDIA)
    def test_proof_upload_and_authorized_download(self):
        s = Scenario()
        bearer(self.client, s.owner, s.tenant)
        resp = self.client.post(
            "/api/meter-readings/",
            {
                "meter_id": str(s.meter.id),
                "reading_date": "2026-02-28",
                "reading_value": "12450",
                "proof": SimpleUploadedFile("x.png", PNG, content_type="application/octet-stream"),
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertTrue(resp.data["has_proof"])
        self.assertEqual(resp.data["proof_content_type"], "image/png")
        proof = self.client.get(f"/api/meter-readings/{resp.data['id']}/proof/")
        self.assertEqual(proof.status_code, 200)
        self.assertEqual(proof["Content-Type"], "image/png")
        self.assertEqual(b"".join(proof.streaming_content), PNG)

        # The resident can see proof only for readings on their own published bill.
        s.reading(date(2026, 3, 31), "12610")
        bearer(self.client, s.user, s.tenant)
        self.assertEqual(self.client.get(f"/api/meter-readings/{resp.data['id']}/proof/").status_code, 404)
        from apps.properties.services import BillingCycleService, BillService

        created, _ = BillingCycleService.generate(actor=s.owner, cycle=s.cycle())
        BillService.publish(actor=s.owner, bill=created[0])
        self.assertEqual(self.client.get(f"/api/meter-readings/{resp.data['id']}/proof/").status_code, 200)

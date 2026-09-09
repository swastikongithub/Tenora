"""
`manage.py sync_razorpay_plans` and `PlanSyncService.sync_plan` — the domain
orchestration only (check-then-create, local write-back, idempotency). The
gateway call is mocked at the `get_gateway` seam; the actual request the
Razorpay adapter builds is covered in `test_gateway_razorpay.py`.
"""

import itertools
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.billing.gateway import PaymentGatewayAdapter
from apps.billing.models import Plan
from apps.billing.services import PlanSyncService


def _gateway():
    """A mock adapter whose create_plan hands back a fresh unique id per call —
    mirroring a real gateway (and Plan.external_plan_id is unique)."""
    gw = mock.Mock(spec=PaymentGatewayAdapter)
    counter = itertools.count(1)
    gw.create_plan.side_effect = lambda plan: f"ext_plan_{next(counter):04d}"
    return gw


class PlanSyncTests(TestCase):
    def setUp(self):
        self.pro = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD",
            interval=Plan.Interval.MONTHLY,
        )
        self.team = Plan.objects.create(
            name="Team", code="TEAM", price_cents=9900, currency="USD",
            interval=Plan.Interval.ANNUAL,
        )

    @mock.patch("apps.billing.services.get_gateway")
    def test_creates_a_gateway_plan_for_each_unmapped_plan(self, get_gateway):
        get_gateway.return_value = _gateway()

        call_command("sync_razorpay_plans")

        self.pro.refresh_from_db()
        self.team.refresh_from_db()
        self.assertTrue(self.pro.external_plan_id.startswith("ext_plan_"))
        self.assertTrue(self.team.external_plan_id.startswith("ext_plan_"))
        self.assertNotEqual(self.pro.external_plan_id, self.team.external_plan_id)
        self.assertEqual(get_gateway.return_value.create_plan.call_count, 2)

    @mock.patch("apps.billing.services.get_gateway")
    def test_sync_plan_passes_the_plan_to_the_adapter_and_stores_the_id(
        self, get_gateway
    ):
        get_gateway.return_value = _gateway()

        result = PlanSyncService.sync_plan(self.pro)

        get_gateway.return_value.create_plan.assert_called_once_with(self.pro)
        self.pro.refresh_from_db()
        self.assertEqual(self.pro.external_plan_id, result)

    @mock.patch("apps.billing.services.get_gateway")
    def test_running_twice_does_not_create_duplicates(self, get_gateway):
        get_gateway.return_value = _gateway()

        call_command("sync_razorpay_plans")
        after_first = get_gateway.return_value.create_plan.call_count

        call_command("sync_razorpay_plans")  # everything already mapped

        self.assertEqual(after_first, 2)
        self.assertEqual(get_gateway.return_value.create_plan.call_count, 2)
        self.assertEqual(
            Plan.objects.exclude(external_plan_id__isnull=True).count(), 2
        )

    @mock.patch("apps.billing.services.get_gateway")
    def test_sync_plan_is_a_noop_when_already_mapped(self, get_gateway):
        self.pro.external_plan_id = "ext_plan_EXISTING"
        self.pro.save(update_fields=["external_plan_id"])

        result = PlanSyncService.sync_plan(self.pro)

        self.assertEqual(result, "ext_plan_EXISTING")
        get_gateway.assert_not_called()

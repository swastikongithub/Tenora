"""
Stage D6 — mid-cycle plan-change proration (docs/stage-d6-spec.md §9).

`ProrationService.calculate` is pure math (hand-checked expected values).
`ProrationService.record_for_plan_change` is a best-effort, never-raising audit
step wired into `SubscriptionService.change_plan` — a calculation or DB failure
must not block the plan swap. Nothing here charges, refunds, or calls a gateway.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from fractions import Fraction
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan, ProrationRecord, Subscription
from apps.billing.services import (
    IllegalStateTransition,
    ProrationResult,
    ProrationService,
    SubscriptionService,
)
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

START = datetime(2027, 1, 1, tzinfo=dt_timezone.utc)
THIRTY_DAYS = timedelta(days=30)
END = START + THIRTY_DAYS


def _calc(from_cents, to_cents, now, *, start=START, end=END, currency="USD"):
    return ProrationService.calculate(
        from_price_cents=from_cents,
        to_price_cents=to_cents,
        currency=currency,
        period_start=start,
        period_end=end,
        now=now,
    )


class ProrationCalculateTests(TestCase):
    def test_upgrade_mid_cycle(self):
        # 1/3 of the period elapsed → 2/3 remaining. (9900-2900)*2/3 = 4666.67.
        result = _calc(2900, 9900, START + timedelta(days=10))
        self.assertEqual(result.fraction_remaining, Fraction(2, 3))
        self.assertEqual(result.net_amount_cents, 4667)  # away from zero
        self.assertEqual(result.currency, "USD")
        self.assertEqual(result.calculated_at, START + timedelta(days=10))

    def test_downgrade_mid_cycle(self):
        result = _calc(9900, 2900, START + timedelta(days=10))
        self.assertEqual(result.net_amount_cents, -4667)

    def test_change_on_the_day_the_period_starts_is_the_full_delta(self):
        self.assertEqual(_calc(2900, 9900, START).net_amount_cents, 7000)
        self.assertEqual(_calc(9900, 2900, START).net_amount_cents, -7000)
        self.assertEqual(_calc(2900, 9900, START).fraction_remaining, Fraction(1))

    def test_last_day_is_near_zero_but_correctly_signed(self):
        near_end = END - timedelta(minutes=6)  # 1/7200 of a 30-day period
        self.assertEqual(_calc(2900, 9900, near_end).net_amount_cents, 1)
        self.assertEqual(_calc(9900, 2900, near_end).net_amount_cents, -1)

    def test_same_price_is_exactly_zero_at_any_instant(self):
        for offset in (timedelta(0), timedelta(days=15), END - START):
            self.assertEqual(
                _calc(2900, 2900, START + offset).net_amount_cents, 0
            )

    def test_now_past_period_end_clamps_to_zero(self):
        result = _calc(2900, 9900, END + timedelta(days=3))
        self.assertEqual(result.fraction_remaining, Fraction(0))
        self.assertEqual(result.net_amount_cents, 0)

    def test_now_before_period_start_is_the_full_delta(self):
        result = _calc(2900, 9900, START - timedelta(days=2))
        self.assertEqual(result.fraction_remaining, Fraction(1))
        self.assertEqual(result.net_amount_cents, 7000)

    def test_degenerate_period_raises_invalid_period(self):
        with self.assertRaises(ProrationService.InvalidPeriod):
            _calc(2900, 9900, START, start=START, end=START)

    def test_half_cent_tie_rounds_away_from_zero(self):
        # 4-day period, 1 day remaining → 1/4. Delta ±2 → net exactly ±0.5.
        four_day_end = START + timedelta(days=4)
        one_left = four_day_end - timedelta(days=1)
        up = _calc(1000, 1002, one_left, start=START, end=four_day_end)
        down = _calc(1002, 1000, one_left, start=START, end=four_day_end)
        self.assertEqual(up.net_amount_cents, 1)
        self.assertEqual(down.net_amount_cents, -1)


class ProrationRecordTestBase(TestCase):
    def setUp(self):
        self.pro = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        self.team = Plan.objects.create(
            name="Team", code="TEAM", price_cents=9900, currency="USD"
        )
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.sub = Subscription.objects.create(
            tenant=self.tenant, plan=self.pro,
            status=Subscription.Status.ACTIVE,
            current_period_start=START, current_period_end=END,
        )


class RecordForPlanChangeTests(ProrationRecordTestBase):
    def test_records_one_row_matching_the_calculation(self):
        now = START + timedelta(days=10)

        record = ProrationService.record_for_plan_change(
            self.sub, self.pro, self.team, now=now
        )

        self.assertEqual(ProrationRecord.objects.count(), 1)
        self.assertEqual(record.tenant_id, self.tenant.id)
        self.assertEqual(record.subscription_id, self.sub.id)
        self.assertEqual(record.from_plan_id, self.pro.id)
        self.assertEqual(record.to_plan_id, self.team.id)
        self.assertEqual(record.period_start, START)
        self.assertEqual(record.period_end, END)
        self.assertEqual(record.calculated_at, now)
        self.assertEqual(record.currency, "USD")
        self.assertEqual(record.amount_cents, 4667)

    def test_now_defaults_to_timezone_now(self):
        before = timezone.now()
        record = ProrationService.record_for_plan_change(
            self.sub, self.pro, self.team
        )
        self.assertGreaterEqual(record.calculated_at, before)
        self.assertLessEqual(record.calculated_at, timezone.now())

    def test_same_plan_records_nothing(self):
        with self.assertLogs("apps.billing.services", level="INFO") as logs:
            result = ProrationService.record_for_plan_change(
                self.sub, self.pro, self.pro, now=START + timedelta(days=5)
            )
        self.assertIsNone(result)
        self.assertEqual(ProrationRecord.objects.count(), 0)
        self.assertTrue(any("same plan" in m for m in logs.output))

    def test_different_plans_same_price_records_a_zero_row(self):
        pro_clone = Plan.objects.create(
            name="Pro (clone)", code="PRO2", price_cents=2900, currency="USD"
        )

        record = ProrationService.record_for_plan_change(
            self.sub, self.pro, pro_clone, now=START + timedelta(days=5)
        )

        self.assertIsNotNone(record)
        self.assertEqual(record.amount_cents, 0)
        self.assertEqual(ProrationRecord.objects.count(), 1)

    def test_currency_change_is_skipped(self):
        eur = Plan.objects.create(
            name="Euro", code="EUR", price_cents=9900, currency="EUR"
        )

        with self.assertLogs("apps.billing.services", level="WARNING") as logs:
            result = ProrationService.record_for_plan_change(
                self.sub, self.pro, eur, now=START + timedelta(days=5)
            )

        self.assertIsNone(result)
        self.assertEqual(ProrationRecord.objects.count(), 0)
        self.assertTrue(any("currency change" in m for m in logs.output))

    def test_never_raises_on_a_calculation_failure(self):
        with mock.patch.object(
            ProrationService, "calculate", side_effect=RuntimeError("boom")
        ):
            with self.assertLogs("apps.billing.services", level="ERROR"):
                result = ProrationService.record_for_plan_change(
                    self.sub, self.pro, self.team, now=START
                )
        self.assertIsNone(result)
        self.assertEqual(ProrationRecord.objects.count(), 0)


PASSWORD = "correct-horse-staple-42"


class ChangePlanWiringTests(APITestCase):
    URL = "/api/subscriptions/current/"

    def setUp(self):
        self.pro = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        self.team = Plan.objects.create(
            name="Team", code="TEAM", price_cents=9900, currency="USD"
        )
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.owner = User.objects.create_user(
            email="owner@example.com", password=PASSWORD
        )
        Membership.objects.create(
            user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER
        )
        self.sub = Subscription.objects.create(
            tenant=self.tenant, plan=self.pro,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now() - timedelta(days=10),
            current_period_end=timezone.now() + timedelta(days=20),
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.owner)}",
            HTTP_X_TENANT_ID=str(self.tenant.id),
        )

    def test_service_call_swaps_plan_and_records_one_proration(self):
        SubscriptionService.change_plan(self.sub, self.team)

        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_id, self.team.id)
        self.assertEqual(ProrationRecord.objects.count(), 1)
        record = ProrationRecord.objects.get()
        self.assertEqual(record.from_plan_id, self.pro.id)
        self.assertEqual(record.to_plan_id, self.team.id)
        self.assertGreater(record.amount_cents, 0)  # upgrade

    def test_patch_endpoint_records_a_proration(self):
        resp = self.client.patch(self.URL, {"plan_id": str(self.team.id)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["plan"]["code"], "TEAM")
        self.assertEqual(ProrationRecord.objects.count(), 1)

    def test_calculation_failure_does_not_block_the_plan_change(self):
        with mock.patch.object(
            ProrationService, "calculate", side_effect=RuntimeError("boom")
        ):
            resp = self.client.patch(self.URL, {"plan_id": str(self.team.id)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_id, self.team.id)
        self.assertEqual(ProrationRecord.objects.count(), 0)

    def test_real_db_insert_failure_does_not_poison_the_change_transaction(self):
        # calculate returns a result with currency=None -> the real
        # ProrationRecord insert hits a Postgres NOT NULL violation inside the
        # nested savepoint. The outer change_plan transaction must stay usable
        # and commit the plan swap.
        bad = ProrationResult(
            net_amount_cents=1, currency=None, calculated_at=timezone.now(),
            period_start=self.sub.current_period_start,
            period_end=self.sub.current_period_end,
            fraction_remaining=Fraction(1),
        )
        with mock.patch.object(ProrationService, "calculate", return_value=bad):
            resp = self.client.patch(self.URL, {"plan_id": str(self.team.id)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_id, self.team.id)
        self.assertEqual(ProrationRecord.objects.count(), 0)

    def test_same_plan_patch_still_succeeds_and_records_nothing(self):
        # Existing behavior preserved: a same-plan PATCH is accepted (200), not
        # rejected — D6 adds no guard. It just records no proration.
        resp = self.client.patch(self.URL, {"plan_id": str(self.pro.id)})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_id, self.pro.id)
        self.assertEqual(ProrationRecord.objects.count(), 0)

    def test_canceled_subscription_rejects_the_change_and_records_nothing(self):
        SubscriptionService.transition_status(
            self.sub, Subscription.Status.CANCELED
        )

        with self.assertRaises(IllegalStateTransition):
            SubscriptionService.change_plan(self.sub, self.team)

        self.assertEqual(ProrationRecord.objects.count(), 0)

"""
Stage D5 — usage metering (docs/stage-d5-spec.md §9).

The metered quantity is `active_members` — a count of the tenant's real
`Membership` rows. Nothing synthetic. Snapshots are tied to the tenant's
`Subscription` billing period and are idempotent via the
`unique_usage_snapshot` DB constraint.
"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import Plan, Subscription, UsageRecord
from apps.billing.services import UsageMeteringService
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

MEMBERS = UsageRecord.Metric.ACTIVE_MEMBERS


class UsageMeteringTestBase(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD",
            interval=Plan.Interval.MONTHLY,
        )
        self.start = timezone.now().replace(microsecond=0)
        self.end = self.start + timedelta(days=30)

    def _tenant(self, slug, *, members=0, subscription=True,
                status=Subscription.Status.ACTIVE, period=None):
        """A tenant with an OWNER plus `members` extra MEMBERs, and (by
        default) an ACTIVE subscription over self.start..self.end."""
        tenant = Tenant.objects.create(name=slug.title(), slug=slug)
        owner = User.objects.create_user(
            email=f"owner-{slug}@example.com", password="pw-12345678"
        )
        Membership.objects.create(
            user=owner, tenant=tenant, role=Membership.Role.OWNER
        )
        for i in range(members):
            u = User.objects.create_user(
                email=f"m{i}-{slug}@example.com", password="pw-12345678"
            )
            Membership.objects.create(
                user=u, tenant=tenant, role=Membership.Role.MEMBER
            )
        if subscription:
            s, e = period or (self.start, self.end)
            Subscription.objects.create(
                tenant=tenant, plan=self.plan, status=status,
                current_period_start=s, current_period_end=e,
            )
        return tenant


class RecordSnapshotTests(UsageMeteringTestBase):
    def test_counts_real_memberships_and_stores_the_subscription_period(self):
        tenant = self._tenant("acme", members=3)  # OWNER + 3 = 4

        record, created = UsageMeteringService.record_snapshot(tenant)

        self.assertTrue(created)
        self.assertEqual(record.metric, MEMBERS)
        self.assertEqual(record.quantity, 4)
        self.assertEqual(record.period_start, self.start)
        self.assertEqual(record.period_end, self.end)
        self.assertIsNotNone(record.recorded_at)
        self.assertEqual(UsageRecord.objects.count(), 1)

    def test_counts_only_this_tenants_members(self):
        acme = self._tenant("acme", members=2)   # 3
        self._tenant("globex", members=9)        # 10 — must not leak in

        record, _ = UsageMeteringService.record_snapshot(acme)

        self.assertEqual(record.quantity, 3)

    def test_owner_only_tenant_is_a_valid_quantity_of_one(self):
        tenant = self._tenant("solo", members=0)

        record, _ = UsageMeteringService.record_snapshot(tenant)

        self.assertEqual(record.quantity, 1)

    def test_no_subscription_raises_no_billing_period_and_writes_nothing(self):
        tenant = self._tenant("nosub", members=2, subscription=False)

        with self.assertLogs("apps.billing.services", level="INFO") as logs:
            with self.assertRaises(UsageMeteringService.NoBillingPeriod):
                UsageMeteringService.record_snapshot(tenant)

        self.assertEqual(UsageRecord.objects.count(), 0)
        self.assertTrue(any("no subscription" in m for m in logs.output))

    def test_status_does_not_gate_metering(self):
        # Eligibility rule: any Subscription row is metered, regardless of status.
        for i, st in enumerate(
            [
                Subscription.Status.TRIALING,
                Subscription.Status.PAST_DUE,
                Subscription.Status.CANCELED,
            ]
        ):
            tenant = self._tenant(f"t{i}", members=1, status=st)
            record, created = UsageMeteringService.record_snapshot(tenant)
            self.assertTrue(created, st)
            self.assertEqual(record.quantity, 2, st)
            self.assertEqual(record.period_start, self.start, st)

    def test_cancelled_mid_period_uses_whatever_period_is_on_the_row(self):
        # §8: don't reconstruct history — snapshot against the current row.
        odd_start = self.start - timedelta(days=7)
        odd_end = odd_start + timedelta(days=30)
        tenant = self._tenant(
            "cxl", members=0, status=Subscription.Status.CANCELED,
            period=(odd_start, odd_end),
        )

        record, _ = UsageMeteringService.record_snapshot(tenant)

        self.assertEqual(record.period_start, odd_start)
        self.assertEqual(record.period_end, odd_end)


class IdempotencyTests(UsageMeteringTestBase):
    def test_recording_twice_for_the_same_period_produces_one_row(self):
        tenant = self._tenant("acme", members=2)

        first, c1 = UsageMeteringService.record_snapshot(tenant)
        second, c2 = UsageMeteringService.record_snapshot(tenant)

        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(first.id, second.id)
        self.assertEqual(UsageRecord.objects.count(), 1)

    def test_the_unique_constraint_is_what_enforces_it(self):
        tenant = self._tenant("acme", members=1)
        UsageMeteringService.record_snapshot(tenant)

        # A raw duplicate insert for the same (tenant, metric, period) is
        # rejected by the DB, not by an application check.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                UsageRecord.objects.create(
                    tenant=tenant, metric=MEMBERS, quantity=999,
                    period_start=self.start, period_end=self.end,
                )

    def test_a_re_snapshot_does_not_refresh_the_quantity(self):
        tenant = self._tenant("acme", members=1)  # OWNER + 1 = 2
        first, _ = UsageMeteringService.record_snapshot(tenant)
        self.assertEqual(first.quantity, 2)

        # A member joins, then the period is snapshotted again.
        u = User.objects.create_user(email="late@acme.example.com", password="pw-12345678")
        Membership.objects.create(user=u, tenant=tenant, role=Membership.Role.MEMBER)

        second, created = UsageMeteringService.record_snapshot(tenant)

        self.assertFalse(created)
        self.assertEqual(second.quantity, 2)  # immutable — not re-counted to 3

    def test_a_new_period_is_a_new_row(self):
        tenant = self._tenant("acme", members=1)
        UsageMeteringService.record_snapshot(tenant)

        # Simulate a CHARGED webhook advancing the subscription's period.
        sub = Subscription.objects.get(tenant=tenant)
        sub.current_period_start = self.end
        sub.current_period_end = self.end + timedelta(days=30)
        sub.save(update_fields=["current_period_start", "current_period_end"])

        record, created = UsageMeteringService.record_snapshot(tenant)

        self.assertTrue(created)
        self.assertEqual(UsageRecord.objects.count(), 2)
        self.assertEqual(record.period_start, self.end)


class QueryMethodTests(UsageMeteringTestBase):
    def test_usage_for_period_returns_the_row_or_none(self):
        tenant = self._tenant("acme", members=2)
        UsageMeteringService.record_snapshot(tenant)

        hit = UsageMeteringService.usage_for_period(tenant, self.start, self.end)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.quantity, 3)

        miss = UsageMeteringService.usage_for_period(
            tenant, self.end, self.end + timedelta(days=30)
        )
        self.assertIsNone(miss)

    def test_current_usage_returns_the_current_period_row(self):
        tenant = self._tenant("acme", members=1)
        UsageMeteringService.record_snapshot(tenant)

        current = UsageMeteringService.current_usage(tenant)
        self.assertIsNotNone(current)
        self.assertEqual(current.period_start, self.start)

    def test_current_usage_is_none_without_a_subscription(self):
        tenant = self._tenant("nosub", subscription=False)
        self.assertIsNone(UsageMeteringService.current_usage(tenant))

    def test_current_usage_is_none_before_any_snapshot(self):
        tenant = self._tenant("acme")
        self.assertIsNone(UsageMeteringService.current_usage(tenant))


class MeterUsageCommandTests(UsageMeteringTestBase):
    def test_snapshots_every_subscribed_tenant_and_skips_the_rest(self):
        self._tenant("acme", members=2)                        # 3
        self._tenant("globex", members=0)                      # 1
        self._tenant("nosub", members=5, subscription=False)   # not metered

        out = StringIO()
        call_command("meter_usage", stdout=out)

        self.assertEqual(UsageRecord.objects.count(), 2)
        self.assertEqual(
            UsageRecord.objects.get(tenant__slug="acme").quantity, 3
        )
        self.assertEqual(
            UsageRecord.objects.get(tenant__slug="globex").quantity, 1
        )
        self.assertIn("2 new", out.getvalue())

    def test_a_second_run_in_the_same_period_creates_no_new_rows(self):
        self._tenant("acme", members=1)
        self._tenant("globex", members=3)

        call_command("meter_usage", stdout=StringIO())
        before = UsageRecord.objects.count()

        out = StringIO()
        call_command("meter_usage", stdout=out)

        self.assertEqual(UsageRecord.objects.count(), before)
        self.assertIn("0 new", out.getvalue())

    def test_nothing_to_do_when_no_tenant_has_a_subscription(self):
        self._tenant("nosub", subscription=False)

        out = StringIO()
        call_command("meter_usage", stdout=out)

        self.assertIn("Nothing to do", out.getvalue())
        self.assertEqual(UsageRecord.objects.count(), 0)

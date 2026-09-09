"""
Stage D8 — reconciliation (docs/stage-d8-spec.md §9).

Read-only cross-check of local `Subscription` status against the provider's
reported status, driven entirely by `MockGatewayAdapter.subscription_states`.
No live provider, no HTTP. These tests prove the comparison logic, the
provider-not-found path, the provider-failure-is-not-drift path, per-subscription
failure isolation, the eligibility filter, and the immutable-append policy —
NOT that reconciliation catches real Razorpay drift (that needs a live account;
see spec §0/§11).
"""

from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.billing.gateway import MockGatewayAdapter
from apps.billing.gateway.base import ProviderSubscriptionStatus, ProviderUnavailable
from apps.billing.models import Plan, ReconciliationDiscrepancy, Subscription
from apps.billing.services import ReconciliationService
from apps.tenants.models import Tenant

Category = ReconciliationDiscrepancy.Category


class ReconciliationTestBase(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD",
            interval=Plan.Interval.MONTHLY, external_plan_id="plan_PRO",
        )
        self.other_plan = Plan.objects.create(
            name="Team", code="TEAM", price_cents=9900, currency="USD",
            interval=Plan.Interval.MONTHLY, external_plan_id="plan_TEAM",
        )
        self.start = timezone.now().replace(microsecond=0)
        self.end = self.start + timedelta(days=30)

    def _sub(self, slug, *, status=Subscription.Status.ACTIVE, external_id=None,
             plan=None):
        """A tenant with a subscription. `external_id` defaults to `sub_<slug>`;
        pass `external_id=""` for a subscription with no provider id."""
        tenant = Tenant.objects.create(name=slug.title(), slug=slug)
        if external_id is None:
            external_id = f"sub_{slug}"
        return Subscription.objects.create(
            tenant=tenant,
            plan=plan or self.plan,
            status=status,
            external_subscription_id=external_id or None,
            current_period_start=self.start,
            current_period_end=self.end,
        )

    def _gateway(self, states):
        """Patch the service's gateway with a MockGatewayAdapter configured with
        `states`. Returns the adapter."""
        adapter = MockGatewayAdapter(subscription_states=states)
        patcher = mock.patch(
            "apps.billing.services.get_gateway", return_value=adapter
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return adapter


class ReconcileSubscriptionTests(ReconciliationTestBase):
    def test_match_records_no_discrepancy(self):
        sub = self._sub("acme")
        self._gateway({"sub_acme": {"status": "ACTIVE", "raw_status": "active"}})

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.MATCH)
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 0)

    def test_status_mismatch_is_recorded_with_both_statuses(self):
        sub = self._sub("acme", status=Subscription.Status.ACTIVE)
        self._gateway(
            {"sub_acme": {"status": "CANCELED", "raw_status": "cancelled"}}
        )

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.DISCREPANCY)
        self.assertEqual(result.category, Category.STATUS_MISMATCH)
        row = ReconciliationDiscrepancy.objects.get()
        self.assertEqual(row.category, Category.STATUS_MISMATCH)
        self.assertEqual(row.local_status, Subscription.Status.ACTIVE)
        self.assertEqual(row.provider_status, ProviderSubscriptionStatus.CANCELED)
        self.assertEqual(row.external_subscription_id, "sub_acme")
        self.assertEqual(row.tenant_id, sub.tenant_id)
        self.assertIn("cancelled", row.detail)  # raw status carried into the prose

    def test_status_mismatch_other_direction(self):
        sub = self._sub("acme", status=Subscription.Status.PAST_DUE)
        self._gateway({"sub_acme": {"status": "ACTIVE", "raw_status": "active"}})

        ReconciliationService.reconcile_subscription(sub)

        row = ReconciliationDiscrepancy.objects.get()
        self.assertEqual(row.category, Category.STATUS_MISMATCH)
        self.assertEqual(row.local_status, Subscription.Status.PAST_DUE)
        self.assertEqual(row.provider_status, ProviderSubscriptionStatus.ACTIVE)

    def test_local_trialing_matches_provider_active(self):
        sub = self._sub("acme", status=Subscription.Status.TRIALING)
        self._gateway({"sub_acme": {"status": "ACTIVE", "raw_status": "active"}})

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.MATCH)
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 0)

    def test_local_canceled_provider_canceled_is_a_match(self):
        sub = self._sub("acme", status=Subscription.Status.CANCELED)
        self._gateway(
            {"sub_acme": {"status": "CANCELED", "raw_status": "cancelled"}}
        )

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.MATCH)
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 0)

    def test_local_canceled_provider_active_is_its_own_category(self):
        sub = self._sub("acme", status=Subscription.Status.CANCELED)
        self._gateway({"sub_acme": {"status": "ACTIVE", "raw_status": "active"}})

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.DISCREPANCY)
        self.assertEqual(result.category, Category.LOCAL_CANCELED_PROVIDER_ACTIVE)
        row = ReconciliationDiscrepancy.objects.get()
        self.assertEqual(row.category, Category.LOCAL_CANCELED_PROVIDER_ACTIVE)
        self.assertNotEqual(row.category, Category.STATUS_MISMATCH)
        self.assertEqual(row.local_status, Subscription.Status.CANCELED)
        self.assertEqual(row.provider_status, ProviderSubscriptionStatus.ACTIVE)

    def test_local_canceled_provider_past_due_and_pending_same_category(self):
        for slug, provider in (
            ("a", {"status": "PAST_DUE", "raw_status": "halted"}),
            ("b", {"status": "PENDING", "raw_status": "authenticated"}),
        ):
            with self.subTest(provider=provider):
                sub = self._sub(slug, status=Subscription.Status.CANCELED)
                self._gateway({f"sub_{slug}": provider})

                ReconciliationService.reconcile_subscription(sub)

                row = ReconciliationDiscrepancy.objects.get(
                    external_subscription_id=f"sub_{slug}"
                )
                self.assertEqual(
                    row.category, Category.LOCAL_CANCELED_PROVIDER_ACTIVE
                )
                self.assertEqual(row.provider_status, provider["status"])

    def test_discrepancy_is_auditable_from_columns_without_parsing_detail(self):
        sub = self._sub("acme", status=Subscription.Status.ACTIVE)
        self._gateway(
            {"sub_acme": {"status": "PAST_DUE", "raw_status": "halted"}}
        )

        ReconciliationService.reconcile_subscription(sub)

        row = ReconciliationDiscrepancy.objects.get()
        # The whole point: no string parsing needed.
        self.assertEqual(row.local_status, "ACTIVE")
        self.assertEqual(row.provider_status, "PAST_DUE")

    def test_plan_divergence_alone_is_not_a_discrepancy(self):
        # local plan != provider plan_id, but status agrees -> no drift (D6 gap).
        sub = self._sub("acme", status=Subscription.Status.ACTIVE, plan=self.plan)
        adapter = self._gateway(
            {
                "sub_acme": {
                    "status": "ACTIVE",
                    "raw_status": "active",
                    "external_plan_id": "plan_TEAM",  # differs from local plan_PRO
                }
            }
        )

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.MATCH)
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 0)
        # the state still captures the provider plan id, for a future stage
        self.assertEqual(
            adapter.fetch_subscription_state("sub_acme").external_plan_id,
            "plan_TEAM",
        )

    def test_period_divergence_is_not_a_discrepancy(self):
        sub = self._sub("acme", status=Subscription.Status.ACTIVE)
        sub.current_period_start = self.start - timedelta(days=900)
        sub.current_period_end = self.start - timedelta(days=870)
        sub.save(update_fields=["current_period_start", "current_period_end"])
        self._gateway({"sub_acme": {"status": "ACTIVE", "raw_status": "active"}})

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.MATCH)
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 0)

    def test_provider_not_found_is_a_distinct_category(self):
        sub = self._sub("acme", status=Subscription.Status.ACTIVE)
        self._gateway({"sub_acme": None})

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.DISCREPANCY)
        self.assertEqual(result.category, Category.PROVIDER_NOT_FOUND)
        row = ReconciliationDiscrepancy.objects.get()
        self.assertEqual(row.category, Category.PROVIDER_NOT_FOUND)
        self.assertEqual(row.local_status, Subscription.Status.ACTIVE)
        self.assertEqual(row.provider_status, "")

    def test_unknown_id_is_treated_as_provider_not_found(self):
        sub = self._sub("acme", status=Subscription.Status.ACTIVE)
        self._gateway({})  # nothing configured for sub_acme

        result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.category, Category.PROVIDER_NOT_FOUND)

    def test_provider_unavailable_records_nothing_and_does_not_raise(self):
        sub = self._sub("acme", status=Subscription.Status.ACTIVE)
        self._gateway({"sub_acme": ProviderUnavailable("razorpay 503")})

        with self.assertLogs("apps.billing.services", level="WARNING") as cm:
            result = ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(result.outcome, ReconciliationService.UNAVAILABLE)
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 0)
        self.assertTrue(any("provider unavailable" in m for m in cm.output))

    def test_reconcile_does_not_mutate_the_subscription(self):
        sub = self._sub("acme", status=Subscription.Status.CANCELED)
        before = Subscription.objects.get(pk=sub.pk)
        self._gateway({"sub_acme": {"status": "ACTIVE", "raw_status": "active"}})

        ReconciliationService.reconcile_subscription(sub)

        after = Subscription.objects.get(pk=sub.pk)
        self.assertEqual(after.status, before.status)  # NOT "corrected"
        self.assertEqual(after.plan_id, before.plan_id)
        self.assertEqual(after.updated_at, before.updated_at)
        self.assertEqual(after.current_period_end, before.current_period_end)

    def test_repeated_reconciliation_appends_a_row_each_time(self):
        sub = self._sub("acme", status=Subscription.Status.ACTIVE)
        self._gateway(
            {"sub_acme": {"status": "CANCELED", "raw_status": "cancelled"}}
        )

        ReconciliationService.reconcile_subscription(sub)
        ReconciliationService.reconcile_subscription(sub)

        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 2)


class ReconcileAllTests(ReconciliationTestBase):
    def test_only_subscriptions_with_a_provider_id_are_swept(self):
        self._sub("linked", external_id="sub_linked")
        self._sub("unlinked", external_id="")
        self._gateway(
            {"sub_linked": {"status": "ACTIVE", "raw_status": "active"}}
        )

        result = ReconciliationService.reconcile_all()

        self.assertEqual(result.total, 1)
        self.assertEqual(result.checked[0].external_subscription_id, "sub_linked")

    def test_locally_canceled_subscription_is_included_in_the_sweep(self):
        self._sub("gone", status=Subscription.Status.CANCELED, external_id="sub_gone")
        self._gateway({"sub_gone": {"status": "ACTIVE", "raw_status": "active"}})

        result = ReconciliationService.reconcile_all()

        self.assertEqual(result.total, 1)
        self.assertEqual(len(result.discrepancies), 1)
        self.assertEqual(
            ReconciliationDiscrepancy.objects.get().category,
            Category.LOCAL_CANCELED_PROVIDER_ACTIVE,
        )

    def test_one_failing_subscription_does_not_stop_the_others(self):
        self._sub("a", external_id="sub_a")
        self._sub("b", external_id="sub_b")
        self._sub("c", external_id="sub_c")

        real = ReconciliationService.reconcile_subscription

        def flaky(subscription, **kw):
            if subscription.external_subscription_id == "sub_b":
                raise RuntimeError("kaboom")
            return real(subscription, **kw)

        self._gateway(
            {
                "sub_a": {"status": "CANCELED", "raw_status": "cancelled"},
                "sub_c": {"status": "CANCELED", "raw_status": "cancelled"},
            }
        )
        with mock.patch.object(
            ReconciliationService, "reconcile_subscription", side_effect=flaky
        ):
            result = ReconciliationService.reconcile_all()

        self.assertEqual(result.total, 3)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(len(result.discrepancies), 2)  # a and c still recorded
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 2)

    def test_clean_sweep_reports_all_matched(self):
        self._sub("a", external_id="sub_a")
        self._sub("b", external_id="sub_b")
        self._gateway(
            {
                "sub_a": {"status": "ACTIVE", "raw_status": "active"},
                "sub_b": {"status": "ACTIVE", "raw_status": "active"},
            }
        )

        result = ReconciliationService.reconcile_all()

        self.assertEqual(len(result.matched), 2)
        self.assertEqual(len(result.discrepancies), 0)
        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 0)


class ReconcileCommandTests(ReconciliationTestBase):
    def test_command_reports_nothing_to_do_with_no_linked_subscriptions(self):
        self._sub("unlinked", external_id="")
        out = StringIO()

        call_command("reconcile_subscriptions", stdout=out)

        self.assertIn("Nothing to do", out.getvalue())

    def test_command_drives_the_real_sweep_and_records_drift(self):
        self._sub("acme", status=Subscription.Status.ACTIVE, external_id="sub_acme")
        self._gateway(
            {"sub_acme": {"status": "CANCELED", "raw_status": "cancelled"}}
        )
        out = StringIO()

        call_command("reconcile_subscriptions", stdout=out)

        self.assertEqual(ReconciliationDiscrepancy.objects.count(), 1)
        self.assertIn("STATUS_MISMATCH", out.getvalue())
        self.assertIn("1 discrepancies", out.getvalue())

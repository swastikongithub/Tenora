"""
The three fallback sweep triggers — docs/operator-control-plane-spec.md §B
"Fallback sweep controls — explicitly temporary":

  POST /api/platform/webhook-events/process-pending/
  POST /api/platform/reconciliation/run/
  POST /api/platform/usage/run/

Each must call the exact existing sweep-all service entry point (no
orchestration logic duplicated here), be Staff-tier, throttled at
`platform-sweep` (10/hour, shared across all three — one scope name applied
to all of them), and record an observational (not critical) audit entry
that never blocks the underlying action even if the audit write itself
fails.
"""

from unittest import mock

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.gateway.base import EventType
from apps.billing.models import Plan, WebhookEvent
from apps.billing.services import SubscriptionService
from apps.platform.models import AuditEvent
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

PROCESS_PENDING_URL = "/api/platform/webhook-events/process-pending/"
RECONCILIATION_RUN_URL = "/api/platform/reconciliation/run/"
USAGE_RUN_URL = "/api/platform/usage/run/"
ALL_SWEEP_URLS = [PROCESS_PENDING_URL, RECONCILIATION_RUN_URL, USAGE_RUN_URL]
PASSWORD = "correct-horse-staple-42"


class SweepEndpointTestBase(APITestCase):
    def setUp(self):
        cache.clear()  # ScopedRateThrottle state must not leak across tests
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.ordinary = User.objects.create_user(
            email="normal@example.com", password=PASSWORD
        )

    def _auth(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}"
        )

    def tearDown(self):
        cache.clear()


class SweepEndpointPermissionTests(SweepEndpointTestBase):
    def test_unauthenticated_gets_401_on_every_sweep_endpoint(self):
        for url in ALL_SWEEP_URLS:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.post(url).status_code, status.HTTP_401_UNAUTHORIZED
                )

    def test_ordinary_user_gets_403_on_every_sweep_endpoint(self):
        self._auth(self.ordinary)
        for url in ALL_SWEEP_URLS:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.post(url).status_code, status.HTTP_403_FORBIDDEN
                )

    def test_staff_is_allowed_on_every_sweep_endpoint(self):
        self._auth(self.staff)
        for url in ALL_SWEEP_URLS:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.post(url).status_code, status.HTTP_200_OK
                )

    def test_no_endpoint_requires_x_tenant_id(self):
        self._auth(self.staff)
        for url in ALL_SWEEP_URLS:
            with self.subTest(url=url):
                resp = self.client.post(url, HTTP_X_TENANT_ID="")
                self.assertNotEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class WebhookProcessPendingTests(SweepEndpointTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_calls_the_exact_existing_sweep_service(self):
        with mock.patch(
            "apps.platform.views.WebhookProcessingService.process_pending"
        ) as mocked:
            from apps.billing.services import WebhookSweepResult

            mocked.return_value = WebhookSweepResult(events=[])
            self.client.post(PROCESS_PENDING_URL)
            mocked.assert_called_once_with()

    def test_real_effect_an_unprocessed_event_becomes_processed(self):
        # UNKNOWN event types always resolve to NOOP but are still marked
        # processed=True (apps.billing.services.WebhookProcessingService
        # ._handle_unknown) — the simplest deterministic "real sweep effect"
        # to assert without needing a matched subscription.
        event = WebhookEvent.objects.create(
            external_event_id="evt_1",
            event_type=EventType.UNKNOWN,
            raw_payload={},
            processed=False,
        )
        resp = self.client.post(PROCESS_PENDING_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["total"], 1)
        event.refresh_from_db()
        self.assertTrue(event.processed)

    def test_writes_an_observational_not_critical_audit_row(self):
        self.client.post(PROCESS_PENDING_URL)
        event = AuditEvent.objects.get()
        self.assertFalse(event.is_critical)
        self.assertEqual(event.action, "webhook.sweep_triggered")
        self.assertEqual(event.actor, self.staff)

    def test_observational_audit_failure_does_not_block_the_sweep(self):
        WebhookEvent.objects.create(
            external_event_id="evt_1",
            event_type=EventType.UNKNOWN,
            raw_payload={},
            processed=False,
        )
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            resp = self.client.post(PROCESS_PENDING_URL)

        # The sweep's own effect still happened and is still reported —
        # only the audit row is missing.
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["total"], 1)
        self.assertEqual(AuditEvent.objects.count(), 0)


class ReconciliationRunTests(SweepEndpointTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_calls_the_exact_existing_sweep_service(self):
        with mock.patch(
            "apps.platform.views.ReconciliationService.reconcile_all"
        ) as mocked:
            from apps.billing.services import ReconciliationSweepResult

            mocked.return_value = ReconciliationSweepResult(checked=[])
            self.client.post(RECONCILIATION_RUN_URL)
            mocked.assert_called_once_with()

    def test_real_call_with_no_gateway_linked_subscriptions_reports_zero(self):
        # No Subscription has an external_subscription_id in this test —
        # ReconciliationService.reconcile_all()'s own queryset excludes
        # those, so this is a genuine, un-mocked end-to-end call.
        resp = self.client.post(RECONCILIATION_RUN_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["total"], 0)

    def test_writes_an_observational_not_critical_audit_row(self):
        self.client.post(RECONCILIATION_RUN_URL)
        event = AuditEvent.objects.get()
        self.assertFalse(event.is_critical)
        self.assertEqual(event.action, "reconciliation.sweep_triggered")

    def test_observational_audit_failure_does_not_block_the_sweep(self):
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            resp = self.client.post(RECONCILIATION_RUN_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditEvent.objects.count(), 0)


class UsageRunTests(SweepEndpointTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_calls_the_exact_existing_sweep_service(self):
        with mock.patch(
            "apps.platform.views.UsageMeteringService.snapshot_all_subscribed"
        ) as mocked:
            from apps.billing.services import UsageSnapshotBatchResult

            mocked.return_value = UsageSnapshotBatchResult(
                records=[], existing=0, skipped=0, total=0
            )
            self.client.post(USAGE_RUN_URL)
            mocked.assert_called_once_with()

    def test_real_effect_a_subscribed_tenant_gets_a_usage_snapshot(self):
        from apps.billing.models import UsageRecord

        plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        owner = User.objects.create_user(email="owner@acme.test", password=PASSWORD)
        Membership.objects.create(user=owner, tenant=tenant, role=Membership.Role.OWNER)
        start, end = SubscriptionService.default_period(plan)
        SubscriptionService.create_subscription(tenant, plan, start, end)

        resp = self.client.post(USAGE_RUN_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["created"], 1)
        self.assertTrue(
            UsageRecord.objects.filter(
                tenant=tenant, metric=UsageRecord.Metric.ACTIVE_MEMBERS
            ).exists()
        )

    def test_writes_an_observational_not_critical_audit_row(self):
        self.client.post(USAGE_RUN_URL)
        event = AuditEvent.objects.get()
        self.assertFalse(event.is_critical)
        self.assertEqual(event.action, "usage.sweep_triggered")

    def test_observational_audit_failure_does_not_block_the_sweep(self):
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            resp = self.client.post(USAGE_RUN_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditEvent.objects.count(), 0)


class SweepThrottleTests(SweepEndpointTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_throttled_at_10_per_hour(self):
        for _ in range(10):
            resp = self.client.post(PROCESS_PENDING_URL)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(PROCESS_PENDING_URL)
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_throttle_budget_is_shared_across_all_three_sweep_endpoints(self):
        # One "platform-sweep" scope applied to all three, not 10/hour each
        # independently — exhausting it via one endpoint throttles the
        # others too.
        for _ in range(10):
            self.client.post(PROCESS_PENDING_URL)

        resp = self.client.post(RECONCILIATION_RUN_URL)
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        resp = self.client.post(USAGE_RUN_URL)
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

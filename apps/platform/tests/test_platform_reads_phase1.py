"""
Operator Control Plane, Phase 1 (docs/operator-control-plane-spec.md) — the
new read-only platform endpoints: health, plans (list/detail), tenant detail,
webhook events (list/detail, sanitized), reconciliation discrepancies, users
(list/detail).

Real access tokens throughout, never force_authenticate — same convention
apps/platform/tests/test_platform_views.py already documents.

Detail lookups here use `?id=` on a static path (not a `<uuid:pk>` path
segment) — see apps/platform/views.py's module docstring for why; these
tests exercise that exact contract, including the malformed/unmatched-id
404 case.
"""

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.gateway.base import EventType
from apps.billing.models import (
    Plan,
    ReconciliationDiscrepancy,
    Subscription,
    WebhookEvent,
)
from apps.billing.services import SubscriptionService
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

PASSWORD = "correct-horse-staple-42"

HEALTH_URL = "/api/platform/health/"
PLANS_URL = "/api/platform/plans/"
PLAN_DETAIL_URL = "/api/platform/plans/detail/"
TENANT_DETAIL_URL = "/api/platform/tenants/detail/"
WEBHOOK_EVENTS_URL = "/api/platform/webhook-events/"
WEBHOOK_EVENT_DETAIL_URL = "/api/platform/webhook-events/detail/"
DISCREPANCIES_URL = "/api/platform/reconciliation-discrepancies/"
USERS_URL = "/api/platform/users/"
USER_DETAIL_URL = "/api/platform/users/detail/"

ALL_URLS = [
    HEALTH_URL,
    PLANS_URL,
    PLAN_DETAIL_URL,
    TENANT_DETAIL_URL,
    WEBHOOK_EVENTS_URL,
    WEBHOOK_EVENT_DETAIL_URL,
    DISCREPANCIES_URL,
    USERS_URL,
    USER_DETAIL_URL,
]


class PlatformPhase1PermissionMatrixTests(APITestCase):
    """Every new endpoint, run through the same matrix as the existing
    platform-admin endpoints: unauthenticated -> 401, ordinary user -> 403,
    staff -> allowed, no X-Tenant-ID required."""

    def setUp(self):
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

    def test_unauthenticated_gets_401_on_every_new_endpoint(self):
        for url in ALL_URLS:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )

    def test_non_staff_gets_403_not_404_on_every_new_endpoint(self):
        self._auth(self.ordinary)
        for url in ALL_URLS:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code, status.HTTP_403_FORBIDDEN
                )

    def test_staff_is_allowed_on_every_new_endpoint_with_no_tenant_header(self):
        # No X-Tenant-ID sent anywhere below — global paths, staff JWT alone.
        self._auth(self.staff)
        for url in ALL_URLS:
            with self.subTest(url=url):
                resp = self.client.get(url)
                # Detail endpoints 404 with no ?id= at all — still proves the
                # permission layer let the request through (not 401/403).
                self.assertIn(
                    resp.status_code,
                    (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND),
                )

    def test_no_endpoint_requires_x_tenant_id(self):
        # A staff caller with NO tenant context at all (no Membership rows,
        # no header) still gets through every global path.
        self._auth(self.staff)
        for url in ALL_URLS:
            with self.subTest(url=url):
                resp = self.client.get(url, HTTP_X_TENANT_ID="")
                self.assertNotEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class PlatformHealthViewTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.staff)}"
        )

    def test_empty_system_reports_zeros_and_null_timestamps(self):
        data = self.client.get(HEALTH_URL).data
        self.assertEqual(data["total_tenants"], 0)
        self.assertEqual(data["unprocessed_webhook_events"], 0)
        self.assertEqual(data["discrepancies_last_24h"], 0)
        self.assertIsNone(data["last_webhook_received_at"])
        self.assertIsNone(data["last_usage_snapshot_at"])
        self.assertIsNone(data["last_discrepancy_detected_at"])

    def test_reports_the_configured_gateway_adapter(self):
        from django.conf import settings

        data = self.client.get(HEALTH_URL).data
        self.assertEqual(data["payment_gateway"], settings.PAYMENT_GATEWAY)

    def test_unprocessed_webhook_backlog_is_a_real_count(self):
        WebhookEvent.objects.create(
            external_event_id="evt_1",
            event_type=EventType.CHARGED,
            raw_payload={},
            processed=False,
        )
        WebhookEvent.objects.create(
            external_event_id="evt_2",
            event_type=EventType.CHARGED,
            raw_payload={},
            processed=True,
        )
        data = self.client.get(HEALTH_URL).data
        self.assertEqual(data["unprocessed_webhook_events"], 1)


class PlatformPlanListDetailTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.staff)}"
        )
        self.active_plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD", is_active=True
        )
        self.inactive_plan = Plan.objects.create(
            name="Legacy",
            code="LEGACY",
            price_cents=1900,
            currency="USD",
            is_active=False,
        )

    def test_list_includes_inactive_plans_unlike_the_tenant_facing_endpoint(self):
        resp = self.client.get(PLANS_URL)
        codes = {row["code"] for row in resp.data["results"]}
        self.assertEqual(codes, {"PRO", "LEGACY"})

    def test_list_is_paginated(self):
        resp = self.client.get(PLANS_URL)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, resp.data)

    def test_filter_by_is_active(self):
        resp = self.client.get(PLANS_URL, {"is_active": "true"})
        codes = {row["code"] for row in resp.data["results"]}
        self.assertEqual(codes, {"PRO"})

    def test_search_by_name_or_code(self):
        resp = self.client.get(PLANS_URL, {"search": "legacy"})
        codes = {row["code"] for row in resp.data["results"]}
        self.assertEqual(codes, {"LEGACY"})

    def test_detail_exposes_external_plan_id_and_subscriber_count(self):
        tenant = Tenant.objects.create(name="Alpha", slug="alpha")
        start, end = SubscriptionService.default_period(self.active_plan)
        SubscriptionService.create_subscription(tenant, self.active_plan, start, end)

        resp = self.client.get(PLAN_DETAIL_URL, {"id": str(self.active_plan.id)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["code"], "PRO")
        self.assertIn("external_plan_id", resp.data)
        self.assertEqual(resp.data["subscriber_count"], 1)

    def test_detail_404_for_nonexistent_id(self):
        resp = self.client.get(
            PLAN_DETAIL_URL, {"id": "00000000-0000-0000-0000-000000000000"}
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_404_for_malformed_id(self):
        resp = self.client.get(PLAN_DETAIL_URL, {"id": "not-a-uuid"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_404_for_missing_id(self):
        resp = self.client.get(PLAN_DETAIL_URL)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PlatformTenantDetailTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.staff)}"
        )
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )

    def test_detail_includes_memberships_and_subscription(self):
        tenant = Tenant.objects.create(name="Alpha", slug="alpha")
        owner = User.objects.create_user(email="owner@alpha.test", password=PASSWORD)
        Membership.objects.create(user=owner, tenant=tenant, role=Membership.Role.OWNER)
        start, end = SubscriptionService.default_period(self.plan)
        SubscriptionService.create_subscription(
            tenant, self.plan, start, end, external_subscription_id="sub_ext_1"
        )

        resp = self.client.get(TENANT_DETAIL_URL, {"id": str(tenant.id)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "Alpha")
        self.assertEqual(len(resp.data["memberships"]), 1)
        self.assertEqual(resp.data["memberships"][0]["email"], "owner@alpha.test")
        self.assertEqual(resp.data["subscription"]["status"], "TRIALING")
        self.assertEqual(resp.data["recent_webhook_events"], [])

    def test_detail_subscription_null_when_absent(self):
        tenant = Tenant.objects.create(name="Beta", slug="beta")
        resp = self.client.get(TENANT_DETAIL_URL, {"id": str(tenant.id)})
        self.assertIsNone(resp.data["subscription"])
        self.assertEqual(resp.data["memberships"], [])

    def test_detail_includes_recent_webhook_events_sanitized(self):
        tenant = Tenant.objects.create(name="Gamma", slug="gamma")
        start, end = SubscriptionService.default_period(self.plan)
        SubscriptionService.create_subscription(
            tenant, self.plan, start, end, external_subscription_id="sub_ext_9"
        )
        WebhookEvent.objects.create(
            external_event_id="evt_9",
            event_type=EventType.CHARGED,
            raw_payload={"contact": "leaked@example.com"},
            external_subscription_id="sub_ext_9",
        )

        resp = self.client.get(TENANT_DETAIL_URL, {"id": str(tenant.id)})
        events = resp.data["recent_webhook_events"]
        self.assertEqual(len(events), 1)
        self.assertNotIn("raw_payload", events[0])
        self.assertEqual(events[0]["tenant"]["id"], str(tenant.id))

    def test_404_for_nonexistent_tenant(self):
        resp = self.client.get(
            TENANT_DETAIL_URL, {"id": "00000000-0000-0000-0000-000000000000"}
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PlatformWebhookEventSanitizationTests(APITestCase):
    """The core promise of docs/operator-control-plane-spec.md §B: sanitized
    normalized fields only, raw_payload NEVER exposed by list or detail."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.staff)}"
        )
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        self.tenant = Tenant.objects.create(name="Alpha", slug="alpha")
        start, end = SubscriptionService.default_period(self.plan)
        SubscriptionService.create_subscription(
            self.tenant, self.plan, start, end, external_subscription_id="sub_ext_1"
        )
        self.event = WebhookEvent.objects.create(
            external_event_id="evt_1",
            event_type=EventType.CHARGED,
            raw_payload={
                "event": "subscription.charged",
                "contact": {"email": "customer@example.com", "phone": "+15551234"},
            },
            external_subscription_id="sub_ext_1",
        )

    def test_list_never_exposes_raw_payload(self):
        resp = self.client.get(WEBHOOK_EVENTS_URL)
        for row in resp.data["results"]:
            self.assertNotIn("raw_payload", row)
        self.assertEqual(len(resp.data["results"]), 1)

    def test_list_never_leaks_raw_payload_content_anywhere_in_the_body(self):
        resp = self.client.get(WEBHOOK_EVENTS_URL)
        self.assertNotIn("customer@example.com", resp.content.decode())
        self.assertNotIn("+15551234", resp.content.decode())

    def test_detail_never_exposes_raw_payload(self):
        resp = self.client.get(WEBHOOK_EVENT_DETAIL_URL, {"id": str(self.event.id)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("raw_payload", resp.data)
        self.assertNotIn("customer@example.com", resp.content.decode())

    def test_detail_exposes_exactly_the_sanitized_field_set(self):
        resp = self.client.get(WEBHOOK_EVENT_DETAIL_URL, {"id": str(self.event.id)})
        self.assertEqual(
            set(resp.data.keys()),
            {
                "id",
                "external_event_id",
                "event_type",
                "external_subscription_id",
                "tenant",
                "period_start",
                "period_end",
                "event_created_at",
                "received_at",
                "processed",
            },
        )

    def test_detail_resolves_tenant_from_subscription(self):
        resp = self.client.get(WEBHOOK_EVENT_DETAIL_URL, {"id": str(self.event.id)})
        self.assertEqual(resp.data["tenant"]["id"], str(self.tenant.id))
        self.assertEqual(resp.data["tenant"]["slug"], "alpha")

    def test_detail_tenant_null_when_unmatched(self):
        orphan = WebhookEvent.objects.create(
            external_event_id="evt_orphan",
            event_type=EventType.UNKNOWN,
            raw_payload={},
            external_subscription_id="sub_no_match",
        )
        resp = self.client.get(WEBHOOK_EVENT_DETAIL_URL, {"id": str(orphan.id)})
        self.assertIsNone(resp.data["tenant"])

    def test_detail_404_for_nonexistent_id(self):
        resp = self.client.get(
            WEBHOOK_EVENT_DETAIL_URL, {"id": "00000000-0000-0000-0000-000000000000"}
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_tenant(self):
        other_tenant = Tenant.objects.create(name="Beta", slug="beta")
        start, end = SubscriptionService.default_period(self.plan)
        SubscriptionService.create_subscription(
            other_tenant, self.plan, start, end, external_subscription_id="sub_ext_2"
        )
        WebhookEvent.objects.create(
            external_event_id="evt_2",
            event_type=EventType.CHARGED,
            raw_payload={},
            external_subscription_id="sub_ext_2",
        )

        resp = self.client.get(WEBHOOK_EVENTS_URL, {"tenant": str(self.tenant.id)})
        ids = {row["external_event_id"] for row in resp.data["results"]}
        self.assertEqual(ids, {"evt_1"})

    def test_filter_by_event_type(self):
        WebhookEvent.objects.create(
            external_event_id="evt_cancelled",
            event_type=EventType.CANCELLED,
            raw_payload={},
        )
        resp = self.client.get(WEBHOOK_EVENTS_URL, {"event_type": "CANCELLED"})
        ids = {row["external_event_id"] for row in resp.data["results"]}
        self.assertEqual(ids, {"evt_cancelled"})

    def test_filter_by_invalid_event_type_returns_empty_not_error(self):
        resp = self.client.get(WEBHOOK_EVENTS_URL, {"event_type": "NOT_A_TYPE"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["results"], [])

    def test_filter_by_processed(self):
        WebhookEvent.objects.filter(pk=self.event.pk).update(processed=True)
        resp = self.client.get(WEBHOOK_EVENTS_URL, {"processed": "true"})
        ids = {row["external_event_id"] for row in resp.data["results"]}
        self.assertEqual(ids, {"evt_1"})

        resp = self.client.get(WEBHOOK_EVENTS_URL, {"processed": "false"})
        self.assertEqual(resp.data["results"], [])


class PlatformReconciliationDiscrepancyListTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.staff)}"
        )
        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        self.tenant = Tenant.objects.create(name="Alpha", slug="alpha")
        start, end = SubscriptionService.default_period(self.plan)
        self.subscription = SubscriptionService.create_subscription(
            self.tenant, self.plan, start, end, external_subscription_id="sub_ext_1"
        )

    def _discrepancy(self, category):
        from django.utils import timezone

        return ReconciliationDiscrepancy.objects.create(
            tenant=self.tenant,
            subscription=self.subscription,
            external_subscription_id="sub_ext_1",
            category=category,
            local_status="ACTIVE",
            provider_status="PAST_DUE",
            detail="local ACTIVE vs provider PAST_DUE",
            detected_at=timezone.now(),
        )

    def test_list_returns_discrepancies_with_tenant_summary(self):
        self._discrepancy(ReconciliationDiscrepancy.Category.STATUS_MISMATCH)
        resp = self.client.get(DISCREPANCIES_URL)
        self.assertEqual(len(resp.data["results"]), 1)
        row = resp.data["results"][0]
        self.assertEqual(row["tenant"]["slug"], "alpha")
        self.assertEqual(row["category"], "STATUS_MISMATCH")

    def test_filter_by_category(self):
        self._discrepancy(ReconciliationDiscrepancy.Category.STATUS_MISMATCH)
        self._discrepancy(ReconciliationDiscrepancy.Category.PROVIDER_NOT_FOUND)
        resp = self.client.get(
            DISCREPANCIES_URL, {"category": "PROVIDER_NOT_FOUND"}
        )
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["category"], "PROVIDER_NOT_FOUND")

    def test_filter_by_tenant(self):
        other = Tenant.objects.create(name="Beta", slug="beta")
        resp = self.client.get(DISCREPANCIES_URL, {"tenant": str(other.id)})
        self.assertEqual(resp.data["results"], [])


class PlatformUserListDetailTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.staff)}"
        )

    def test_list_never_exposes_password(self):
        User.objects.create_user(email="ordinary@example.com", password=PASSWORD)
        resp = self.client.get(USERS_URL)
        for row in resp.data["results"]:
            self.assertNotIn("password", row)

    def test_filter_by_is_staff(self):
        User.objects.create_user(email="ordinary@example.com", password=PASSWORD)
        resp = self.client.get(USERS_URL, {"is_staff": "true"})
        emails = {row["email"] for row in resp.data["results"]}
        self.assertEqual(emails, {"operator@example.com"})

    def test_search_by_email(self):
        User.objects.create_user(email="findme@example.com", password=PASSWORD)
        resp = self.client.get(USERS_URL, {"search": "findme"})
        emails = {row["email"] for row in resp.data["results"]}
        self.assertEqual(emails, {"findme@example.com"})

    def test_detail_includes_memberships_across_tenants(self):
        user = User.objects.create_user(email="member@example.com", password=PASSWORD)
        t1 = Tenant.objects.create(name="Alpha", slug="alpha")
        t2 = Tenant.objects.create(name="Beta", slug="beta")
        Membership.objects.create(user=user, tenant=t1, role=Membership.Role.OWNER)
        Membership.objects.create(user=user, tenant=t2, role=Membership.Role.MEMBER)

        resp = self.client.get(USER_DETAIL_URL, {"id": str(user.id)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        roles = {m["slug"]: m["role"] for m in resp.data["memberships"]}
        self.assertEqual(roles, {"alpha": "OWNER", "beta": "MEMBER"})
        self.assertNotIn("password", resp.data)

    def test_detail_404_for_nonexistent_user(self):
        resp = self.client.get(
            USER_DETAIL_URL, {"id": "00000000-0000-0000-0000-000000000000"}
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

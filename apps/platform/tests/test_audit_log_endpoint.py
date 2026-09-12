"""
GET /api/platform/audit-log/ — docs/operator-control-plane-spec.md §C, the
previously-deferred read surface for Phase 2's new AuditEvent rows.
Staff-tier, paginated (page size 25), filterable by actor/action/
target_type/is_critical, newest first.
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.platform.models import AuditEvent
from apps.platform.services import AuditService
from apps.users.models import User

URL = "/api/platform/audit-log/"
PASSWORD = "correct-horse-staple-42"


class AuditLogTestBase(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.other_staff = User.objects.create_user(
            email="other-operator@example.com", password=PASSWORD, is_staff=True
        )
        self.ordinary = User.objects.create_user(
            email="normal@example.com", password=PASSWORD
        )

    def _auth(self, user):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}"
        )


class AuditLogPermissionTests(AuditLogTestBase):
    def test_unauthenticated_gets_401(self):
        self.assertEqual(
            self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_ordinary_user_gets_403(self):
        self._auth(self.ordinary)
        self.assertEqual(
            self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_staff_is_allowed(self):
        self._auth(self.staff)
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_200_OK)

    def test_no_x_tenant_id_required(self):
        self._auth(self.staff)
        resp = self.client.get(URL, HTTP_X_TENANT_ID="")
        self.assertNotEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class AuditLogListTests(AuditLogTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_empty_log_returns_empty_paginated_results(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 0)
        self.assertEqual(resp.data["results"], [])

    def test_ordered_newest_first(self):
        # auto_now_add's real-clock timestamps can tie at this resolution
        # for rapid-fire calls in a test — set them explicitly (via
        # .update(), which bypasses auto_now_add) so the ordering assertion
        # is deterministic, the same pattern PlatformStatsTests already
        # uses for Tenant.created_at.
        base = timezone.now()
        for i, summary in enumerate(["first", "second", "third"]):
            AuditService.record_critical(
                actor=self.staff, action="subscription.transitioned",
                target_type="Subscription", target_id=f"s{i}", summary=summary,
            )
            AuditEvent.objects.filter(summary=summary).update(
                created_at=base + timezone.timedelta(seconds=i)
            )

        resp = self.client.get(URL)
        summaries = [row["summary"] for row in resp.data["results"]]
        self.assertEqual(summaries, ["third", "second", "first"])

    def test_response_shape_includes_actor_and_never_a_password_or_raw_payload(self):
        AuditService.record_critical(
            actor=self.staff, action="subscription.transitioned",
            target_type="Subscription", target_id="s1", summary="…",
            metadata={"from_status": "ACTIVE", "to_status": "PAST_DUE"},
        )
        resp = self.client.get(URL)
        row = resp.data["results"][0]
        self.assertEqual(
            set(row.keys()),
            {
                "id", "actor", "action", "target_type", "target_id",
                "summary", "metadata", "is_critical", "created_at",
            },
        )
        self.assertEqual(row["actor"], {"id": str(self.staff.id), "email": self.staff.email})
        self.assertNotIn("password", str(resp.content))
        self.assertNotIn("raw_payload", str(resp.content))

    def test_actor_is_null_once_the_account_is_gone(self):
        AuditService.record_critical(
            actor=self.other_staff, action="subscription.transitioned",
            target_type="Subscription", target_id="s1", summary="…",
        )
        self.other_staff.delete()

        resp = self.client.get(URL)
        self.assertIsNone(resp.data["results"][0]["actor"])

    def test_pagination_page_size_is_25(self):
        for i in range(30):
            AuditService.record_critical(
                actor=self.staff, action="subscription.transitioned",
                target_type="Subscription", target_id=f"s{i}", summary=f"row {i}",
            )
        resp = self.client.get(URL)
        self.assertEqual(resp.data["count"], 30)
        self.assertEqual(len(resp.data["results"]), 25)
        self.assertIsNotNone(resp.data["next"])

        resp2 = self.client.get(URL, {"page": 2})
        self.assertEqual(len(resp2.data["results"]), 5)


class AuditLogFilterTests(AuditLogTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)
        AuditService.record_critical(
            actor=self.staff, action="subscription.transitioned",
            target_type="Subscription", target_id="s1", summary="critical by staff",
        )
        AuditService.record_observational(
            actor=self.other_staff, action="webhook.sweep_triggered",
            target_type="WebhookEvent", target_id="*", summary="observational by other",
        )

    def test_filter_by_actor(self):
        resp = self.client.get(URL, {"actor": str(self.staff.id)})
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["summary"], "critical by staff")

    def test_filter_by_malformed_actor_returns_empty_not_error(self):
        resp = self.client.get(URL, {"actor": "not-a-uuid"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["results"], [])

    def test_filter_by_action(self):
        resp = self.client.get(URL, {"action": "webhook.sweep_triggered"})
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["summary"], "observational by other")

    def test_filter_by_target_type(self):
        resp = self.client.get(URL, {"target_type": "Subscription"})
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["target_type"], "Subscription")

    def test_filter_by_is_critical_true(self):
        resp = self.client.get(URL, {"is_critical": "true"})
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertTrue(resp.data["results"][0]["is_critical"])

    def test_filter_by_is_critical_false(self):
        resp = self.client.get(URL, {"is_critical": "false"})
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertFalse(resp.data["results"][0]["is_critical"])

    def test_combining_filters(self):
        resp = self.client.get(
            URL, {"actor": str(self.staff.id), "target_type": "Subscription"}
        )
        self.assertEqual(len(resp.data["results"]), 1)

        resp2 = self.client.get(
            URL, {"actor": str(self.staff.id), "target_type": "WebhookEvent"}
        )
        self.assertEqual(resp2.data["results"], [])

"""
Phase 3 — plan & pricing management (docs/operator-control-plane-spec.md §B
"Plan management", master plan §3).

    POST  /api/platform/plans/                create
    PATCH /api/platform/plans/detail/?id=     edit / archive / restore
    POST  /api/platform/plans/sync/?id=       gateway sync

All Staff-tier. Real access tokens throughout — force_authenticate would
bypass TenantJWTAuthentication, which is exactly the code path these tests
need to exercise (these are GLOBAL_PATHS: no X-Tenant-ID is ever required,
and one sent for a foreign tenant must not change the outcome).

The gateway is never reached for real: PAYMENT_GATEWAY="mock" or a patched
`get_gateway`, per CLAUDE.md.
"""

from unittest import mock

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan, Subscription
from apps.billing.services import SubscriptionService
from apps.platform.models import AuditEvent
from apps.platform.services import PlanLocked, PlanManagementService
from apps.tenants.models import Tenant
from apps.users.models import User

LIST_URL = "/api/platform/plans/"
DETAIL_URL = "/api/platform/plans/detail/"
SYNC_URL = "/api/platform/plans/sync/"
PASSWORD = "correct-horse-staple-42"

VALID_CREATE = {
    "name": "Scale",
    "code": "SCALE",
    "price_cents": 19900,
    "currency": "USD",
    "interval": "MONTHLY",
}


class PlanManagementTestBase(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.root = User.objects.create_user(
            email="root@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.ordinary = User.objects.create_user(
            email="normal@example.com", password=PASSWORD
        )

        # Unsynced: every field is still editable.
        self.draft = Plan.objects.create(
            name="Draft", code="DRAFT", price_cents=1000, currency="USD"
        )
        # Synced: `external_plan_id` set, so the money/identity fields are
        # locked (spec §B "external_plan_id as a platform-level lock marker").
        self.locked = Plan.objects.create(
            name="Pro",
            code="PRO",
            price_cents=2900,
            currency="USD",
            external_plan_id="ext_plan_pro",
        )

    def _auth(self, user, tenant_id=None):
        creds = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}
        if tenant_id is not None:
            creds["HTTP_X_TENANT_ID"] = str(tenant_id)
        self.client.credentials(**creds)

    def _detail(self, plan_id):
        return f"{DETAIL_URL}?id={plan_id}"

    def _sync(self, plan_id):
        return f"{SYNC_URL}?id={plan_id}"


class PlanManagementPermissionTests(PlanManagementTestBase):
    """The permission matrix, per endpoint: 401 unauthenticated, 403 for an
    ordinary authenticated user, 200/201 for Staff. Plan management is
    Staff-tier — Root is allowed because Root is also Staff, never because
    these endpoints check for it."""

    def test_create_unauthenticated_is_401(self):
        resp = self.client.post(LIST_URL, VALID_CREATE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_ordinary_user_is_403(self):
        self._auth(self.ordinary)
        resp = self.client.post(LIST_URL, VALID_CREATE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Plan.objects.filter(code="SCALE").exists())

    def test_create_staff_is_201(self):
        self._auth(self.staff)
        resp = self.client.post(LIST_URL, VALID_CREATE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_create_root_is_also_allowed_this_is_staff_tier(self):
        self._auth(self.root)
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "code": "ROOTMADE"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_patch_unauthenticated_is_401(self):
        resp = self.client.patch(
            self._detail(self.draft.id), {"name": "X"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_ordinary_user_is_403_and_changes_nothing(self):
        self._auth(self.ordinary)
        resp = self.client.patch(
            self._detail(self.draft.id), {"name": "Hijacked"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.name, "Draft")

    def test_patch_staff_is_200(self):
        self._auth(self.staff)
        resp = self.client.patch(
            self._detail(self.draft.id), {"name": "Draft II"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_sync_unauthenticated_is_401(self):
        resp = self.client.post(self._sync(self.draft.id))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sync_ordinary_user_is_403_and_never_reaches_the_gateway(self):
        self._auth(self.ordinary)
        with mock.patch("apps.billing.services.get_gateway") as gateway:
            resp = self.client.post(self._sync(self.draft.id))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        gateway.assert_not_called()
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.external_plan_id)

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_sync_staff_is_200(self):
        self._auth(self.staff)
        resp = self.client.post(self._sync(self.draft.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_x_tenant_id_for_a_foreign_tenant_does_not_change_the_outcome(self):
        # Global paths: TenantJWTAuthentication returns before resolving
        # X-Tenant-ID / Membership, so a header naming a tenant the operator
        # isn't a member of must not 400/403 on any of the three endpoints.
        other = Tenant.objects.create(name="Other", slug="other")
        self._auth(self.staff, tenant_id=other.id)

        self.assertEqual(
            self.client.post(LIST_URL, VALID_CREATE, format="json").status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            self.client.patch(
                self._detail(self.draft.id), {"name": "Draft II"}, format="json"
            ).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.post(self._sync(self.draft.id)).status_code,
            status.HTTP_200_OK,
        )


class PlanLookupTests(PlanManagementTestBase):
    """A malformed or missing id must read as "not found", never a 500 — the
    same collapse apps.platform.utils.parse_uuid_or_none already applies to
    every other detail view on this surface."""

    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_patch_nonexistent_plan_is_404(self):
        resp = self.client.patch(
            self._detail("00000000-0000-0000-0000-000000000000"),
            {"name": "X"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_malformed_id_is_404_not_500(self):
        resp = self.client.patch(
            f"{DETAIL_URL}?id=not-a-uuid", {"name": "X"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_missing_id_is_404(self):
        resp = self.client.patch(DETAIL_URL, {"name": "X"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_sync_nonexistent_plan_is_404(self):
        resp = self.client.post(
            self._sync("00000000-0000-0000-0000-000000000000")
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_sync_malformed_id_is_404_not_500(self):
        resp = self.client.post(f"{SYNC_URL}?id=not-a-uuid")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_sync_missing_id_is_404(self):
        resp = self.client.post(SYNC_URL)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PlanCreateTests(PlanManagementTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_creates_the_plan_and_returns_the_read_shape(self):
        resp = self.client.post(LIST_URL, VALID_CREATE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        plan = Plan.objects.get(code="SCALE")
        self.assertEqual(plan.name, "Scale")
        self.assertEqual(plan.price_cents, 19900)
        self.assertEqual(plan.interval, Plan.Interval.MONTHLY)
        # Same field set as GET — including the annotation, so the UI can
        # render a created plan without a second request.
        self.assertEqual(
            set(resp.data),
            {
                "id",
                "name",
                "code",
                "price_cents",
                "currency",
                "interval",
                "is_active",
                "external_plan_id",
                "subscriber_count",
            },
        )
        self.assertEqual(resp.data["subscriber_count"], 0)

    def test_new_plan_is_active_and_unsynced_and_the_client_cannot_say_otherwise(self):
        resp = self.client.post(
            LIST_URL,
            {**VALID_CREATE, "is_active": False, "external_plan_id": "ext_forged"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        plan = Plan.objects.get(code="SCALE")
        self.assertTrue(plan.is_active)
        self.assertIsNone(plan.external_plan_id)

    def test_creating_a_plan_makes_no_gateway_call(self):
        with mock.patch("apps.billing.services.get_gateway") as gateway:
            resp = self.client.post(LIST_URL, VALID_CREATE, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        gateway.assert_not_called()

    def test_duplicate_code_is_a_field_error_not_a_500(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "code": "PRO"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", resp.data)
        self.assertEqual(Plan.objects.filter(code="PRO").count(), 1)

    def test_duplicate_code_differing_only_in_case_is_rejected(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "code": "pro"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", resp.data)

    def test_code_is_normalized_to_upper_case(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "code": "scale_annual"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Plan.objects.filter(code="SCALE_ANNUAL").exists())

    def test_code_with_illegal_characters_is_rejected(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "code": "bad code!"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", resp.data)

    def test_blank_name_is_rejected(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "name": "   "}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", resp.data)

    def test_negative_price_is_rejected(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "price_cents": -1}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price_cents", resp.data)

    def test_zero_price_is_allowed(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "price_cents": 0}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_non_integer_price_is_rejected_never_coerced_from_a_float(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "price_cents": 19.99}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price_cents", resp.data)

    def test_bad_currency_is_rejected(self):
        for bad in ("US", "USDD", "12$"):
            with self.subTest(currency=bad):
                resp = self.client.post(
                    LIST_URL, {**VALID_CREATE, "currency": bad}, format="json"
                )
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bad_interval_is_rejected(self):
        resp = self.client.post(
            LIST_URL, {**VALID_CREATE, "interval": "WEEKLY"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interval", resp.data)

    def test_missing_fields_are_rejected(self):
        resp = self.client.post(LIST_URL, {"name": "Only a name"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejected_create_writes_no_plan_and_no_audit_row(self):
        self.client.post(LIST_URL, {"name": "Only a name"}, format="json")
        self.assertEqual(Plan.objects.count(), 2)  # the two from setUp
        self.assertEqual(AuditEvent.objects.count(), 0)


class PlanEditTests(PlanManagementTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_every_field_is_editable_before_the_plan_is_synced(self):
        resp = self.client.patch(
            self._detail(self.draft.id),
            {
                "name": "Draft II",
                "code": "DRAFT2",
                "price_cents": 4200,
                "currency": "EUR",
                "interval": "ANNUAL",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.name, "Draft II")
        self.assertEqual(self.draft.code, "DRAFT2")
        self.assertEqual(self.draft.price_cents, 4200)
        self.assertEqual(self.draft.currency, "EUR")
        self.assertEqual(self.draft.interval, "ANNUAL")

    def test_name_is_editable_on_a_synced_plan(self):
        resp = self.client.patch(
            self._detail(self.locked.id), {"name": "Pro (renamed)"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.locked.refresh_from_db()
        self.assertEqual(self.locked.name, "Pro (renamed)")

    def test_empty_patch_is_rejected(self):
        resp = self.client.patch(self._detail(self.draft.id), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_body_keys_are_ignored_not_bound(self):
        resp = self.client.patch(
            self._detail(self.draft.id),
            {"name": "Draft II", "is_staff": True, "subscriber_count": 99},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.name, "Draft II")

    def test_external_plan_id_can_never_be_set_from_a_request_body(self):
        resp = self.client.patch(
            self._detail(self.draft.id),
            {"external_plan_id": "ext_forged"},
            format="json",
        )
        # No recognized field in the body at all -> rejected as empty.
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.external_plan_id)

    def test_external_plan_id_can_never_be_replaced_from_a_request_body(self):
        resp = self.client.patch(
            self._detail(self.locked.id),
            {"name": "Pro", "external_plan_id": "ext_forged"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.locked.refresh_from_db()
        self.assertEqual(self.locked.external_plan_id, "ext_plan_pro")

    def test_duplicate_code_on_edit_is_a_field_error(self):
        resp = self.client.patch(
            self._detail(self.draft.id), {"code": "PRO"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", resp.data)

    def test_resubmitting_a_plans_own_code_is_not_a_duplicate(self):
        resp = self.client.patch(
            self._detail(self.draft.id),
            {"code": "DRAFT", "name": "Draft II"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_a_no_op_edit_changes_nothing_and_records_nothing(self):
        resp = self.client.patch(
            self._detail(self.draft.id), {"name": "Draft"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditEvent.objects.count(), 0)


class PlanImmutabilityTests(PlanManagementTestBase):
    """docs/operator-control-plane-spec.md §B: once `external_plan_id` is set,
    only `name` and `is_active` may change. Platform policy, enforced
    server-side regardless of what the configured adapter's provider would
    technically allow."""

    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_price_change_on_a_synced_plan_is_rejected_and_row_is_unchanged(self):
        resp = self.client.patch(
            self._detail(self.locked.id), {"price_cents": 100}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price_cents", resp.data)
        self.locked.refresh_from_db()
        self.assertEqual(self.locked.price_cents, 2900)

    def test_currency_interval_and_code_are_locked_too(self):
        for field, value in (
            ("currency", "EUR"),
            ("interval", "ANNUAL"),
            ("code", "PRO_V2"),
        ):
            with self.subTest(field=field):
                resp = self.client.patch(
                    self._detail(self.locked.id), {field: value}, format="json"
                )
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, resp.data)

    def test_a_locked_field_alongside_a_mutable_one_rejects_the_whole_request(self):
        resp = self.client.patch(
            self._detail(self.locked.id),
            {"name": "Pro (renamed)", "price_cents": 100},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.locked.refresh_from_db()
        self.assertEqual(self.locked.name, "Pro")
        self.assertEqual(self.locked.price_cents, 2900)

    def test_every_locked_field_is_named_in_the_error(self):
        resp = self.client.patch(
            self._detail(self.locked.id),
            {"price_cents": 100, "currency": "EUR"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price_cents", resp.data)
        self.assertIn("currency", resp.data)

    def test_a_rejected_locked_edit_writes_no_audit_row(self):
        self.client.patch(
            self._detail(self.locked.id), {"price_cents": 100}, format="json"
        )
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_the_service_itself_refuses_a_locked_field_not_only_the_view(self):
        with self.assertRaises(PlanLocked):
            PlanManagementService.update_plan(
                actor=self.staff, plan=self.locked, changes={"price_cents": 1}
            )
        self.locked.refresh_from_db()
        self.assertEqual(self.locked.price_cents, 2900)


class PlanArchiveTests(PlanManagementTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        start, end = SubscriptionService.default_period(self.locked)
        self.subscription = SubscriptionService.create_subscription(
            self.tenant, self.locked, start, end
        )

    def test_archiving_deactivates_the_plan(self):
        resp = self.client.patch(
            self._detail(self.locked.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.locked.refresh_from_db()
        self.assertFalse(self.locked.is_active)

    def test_archiving_is_allowed_on_a_synced_plan(self):
        # `is_active` is one of the two fields that stay mutable when locked.
        resp = self.client.patch(
            self._detail(self.locked.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_archiving_preserves_historical_billing_data(self):
        self.client.patch(
            self._detail(self.locked.id), {"is_active": False}, format="json"
        )
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_id, self.locked.id)
        self.assertTrue(Plan.objects.filter(pk=self.locked.pk).exists())

    def test_an_archived_plan_can_be_restored(self):
        self.client.patch(
            self._detail(self.locked.id), {"is_active": False}, format="json"
        )
        resp = self.client.patch(
            self._detail(self.locked.id), {"is_active": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.locked.refresh_from_db()
        self.assertTrue(self.locked.is_active)

    def test_there_is_no_delete_capability(self):
        resp = self.client.delete(self._detail(self.locked.id))
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Plan.objects.filter(pk=self.locked.pk).exists())

    def test_an_archived_plan_is_no_longer_offered_to_tenants(self):
        self.client.patch(
            self._detail(self.locked.id), {"is_active": False}, format="json"
        )
        # The tenant-facing catalogue only ever lists active plans; this is
        # what "archive" means operationally.
        self.assertFalse(
            Plan.objects.filter(pk=self.locked.pk, is_active=True).exists()
        )


@override_settings(PAYMENT_GATEWAY="mock")
class PlanGatewaySyncTests(PlanManagementTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_sync_stores_the_external_plan_id_the_adapter_returned(self):
        resp = self.client.post(self._sync(self.draft.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.draft.refresh_from_db()
        # MockGatewayAdapter.create_plan -> f"mock_plan_{plan.code}"
        self.assertEqual(self.draft.external_plan_id, "mock_plan_DRAFT")
        self.assertEqual(resp.data["external_plan_id"], "mock_plan_DRAFT")
        self.assertTrue(resp.data["created"])

    def test_sync_goes_through_the_adapter_boundary_not_a_provider_sdk(self):
        # The view must reach the gateway only via the reused
        # PlanSyncService -> get_gateway() path (CLAUDE.md: the billing domain
        # never imports a provider SDK directly).
        with mock.patch("apps.billing.services.get_gateway") as get_gateway:
            get_gateway.return_value.create_plan.return_value = "ext_from_adapter"
            resp = self.client.post(self._sync(self.draft.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        get_gateway.return_value.create_plan.assert_called_once()
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.external_plan_id, "ext_from_adapter")

    def test_syncing_an_already_synced_plan_is_a_no_op_not_a_second_gateway_plan(self):
        with mock.patch("apps.billing.services.get_gateway") as get_gateway:
            resp = self.client.post(self._sync(self.locked.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["created"])
        get_gateway.assert_not_called()
        self.locked.refresh_from_db()
        self.assertEqual(self.locked.external_plan_id, "ext_plan_pro")

    def test_a_double_clicked_sync_never_replaces_the_external_plan_id(self):
        self.client.post(self._sync(self.draft.id))
        self.draft.refresh_from_db()
        first = self.draft.external_plan_id
        self.client.post(self._sync(self.draft.id))
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.external_plan_id, first)

    def test_gateway_failure_is_a_502_with_a_generic_message(self):
        with mock.patch("apps.billing.services.get_gateway") as get_gateway:
            get_gateway.return_value.create_plan.side_effect = RuntimeError(
                "provider said: card network key sk_live_SECRET rejected"
            )
            with self.assertLogs("apps.platform.views", level="ERROR"):
                resp = self.client.post(self._sync(self.draft.id))

        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertNotIn("sk_live_SECRET", str(resp.data))
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.external_plan_id)

    def test_gateway_failure_leaves_the_plan_unsynced_and_records_no_success(self):
        with mock.patch("apps.billing.services.get_gateway") as get_gateway:
            get_gateway.return_value.create_plan.side_effect = RuntimeError("boom")
            with self.assertLogs("apps.platform.views", level="ERROR"):
                self.client.post(self._sync(self.draft.id))

        self.assertFalse(AuditEvent.objects.filter(action="plan.synced").exists())
        self.assertFalse(
            AuditEvent.objects.filter(action="plan.sync_failed", is_critical=True).exists()
        )


class PlanAuditTests(PlanManagementTestBase):
    """Every critical mutation writes exactly one AuditEvent with
    is_critical=True, atomically with the change it describes."""

    def setUp(self):
        super().setUp()
        self._auth(self.staff)

    def test_create_writes_one_critical_audit_row(self):
        self.client.post(LIST_URL, VALID_CREATE, format="json")
        self.assertEqual(AuditEvent.objects.count(), 1)
        event = AuditEvent.objects.get()
        self.assertTrue(event.is_critical)
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.action, "plan.created")
        self.assertEqual(event.target_type, "Plan")
        self.assertEqual(event.target_id, str(Plan.objects.get(code="SCALE").id))
        self.assertEqual(event.metadata["price_cents"], 19900)

    def test_edit_writes_one_critical_audit_row_with_before_and_after(self):
        self.client.patch(
            self._detail(self.draft.id), {"price_cents": 5000}, format="json"
        )
        event = AuditEvent.objects.get()
        self.assertTrue(event.is_critical)
        self.assertEqual(event.action, "plan.updated")
        self.assertEqual(event.metadata["before"]["price_cents"], 1000)
        self.assertEqual(event.metadata["after"]["price_cents"], 5000)

    def test_archive_and_restore_get_their_own_action_names(self):
        self.client.patch(
            self._detail(self.draft.id), {"is_active": False}, format="json"
        )
        self.assertEqual(AuditEvent.objects.latest("created_at").action, "plan.archived")
        self.client.patch(
            self._detail(self.draft.id), {"is_active": True}, format="json"
        )
        self.assertEqual(AuditEvent.objects.latest("created_at").action, "plan.restored")

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_sync_writes_one_critical_audit_row(self):
        self.client.post(self._sync(self.draft.id))
        event = AuditEvent.objects.get(action="plan.synced")
        self.assertTrue(event.is_critical)
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.target_id, str(self.draft.id))
        self.assertEqual(event.metadata["external_plan_id"], "mock_plan_DRAFT")

    def test_a_failed_sync_writes_an_observational_row_naming_no_provider_detail(self):
        with mock.patch("apps.billing.services.get_gateway") as get_gateway:
            get_gateway.return_value.create_plan.side_effect = RuntimeError(
                "gateway key sk_live_SECRET is invalid"
            )
            with self.assertLogs("apps.platform.views", level="ERROR"):
                self.client.post(self._sync(self.draft.id))

        event = AuditEvent.objects.get(action="plan.sync_failed")
        self.assertFalse(event.is_critical)
        self.assertEqual(event.metadata["error_type"], "RuntimeError")
        self.assertNotIn("sk_live_SECRET", str(event.metadata))
        self.assertNotIn("sk_live_SECRET", event.summary)

    def test_audit_metadata_never_carries_a_secret_or_a_raw_payload(self):
        self.client.post(LIST_URL, VALID_CREATE, format="json")
        self.client.patch(
            self._detail(self.draft.id), {"price_cents": 5000}, format="json"
        )
        forbidden = {"password", "secret", "token", "razorpay_key_secret", "raw_payload"}
        for event in AuditEvent.objects.all():
            self.assertFalse(forbidden & set(event.metadata.keys()))

    def test_audit_write_failure_rolls_back_the_plan_creation(self):
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(LIST_URL, VALID_CREATE, format="json")

        self.assertFalse(Plan.objects.filter(code="SCALE").exists())
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_audit_write_failure_rolls_back_a_plan_edit(self):
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.patch(
                    self._detail(self.draft.id), {"price_cents": 5000}, format="json"
                )

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.price_cents, 1000)
        self.assertEqual(AuditEvent.objects.count(), 0)


class PlanManagementIsolationTests(PlanManagementTestBase):
    """Plan management must not disturb the tenant-facing catalogue contract:
    /api/plans/ still lists active plans only, for any member, unchanged."""

    def test_tenant_facing_plan_list_still_only_returns_active_plans(self):
        self._auth(self.staff)
        self.client.post(
            LIST_URL, {**VALID_CREATE, "code": "NEWONE"}, format="json"
        )
        self.client.patch(
            self._detail(self.locked.id), {"is_active": False}, format="json"
        )

        member = User.objects.create_user(email="m@example.com", password=PASSWORD)
        self._auth(member)
        resp = self.client.get("/api/plans/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = {row["code"] for row in resp.data}
        self.assertIn("NEWONE", codes)
        self.assertNotIn("PRO", codes)

    def test_an_operator_created_plan_is_usable_by_the_subscription_domain(self):
        self._auth(self.staff)
        self.client.post(LIST_URL, VALID_CREATE, format="json")
        plan = Plan.objects.get(code="SCALE")

        tenant = Tenant.objects.create(name="Acme", slug="acme")
        start, end = SubscriptionService.default_period(plan)
        sub = SubscriptionService.create_subscription(tenant, plan, start, end)
        self.assertEqual(sub.status, Subscription.Status.TRIALING)
        self.assertEqual(sub.plan_id, plan.id)

"""
Phase 4 — Root controls (docs/operator-control-plane-spec.md §B/§E, master
plan §4).

    PATCH /api/platform/users/detail/?id=       Root-only role management
    GET   /api/platform/webhook-events/raw/?id= Root-only raw gateway payload

The spec calls role management "the single highest-leverage endpoint in this
design... warranting disproportionate test coverage relative to its size", so
this module covers it disproportionately: the permission matrix, the
last-root invariant from every direction, self-demotion, what the endpoint
refuses to touch at all, and the audit row.

Real access tokens throughout, per this codebase's convention — never
force_authenticate, which would bypass TenantJWTAuthentication.
"""

import json
import threading

from django.db import connection, connections
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.gateway.base import EventType
from apps.billing.models import Subscription, WebhookEvent
from apps.billing.services import SubscriptionService
from apps.platform.models import AuditEvent
from apps.platform.permissions import ROOT_Q, is_platform_root
from apps.platform.services import LastRootProtected, UserRoleService
from apps.tenants.models import Tenant
from apps.users.models import User

USERS_URL = "/api/platform/users/detail/"
RAW_URL = "/api/platform/webhook-events/raw/"
EVENT_DETAIL_URL = "/api/platform/webhook-events/detail/"
PASSWORD = "correct-horse-staple-42"

# A payload shaped like a real gateway one: it carries customer contact
# information, which is exactly why the raw read is Root-gated.
RAW_PAYLOAD = {
    "event": "subscription.charged",
    "payload": {
        "subscription": {"entity": {"id": "sub_ext_1", "status": "active"}},
        "payment": {
            "entity": {
                "id": "pay_1",
                "email": "customer@example.com",
                "contact": "+15550001111",
                "card": {"last4": "4242", "network": "Visa"},
            }
        },
    },
}


def _url(base, obj_id):
    return f"{base}?id={obj_id}"


class RootControlsTestBase(APITestCase):
    def setUp(self):
        self.root = User.objects.create_user(
            email="root@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.ordinary = User.objects.create_user(
            email="normal@example.com", password=PASSWORD
        )

    def _auth(self, user, tenant_id=None):
        creds = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}
        if tenant_id is not None:
            creds["HTTP_X_TENANT_ID"] = str(tenant_id)
        self.client.credentials(**creds)


class RootPredicateTests(RootControlsTestBase):
    """The Python predicate and the ORM Q are two shapes of one rule. If they
    ever disagree, either the platform locks itself out or the last Root can be
    demoted — so they are asserted to agree on every combination."""

    def test_predicate_and_query_agree_on_every_flag_combination(self):
        combos = [
            (staff, superuser, active)
            for staff in (True, False)
            for superuser in (True, False)
            for active in (True, False)
        ]
        for index, (staff, superuser, active) in enumerate(combos):
            with self.subTest(is_staff=staff, is_superuser=superuser, is_active=active):
                user = User.objects.create_user(
                    email=f"combo{index}@example.com",
                    password=PASSWORD,
                    is_staff=staff,
                    is_superuser=superuser,
                    is_active=active,
                )
                by_query = User.objects.filter(ROOT_Q, pk=user.pk).exists()
                self.assertEqual(is_platform_root(user), by_query)
                self.assertEqual(by_query, staff and superuser and active)

    def test_a_superuser_without_is_staff_is_not_root(self):
        user = User.objects.create_user(
            email="halfroot@example.com", password=PASSWORD, is_superuser=True
        )
        self.assertFalse(is_platform_root(user))


class RoleManagementPermissionTests(RootControlsTestBase):
    def test_unauthenticated_is_401(self):
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ordinary_user_is_403_and_changes_nothing(self):
        self._auth(self.ordinary)
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.ordinary.refresh_from_db()
        self.assertFalse(self.ordinary.is_staff)

    def test_staff_without_superuser_is_403(self):
        # The whole point of the two tiers: a Staff operator runs the control
        # plane but cannot change who has power.
        self._auth(self.staff)
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.ordinary.refresh_from_db()
        self.assertFalse(self.ordinary.is_staff)

    def test_staff_cannot_escalate_by_patching_their_own_row(self):
        self._auth(self.staff)
        resp = self.client.patch(
            _url(USERS_URL, self.staff.id), {"is_superuser": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_superuser)

    def test_a_superuser_missing_is_staff_is_not_root_at_the_boundary(self):
        half = User.objects.create_user(
            email="half@example.com", password=PASSWORD, is_superuser=True
        )
        self._auth(half)
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_root_is_allowed(self):
        self._auth(self.root)
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_the_read_on_the_same_path_stays_staff_tier(self):
        # One path, two tiers: PATCH is Root, GET is unchanged Staff.
        self._auth(self.staff)
        self.assertEqual(
            self.client.get(_url(USERS_URL, self.ordinary.id)).status_code,
            status.HTTP_200_OK,
        )

    def test_x_tenant_id_for_a_foreign_tenant_does_not_change_the_outcome(self):
        other = Tenant.objects.create(name="Other", slug="other")
        self._auth(self.root, tenant_id=other.id)
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class RoleManagementLookupTests(RootControlsTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.root)

    def test_nonexistent_target_is_404(self):
        resp = self.client.patch(
            _url(USERS_URL, "00000000-0000-0000-0000-000000000000"),
            {"is_staff": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_malformed_target_id_is_404_not_500(self):
        resp = self.client.patch(
            f"{USERS_URL}?id=not-a-uuid", {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_target_id_is_404(self):
        resp = self.client.patch(USERS_URL, {"is_staff": True}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_id_belonging_to_another_model_is_404(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        resp = self.client.patch(
            _url(USERS_URL, tenant.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class RoleManagementContractTests(RootControlsTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.root)

    def test_empty_body_is_rejected(self):
        resp = self.client.patch(_url(USERS_URL, self.ordinary.id), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_promotes_to_staff(self):
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ordinary.refresh_from_db()
        self.assertTrue(self.ordinary.is_staff)
        self.assertFalse(self.ordinary.is_superuser)

    def test_promotes_to_root_with_both_flags_in_one_request(self):
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id),
            {"is_staff": True, "is_superuser": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ordinary.refresh_from_db()
        self.assertTrue(is_platform_root(self.ordinary))

    def test_demotes_staff(self):
        resp = self.client.patch(
            _url(USERS_URL, self.staff.id), {"is_staff": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_staff)

    def test_deactivates_an_operator(self):
        resp = self.client.patch(
            _url(USERS_URL, self.staff.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)

    def test_never_touches_identity_or_credentials(self):
        password_before = User.objects.get(pk=self.ordinary.pk).password
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id),
            {
                "is_staff": True,
                "email": "hijacked@example.com",
                "password": "new-password-attempt",
                "email_verified": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ordinary.refresh_from_db()
        self.assertEqual(self.ordinary.email, "normal@example.com")
        self.assertEqual(self.ordinary.password, password_before)
        # email_verified has exactly one legitimate writer, and it is not this.
        self.assertFalse(self.ordinary.email_verified)

    def test_response_never_contains_a_password_hash(self):
        resp = self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertNotIn("password", resp.data)
        self.assertNotIn("password", json.dumps(resp.data, default=str).lower())

    def test_a_no_op_change_records_nothing(self):
        resp = self.client.patch(
            _url(USERS_URL, self.staff.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditEvent.objects.count(), 0)


class LastRootInvariantTests(RootControlsTestBase):
    """docs/operator-control-plane-spec.md §E: no mutation may result in zero
    users satisfying is_staff AND is_superuser AND is_active."""

    def setUp(self):
        super().setUp()
        self._auth(self.root)

    def _assert_still_root(self):
        self.root.refresh_from_db()
        self.assertTrue(is_platform_root(self.root))
        self.assertEqual(User.objects.filter(ROOT_Q).count(), 1)

    def test_the_only_root_cannot_drop_is_superuser(self):
        resp = self.client.patch(
            _url(USERS_URL, self.root.id), {"is_superuser": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_still_root()

    def test_the_only_root_cannot_drop_is_staff(self):
        resp = self.client.patch(
            _url(USERS_URL, self.root.id), {"is_staff": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_still_root()

    def test_the_only_root_cannot_be_deactivated(self):
        resp = self.client.patch(
            _url(USERS_URL, self.root.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_still_root()

    def test_the_only_root_cannot_be_stripped_of_everything_at_once(self):
        resp = self.client.patch(
            _url(USERS_URL, self.root.id),
            {"is_staff": False, "is_superuser": False, "is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_still_root()

    def test_a_refused_demotion_writes_no_audit_row(self):
        self.client.patch(
            _url(USERS_URL, self.root.id), {"is_superuser": False}, format="json"
        )
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_a_root_may_demote_itself_once_another_root_exists(self):
        other = User.objects.create_user(
            email="root2@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        resp = self.client.patch(
            _url(USERS_URL, self.root.id), {"is_superuser": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.root.refresh_from_db()
        self.assertFalse(is_platform_root(self.root))
        self.assertTrue(is_platform_root(other))

    def test_a_root_may_demote_another_root_while_one_remains(self):
        other = User.objects.create_user(
            email="root2@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        resp = self.client.patch(
            _url(USERS_URL, other.id), {"is_superuser": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.filter(ROOT_Q).count(), 1)

    def test_demoting_the_second_to_last_then_the_last_root_is_refused_at_the_end(self):
        other = User.objects.create_user(
            email="root2@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.assertEqual(
            self.client.patch(
                _url(USERS_URL, other.id), {"is_superuser": False}, format="json"
            ).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.patch(
                _url(USERS_URL, self.root.id), {"is_superuser": False}, format="json"
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(User.objects.filter(ROOT_Q).count(), 1)

    def test_an_inactive_superuser_does_not_count_as_a_remaining_root(self):
        User.objects.create_user(
            email="dormant@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
            is_active=False,
        )
        resp = self.client.patch(
            _url(USERS_URL, self.root.id), {"is_superuser": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_still_root()

    def test_the_invariant_transitively_keeps_at_least_one_staff_account(self):
        # A qualifying Root is always also Staff, so "never zero Roots"
        # implies "never zero Staff" — no separate last-staff rule needed.
        self.client.patch(
            _url(USERS_URL, self.staff.id), {"is_staff": False}, format="json"
        )
        self.client.patch(
            _url(USERS_URL, self.root.id), {"is_staff": False}, format="json"
        )
        self.assertGreaterEqual(User.objects.filter(is_staff=True, is_active=True).count(), 1)

    def test_the_service_itself_enforces_the_invariant_not_only_the_view(self):
        with self.assertRaises(LastRootProtected):
            UserRoleService.update_roles(
                actor=self.root, user=self.root, changes={"is_superuser": False}
            )
        self._assert_still_root()

    def test_active_root_count_reports_the_real_number(self):
        self.assertEqual(UserRoleService.active_root_count(), 1)
        User.objects.create_user(
            email="root2@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.assertEqual(UserRoleService.active_root_count(), 2)


class RoleManagementAuditTests(RootControlsTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.root)

    def test_a_role_change_writes_exactly_one_critical_audit_row(self):
        self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        self.assertEqual(AuditEvent.objects.count(), 1)
        event = AuditEvent.objects.get()
        self.assertTrue(event.is_critical)
        self.assertEqual(event.actor, self.root)
        self.assertEqual(event.action, "user.roles_changed")
        self.assertEqual(event.target_type, "User")
        self.assertEqual(event.target_id, str(self.ordinary.id))
        self.assertEqual(event.metadata["before"]["is_staff"], False)
        self.assertEqual(event.metadata["after"]["is_staff"], True)

    def test_the_audit_row_attributes_the_actor_not_the_target(self):
        self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        event = AuditEvent.objects.get()
        self.assertEqual(event.actor_id, self.root.id)
        self.assertNotEqual(event.actor_id, self.ordinary.id)

    def test_a_self_change_is_marked_as_such(self):
        User.objects.create_user(
            email="root2@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client.patch(
            _url(USERS_URL, self.root.id), {"is_superuser": False}, format="json"
        )
        event = AuditEvent.objects.get()
        self.assertTrue(event.metadata["self_change"])

    def test_audit_metadata_never_carries_a_password_or_secret(self):
        self.client.patch(
            _url(USERS_URL, self.ordinary.id), {"is_staff": True}, format="json"
        )
        event = AuditEvent.objects.get()
        forbidden = {"password", "secret", "token", "raw_payload"}
        self.assertFalse(forbidden & set(event.metadata.keys()))
        self.assertNotIn("password", json.dumps(event.metadata).lower())


class RawWebhookPayloadTests(RootControlsTestBase):
    def setUp(self):
        super().setUp()
        self.event = WebhookEvent.objects.create(
            external_event_id="evt_1",
            external_subscription_id="sub_ext_1",
            event_type=EventType.CHARGED,
            raw_payload=RAW_PAYLOAD,
        )

    def test_unauthenticated_is_401(self):
        resp = self.client.get(_url(RAW_URL, self.event.id))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ordinary_user_is_403(self):
        self._auth(self.ordinary)
        resp = self.client.get(_url(RAW_URL, self.event.id))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_without_superuser_is_403_and_sees_no_payload(self):
        self._auth(self.staff)
        resp = self.client.get(_url(RAW_URL, self.event.id))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("customer@example.com", json.dumps(resp.data, default=str))

    def test_root_gets_the_raw_payload(self):
        self._auth(self.root)
        resp = self.client.get(_url(RAW_URL, self.event.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["raw_payload"], RAW_PAYLOAD)

    def test_the_raw_read_still_carries_every_normalized_field(self):
        self._auth(self.root)
        resp = self.client.get(_url(RAW_URL, self.event.id))
        for field in (
            "id",
            "external_event_id",
            "event_type",
            "external_subscription_id",
            "tenant",
            "received_at",
            "processed",
        ):
            self.assertIn(field, resp.data)

    def test_the_raw_read_resolves_the_tenant_like_the_sanitized_one(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme")
        from apps.billing.models import Plan

        plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        start, end = SubscriptionService.default_period(plan)
        SubscriptionService.create_subscription(
            tenant, plan, start, end, external_subscription_id="sub_ext_1"
        )
        self._auth(self.root)
        resp = self.client.get(_url(RAW_URL, self.event.id))
        self.assertEqual(resp.data["tenant"]["slug"], "acme")

    def test_the_sanitized_detail_read_still_never_exposes_the_payload(self):
        # Phase 4 must not widen the Staff-tier surface it sits beside.
        self._auth(self.staff)
        resp = self.client.get(_url(EVENT_DETAIL_URL, self.event.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("raw_payload", resp.data)
        self.assertNotIn("customer@example.com", json.dumps(resp.data, default=str))

    def test_root_reading_the_sanitized_detail_still_gets_no_payload(self):
        self._auth(self.root)
        resp = self.client.get(_url(EVENT_DETAIL_URL, self.event.id))
        self.assertNotIn("raw_payload", resp.data)

    def test_nonexistent_event_is_404(self):
        self._auth(self.root)
        resp = self.client.get(
            _url(RAW_URL, "00000000-0000-0000-0000-000000000000")
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_malformed_id_is_404_not_500(self):
        self._auth(self.root)
        resp = self.client.get(f"{RAW_URL}?id=not-a-uuid")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_viewing_writes_an_observational_audit_row(self):
        self._auth(self.root)
        self.client.get(_url(RAW_URL, self.event.id))
        event = AuditEvent.objects.get(action="webhook.raw_payload_viewed")
        self.assertFalse(event.is_critical)
        self.assertEqual(event.actor, self.root)
        self.assertEqual(event.target_id, str(self.event.id))

    def test_the_audit_row_never_contains_any_part_of_the_payload(self):
        self._auth(self.root)
        self.client.get(_url(RAW_URL, self.event.id))
        event = AuditEvent.objects.get(action="webhook.raw_payload_viewed")
        recorded = json.dumps(event.metadata) + event.summary
        self.assertNotIn("customer@example.com", recorded)
        self.assertNotIn("4242", recorded)
        self.assertNotIn("+15550001111", recorded)

    def test_a_refused_read_records_nothing(self):
        self._auth(self.staff)
        self.client.get(_url(RAW_URL, self.event.id))
        self.assertEqual(AuditEvent.objects.count(), 0)


class LastRootConcurrencyTests(TransactionTestCase):
    """
    The invariant is a check-then-act, so it is only true if concurrent role
    mutations serialize. Two Roots demoting each other at the same time is the
    exact race: without the row lock in UserRoleService.update_roles both
    transactions see the other still qualifying and both commit, leaving zero.

    TransactionTestCase (not APITestCase) because this needs real committed
    transactions across two database connections.
    """

    def setUp(self):
        self.root_a = User.objects.create_user(
            email="roota@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.root_b = User.objects.create_user(
            email="rootb@example.com",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )

    def test_two_simultaneous_demotions_cannot_leave_zero_roots(self):
        barrier = threading.Barrier(2, timeout=10)
        errors = []

        def demote(actor, target):
            try:
                barrier.wait()
                UserRoleService.update_roles(
                    actor=actor, user=target, changes={"is_superuser": False}
                )
            except LastRootProtected:
                errors.append("refused")
            except threading.BrokenBarrierError:
                errors.append("barrier")
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=demote, args=(self.root_a, self.root_a)),
            threading.Thread(target=demote, args=(self.root_b, self.root_b)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        with connection.cursor():
            pass
        self.assertGreaterEqual(
            User.objects.filter(ROOT_Q).count(),
            1,
            "the last-root invariant was violated under concurrency",
        )

    def tearDown(self):
        User.objects.all().delete()
        AuditEvent.objects.all().delete()
        Subscription.objects.all().delete()

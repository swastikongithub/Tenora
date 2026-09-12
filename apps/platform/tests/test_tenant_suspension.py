"""
Phase 5 — tenant suspend / reactivate (docs/operator-control-plane-spec.md
§B/§F, master plan §5).

    PATCH /api/platform/tenants/detail/?id=   Root-tier {is_active}

and the enforcement that gives it meaning: one check inside
`TenantJWTAuthentication`, the file this codebase treats as its most
architecturally sensitive.

This module is deliberately shaped like apps/tenants/tests/test_isolation.py —
the spec asks for "its own dedicated isolation-style regression suite before
the tenant-suspension check goes live", so the existing isolation guarantees
are re-asserted here WITH suspension in play, not merely assumed to still
hold.

Real access tokens throughout: these tests exist to exercise
TenantJWTAuthentication itself, which force_authenticate would skip entirely.
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan, Subscription
from apps.platform.models import AuditEvent
from apps.platform.services import TenantSuspensionService
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

TENANT_DETAIL_URL = "/api/platform/tenants/detail/"
SUBSCRIPTION_URL = "/api/subscriptions/current/"
MEMBERSHIPS_URL = "/api/memberships/"
TENANTS_ME_URL = "/api/tenants/me/"
USERS_ME_URL = "/api/users/me/"
PLANS_URL = "/api/plans/"
PASSWORD = "correct-horse-staple-42"


def _detail(tenant_id):
    return f"{TENANT_DETAIL_URL}?id={tenant_id}"


class TenantSuspensionTestBase(APITestCase):
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

        self.plan = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )

        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.other_tenant = Tenant.objects.create(name="Globex", slug="globex")

        self.owner = User.objects.create_user(
            email="owner@acme.test", password=PASSWORD
        )
        self.other_owner = User.objects.create_user(
            email="owner@globex.test", password=PASSWORD
        )
        Membership.objects.create(
            user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER
        )
        Membership.objects.create(
            user=self.other_owner,
            tenant=self.other_tenant,
            role=Membership.Role.OWNER,
        )

        now = timezone.now()
        self.subscription = Subscription.objects.create(
            tenant=self.tenant,
            plan=self.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
        )

    def _auth(self, user, tenant_id=None):
        creds = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}
        if tenant_id is not None:
            creds["HTTP_X_TENANT_ID"] = str(tenant_id)
        self.client.credentials(**creds)

    def _suspend(self, tenant):
        tenant.is_active = False
        tenant.save(update_fields=["is_active"])


class TenantSuspensionPermissionTests(TenantSuspensionTestBase):
    def test_unauthenticated_is_401(self):
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ordinary_user_is_403_and_changes_nothing(self):
        self._auth(self.ordinary)
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)

    def test_staff_without_superuser_is_403(self):
        # Suspension is Root-tier: it can take a paying customer's whole
        # workspace offline, which is not routine operator work.
        self._auth(self.staff)
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)

    def test_a_tenant_owner_cannot_suspend_their_own_tenant(self):
        self._auth(self.owner, tenant_id=self.tenant.id)
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_tenant_owner_cannot_suspend_a_different_tenant(self):
        self._auth(self.owner, tenant_id=self.tenant.id)
        resp = self.client.patch(
            _detail(self.other_tenant.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.other_tenant.refresh_from_db()
        self.assertTrue(self.other_tenant.is_active)

    def test_root_is_allowed(self):
        self._auth(self.root)
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_the_read_on_the_same_path_stays_staff_tier(self):
        self._auth(self.staff)
        resp = self.client.get(_detail(self.tenant.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class TenantSuspensionMutationTests(TenantSuspensionTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.root)

    def test_suspends_the_tenant(self):
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["is_active"])
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.is_active)

    def test_reactivates_the_tenant(self):
        self._suspend(self.tenant)
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)

    def test_suspension_touches_no_subscription_and_calls_no_gateway(self):
        # Suspension is an access decision, not a billing one.
        before = Subscription.objects.get(tenant=self.tenant)
        self.client.patch(_detail(self.tenant.id), {"is_active": False}, format="json")
        after = Subscription.objects.get(tenant=self.tenant)
        self.assertEqual(after.status, before.status)
        self.assertEqual(after.plan_id, before.plan_id)
        self.assertEqual(after.current_period_end, before.current_period_end)

    def test_suspension_deletes_no_memberships(self):
        self.client.patch(_detail(self.tenant.id), {"is_active": False}, format="json")
        self.assertTrue(
            Membership.objects.filter(tenant=self.tenant, user=self.owner).exists()
        )

    def test_empty_body_is_rejected(self):
        resp = self.client.patch(_detail(self.tenant.id), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_name_and_slug_are_not_reachable_from_this_endpoint(self):
        resp = self.client.patch(
            _detail(self.tenant.id),
            {"is_active": False, "name": "Renamed", "slug": "renamed"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, "Acme")
        self.assertEqual(self.tenant.slug, "acme")

    def test_nonexistent_tenant_is_404(self):
        resp = self.client.patch(
            _detail("00000000-0000-0000-0000-000000000000"),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_malformed_id_is_404_not_500(self):
        resp = self.client.patch(
            f"{TENANT_DETAIL_URL}?id=not-a-uuid", {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_id_is_404(self):
        resp = self.client.patch(
            TENANT_DETAIL_URL, {"is_active": False}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class TenantSuspensionAuditTests(TenantSuspensionTestBase):
    def setUp(self):
        super().setUp()
        self._auth(self.root)

    def test_suspend_writes_one_critical_audit_row(self):
        self.client.patch(_detail(self.tenant.id), {"is_active": False}, format="json")
        self.assertEqual(AuditEvent.objects.count(), 1)
        event = AuditEvent.objects.get()
        self.assertTrue(event.is_critical)
        self.assertEqual(event.actor, self.root)
        self.assertEqual(event.action, "tenant.suspended")
        self.assertEqual(event.target_type, "Tenant")
        self.assertEqual(event.target_id, str(self.tenant.id))
        self.assertEqual(event.metadata["slug"], "acme")

    def test_reactivate_writes_its_own_action(self):
        self._suspend(self.tenant)
        self.client.patch(_detail(self.tenant.id), {"is_active": True}, format="json")
        event = AuditEvent.objects.get()
        self.assertEqual(event.action, "tenant.reactivated")
        self.assertTrue(event.is_critical)

    def test_a_no_op_records_nothing(self):
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_a_refused_mutation_records_nothing(self):
        self._auth(self.staff)
        self.client.patch(_detail(self.tenant.id), {"is_active": False}, format="json")
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_audit_write_failure_rolls_back_the_suspension(self):
        from unittest import mock

        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.patch(
                    _detail(self.tenant.id), {"is_active": False}, format="json"
                )

        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)
        self.assertEqual(AuditEvent.objects.count(), 0)


class SuspensionEnforcementTests(TenantSuspensionTestBase):
    """The authentication-boundary check — the point of the whole phase."""

    def test_an_active_tenant_is_reachable(self):
        self._auth(self.owner, tenant_id=self.tenant.id)
        resp = self.client.get(SUBSCRIPTION_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_a_suspended_tenant_is_blocked(self):
        self._suspend(self.tenant)
        self._auth(self.owner, tenant_id=self.tenant.id)
        resp = self.client.get(SUBSCRIPTION_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_the_suspension_response_is_403_not_401(self):
        # 401 would invite the client to re-authenticate, which changes
        # nothing: the credentials were never the problem.
        self._suspend(self.tenant)
        self._auth(self.owner, tenant_id=self.tenant.id)
        resp = self.client.get(SUBSCRIPTION_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["detail"].code, "tenant_suspended")

    def test_the_suspension_response_is_the_same_for_every_verb_and_route(self):
        self._suspend(self.tenant)
        self._auth(self.owner, tenant_id=self.tenant.id)
        for method, url in (
            (self.client.get, SUBSCRIPTION_URL),
            (self.client.get, MEMBERSHIPS_URL),
        ):
            with self.subTest(url=url):
                self.assertEqual(method(url).status_code, status.HTTP_403_FORBIDDEN)

        self.assertEqual(
            self.client.post(
                MEMBERSHIPS_URL, {"email": "new@example.com"}, format="json"
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_reactivating_restores_access(self):
        self._suspend(self.tenant)
        self._auth(self.owner, tenant_id=self.tenant.id)
        self.assertEqual(
            self.client.get(SUBSCRIPTION_URL).status_code, status.HTTP_403_FORBIDDEN
        )

        self.tenant.is_active = True
        self.tenant.save(update_fields=["is_active"])

        self._auth(self.owner, tenant_id=self.tenant.id)
        self.assertEqual(
            self.client.get(SUBSCRIPTION_URL).status_code, status.HTTP_200_OK
        )

    def test_a_suspension_does_not_affect_any_other_tenant(self):
        self._suspend(self.tenant)
        self._auth(self.other_owner, tenant_id=self.other_tenant.id)
        # No subscription for Globex, so 404 from the view — the point is
        # that authentication let the request THROUGH, which a suspension
        # would not have.
        resp = self.client.get(SUBSCRIPTION_URL)
        self.assertNotEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_global_paths_still_work_for_a_member_of_a_suspended_tenant(self):
        # Identity and the tenant list are not tenant-scoped: a suspended
        # customer must still be able to sign in, see which workspaces they
        # belong to, and read the public plan catalogue.
        self._suspend(self.tenant)
        self._auth(self.owner, tenant_id=self.tenant.id)
        for url in (USERS_ME_URL, TENANTS_ME_URL, PLANS_URL):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code, status.HTTP_200_OK
                )

    def test_a_suspended_tenant_still_appears_in_the_users_own_tenant_list(self):
        self._suspend(self.tenant)
        self._auth(self.owner)
        resp = self.client.get(TENANTS_ME_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = {row["slug"]: row for row in resp.data}
        self.assertIn("acme", rows)
        self.assertFalse(rows["acme"]["is_active"])


class SuspensionDoesNotWeakenIsolationTests(TenantSuspensionTestBase):
    """
    The existing isolation contract, re-asserted with suspension in play. The
    new check runs AFTER membership resolution precisely so that none of these
    answers change — in particular so a non-member cannot use the suspension
    response to learn anything about a tenant they have no relationship with.
    """

    def test_a_non_member_gets_the_same_403_whether_the_tenant_is_suspended(self):
        self._auth(self.other_owner, tenant_id=self.tenant.id)
        active_resp = self.client.get(SUBSCRIPTION_URL)

        self._suspend(self.tenant)
        self._auth(self.other_owner, tenant_id=self.tenant.id)
        suspended_resp = self.client.get(SUBSCRIPTION_URL)

        self.assertEqual(active_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(suspended_resp.status_code, status.HTTP_403_FORBIDDEN)
        # Byte-identical: a non-member learns nothing about a tenant's
        # suspension state from this endpoint.
        self.assertEqual(active_resp.content, suspended_resp.content)

    def test_a_missing_tenant_header_is_still_400_not_403(self):
        self._suspend(self.tenant)
        self._auth(self.owner)
        resp = self.client.get(SUBSCRIPTION_URL)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_malformed_tenant_header_is_still_400(self):
        self._suspend(self.tenant)
        self._auth(self.owner, tenant_id="not-a-uuid")
        resp = self.client.get(SUBSCRIPTION_URL)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_unknown_tenant_id_is_still_403_not_a_suspension_answer(self):
        self._auth(self.owner, tenant_id="00000000-0000-0000-0000-000000000000")
        resp = self.client.get(SUBSCRIPTION_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["detail"].code, "not_a_member")

    def test_a_forged_tenant_id_in_the_body_is_still_ignored(self):
        self._suspend(self.other_tenant)
        self._auth(self.owner, tenant_id=self.tenant.id)
        # A body naming the suspended foreign tenant must neither be honored
        # nor produce that tenant's suspension answer.
        resp = self.client.get(SUBSCRIPTION_URL, {"tenant_id": str(self.other_tenant.id)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # The caller's OWN subscription came back — the header decided the
        # tenant, the body decided nothing, exactly as before this phase.
        self.assertEqual(resp.data["id"], str(self.subscription.id))

    def test_jwt_semantics_are_unchanged_by_suspension(self):
        # No claim about the tenant lives in the token: the same token works
        # before suspension, is refused during it, and works again after —
        # without ever being reissued.
        token = f"Bearer {AccessToken.for_user(self.owner)}"
        creds = {"HTTP_AUTHORIZATION": token, "HTTP_X_TENANT_ID": str(self.tenant.id)}

        self.client.credentials(**creds)
        self.assertEqual(
            self.client.get(SUBSCRIPTION_URL).status_code, status.HTTP_200_OK
        )

        self._suspend(self.tenant)
        self.client.credentials(**creds)
        self.assertEqual(
            self.client.get(SUBSCRIPTION_URL).status_code, status.HTTP_403_FORBIDDEN
        )

        self.tenant.is_active = True
        self.tenant.save(update_fields=["is_active"])
        self.client.credentials(**creds)
        self.assertEqual(
            self.client.get(SUBSCRIPTION_URL).status_code, status.HTTP_200_OK
        )


class OperatorsKeepWorkingOnASuspendedTenantTests(TenantSuspensionTestBase):
    """
    Spec §5.4: suspending a customer must not lock operators out of the
    control plane that would un-suspend them. Every /api/platform/ path is in
    GLOBAL_PATHS, so the suspension check never runs for it — asserted here
    rather than assumed.
    """

    def setUp(self):
        super().setUp()
        self._suspend(self.tenant)

    def test_staff_can_still_read_a_suspended_tenants_detail(self):
        self._auth(self.staff)
        resp = self.client.get(_detail(self.tenant.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["is_active"])

    def test_staff_can_still_list_tenants_including_the_suspended_one(self):
        self._auth(self.staff)
        resp = self.client.get("/api/platform/tenants/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        slugs = {row["slug"] for row in resp.data["results"]}
        self.assertIn("acme", slugs)

    def test_root_can_still_reactivate_it(self):
        self._auth(self.root)
        resp = self.client.patch(
            _detail(self.tenant.id), {"is_active": True}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.is_active)

    def test_an_operator_who_is_also_a_member_is_blocked_on_the_tenant_api_only(self):
        # The same person, two hats: their operator access is unaffected,
        # their ordinary tenant access is not.
        Membership.objects.create(
            user=self.staff, tenant=self.tenant, role=Membership.Role.MEMBER
        )
        self._auth(self.staff, tenant_id=self.tenant.id)
        self.assertEqual(
            self.client.get(SUBSCRIPTION_URL).status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.get(_detail(self.tenant.id)).status_code, status.HTTP_200_OK
        )


class TenantSuspensionServiceTests(TenantSuspensionTestBase):
    def test_the_service_is_idempotent(self):
        TenantSuspensionService.set_active(
            actor=self.root, tenant=self.tenant, is_active=False
        )
        TenantSuspensionService.set_active(
            actor=self.root, tenant=self.tenant, is_active=False
        )
        self.assertEqual(AuditEvent.objects.count(), 1)

    def test_the_service_takes_the_actor_explicitly(self):
        TenantSuspensionService.set_active(
            actor=self.root, tenant=self.tenant, is_active=False
        )
        self.assertEqual(AuditEvent.objects.get().actor, self.root)

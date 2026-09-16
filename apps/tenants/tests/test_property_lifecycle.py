"""
Invitations, plan limits and membership lifecycle
(docs/TENORA_PROPERTY_BILLING_MASTER_PLAN.md §4.4, §17, §27).
"""

import threading
from datetime import timedelta
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.billing.models import Plan, Subscription
from apps.notifications.models import Notification
from apps.properties.models import Resident
from apps.properties.tests.factories import add_resident, bearer, make_user, make_workspace
from apps.tenants.limits import MemberLimitReached, PlanLimitService, WorkspaceLimitReached
from apps.tenants.models import Invitation, Membership, Tenant
from apps.tenants.services import (
    InvitationNotPending,
    InvitationService,
    LastOwnerCannotLeave,
    MembershipService,
    TenantService,
)


def subscribe(tenant, code, workspaces, members):
    plan, _ = Plan.objects.get_or_create(
        code=code,
        defaults={
            "name": code.title(),
            "price_cents": 100,
            "max_workspaces": workspaces,
            "max_members_per_workspace": members,
        },
    )
    now = timezone.now()
    return Subscription.objects.create(
        tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
        current_period_start=now, current_period_end=now + timedelta(days=30),
    )


class InvitationFlowTests(APITestCase):
    def setUp(self):
        self.tenant, self.owner = make_workspace("sunrise")
        self.invitee = make_user("rahul@example.com")

    def invite(self):
        bearer(self.client, self.owner, self.tenant)
        resp = self.client.post("/api/invitations/", {"email": "rahul@example.com"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data

    def test_invitation_is_pending_and_grants_no_access(self):
        data = self.invite()
        self.assertEqual(data["status"], "PENDING")
        self.assertFalse(Membership.objects.filter(user=self.invitee, tenant=self.tenant).exists())
        note = Notification.objects.get(recipient=self.invitee, kind="INVITATION_RECEIVED")
        self.assertEqual(note.data["invitation_id"], data["id"])
        bearer(self.client, self.invitee, self.tenant)
        self.assertEqual(self.client.get("/api/bills/").status_code, 403)

    def test_invitee_sees_and_accepts_then_gains_resident_access(self):
        data = self.invite()
        bearer(self.client, self.invitee)
        mine = self.client.get("/api/invitations/mine/").data
        self.assertEqual([i["id"] for i in mine], [data["id"]])
        resp = self.client.post("/api/invitations/respond/", {"id": data["id"], "action": "accept"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ACCEPTED")
        membership = Membership.objects.get(user=self.invitee, tenant=self.tenant)
        self.assertEqual((membership.role, membership.status), ("MEMBER", "ACTIVE"))
        self.assertTrue(Resident.objects.filter(tenant=self.tenant, user=self.invitee, status="ACTIVE").exists())
        self.assertTrue(Notification.objects.filter(recipient=self.owner, kind="INVITATION_ACCEPTED").exists())
        # Accepting twice is idempotent.
        again = self.client.post("/api/invitations/respond/", {"id": data["id"], "action": "accept"}, format="json")
        self.assertEqual(again.status_code, 200)
        bearer(self.client, self.invitee, self.tenant)
        self.assertEqual(self.client.get("/api/bills/").status_code, 200)
        self.assertEqual(self.client.get("/api/subscriptions/current/").status_code, 403)

    def test_decline_creates_no_membership_and_cannot_then_accept(self):
        data = self.invite()
        bearer(self.client, self.invitee)
        resp = self.client.post("/api/invitations/respond/", {"id": data["id"], "action": "decline"}, format="json")
        self.assertEqual(resp.data["status"], "DECLINED")
        self.assertFalse(Membership.objects.filter(user=self.invitee, tenant=self.tenant).exists())
        resp = self.client.post("/api/invitations/respond/", {"id": data["id"], "action": "accept"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(Notification.objects.filter(recipient=self.owner, kind="INVITATION_DECLINED").exists())

    def test_someone_else_cannot_answer_an_invitation(self):
        data = self.invite()
        stranger = make_user("stranger@example.com")
        bearer(self.client, stranger)
        resp = self.client.post("/api/invitations/respond/", {"id": data["id"], "action": "accept"}, format="json")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.client.get("/api/invitations/mine/").data, [])
        self.assertFalse(Membership.objects.filter(user=stranger, tenant=self.tenant).exists())

    def test_expired_invitation_cannot_be_accepted(self):
        data = self.invite()
        Invitation.objects.filter(pk=data["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(InvitationNotPending):
            InvitationService.respond(user=self.invitee, invitation_id=data["id"], accept=True)
        self.assertEqual(Invitation.objects.get(pk=data["id"]).status, "EXPIRED")

    def test_cancelled_invitation_cannot_be_accepted(self):
        data = self.invite()
        resp = self.client.post(f"/api/invitations/{data['id']}/cancel/", format="json")
        self.assertEqual(resp.data["status"], "CANCELLED")
        with self.assertRaises(InvitationNotPending):
            InvitationService.respond(user=self.invitee, invitation_id=data["id"], accept=True)

    def test_duplicate_pending_invitation_refused(self):
        self.invite()
        resp = self.client.post("/api/invitations/", {"email": "rahul@example.com"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Invitation.objects.filter(tenant=self.tenant).count(), 1)

    def test_resident_cannot_invite(self):
        user, _ = add_resident(self.tenant, self.owner, "member@example.com")
        bearer(self.client, user, self.tenant)
        resp = self.client.post("/api/invitations/", {"email": "rahul@example.com"}, format="json")
        self.assertEqual(resp.status_code, 403)


class PlanLimitTests(APITestCase):
    def test_default_basic_allows_two_workspaces(self):
        owner = make_user("o@example.com")
        bearer(self.client, owner)
        for i in range(2):
            self.assertEqual(self.client.post("/api/tenants/", {"name": f"W{i}", "slug": f"w{i}"}).status_code, 201)
        resp = self.client.post("/api/tenants/", {"name": "W3", "slug": "w3"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "workspace_limit_reached")
        self.assertFalse(Tenant.objects.filter(slug="w3").exists())

    def test_pro_allows_twenty_workspaces_not_twenty_one(self):
        owner = make_user("pro@example.com")
        first, _ = TenantService.create_tenant(owner, "W0", "p0")
        subscribe(first, "PRO", 20, 20)
        for i in range(1, 20):
            TenantService.create_tenant(owner, f"W{i}", f"p{i}")
        with self.assertRaises(WorkspaceLimitReached):
            TenantService.create_tenant(owner, "W20", "p20")
        self.assertEqual(PlanLimitService.usage_for_account(owner)["workspaces"], {"used": 20, "limit": 20})

    def test_basic_member_limit_is_ten_and_pending_invitations_reserve_seats(self):
        tenant, owner = make_workspace("basic")
        subscribe(tenant, "BASIC", 2, 10)
        for i in range(9):
            add_resident(tenant, owner, f"r{i}@example.com")
        make_user("pending@example.com")
        InvitationService.create(tenant=tenant, inviter=owner, email="pending@example.com")
        make_user("eleventh@example.com")
        with self.assertRaises(MemberLimitReached):
            InvitationService.create(tenant=tenant, inviter=owner, email="eleventh@example.com")
        usage = PlanLimitService.usage_for_workspace(tenant)["members"]
        self.assertEqual((usage["active"], usage["pending_invitations"], usage["limit"]), (9, 1, 10))

    def test_pro_member_limit_is_twenty(self):
        tenant, owner = make_workspace("pro")
        subscribe(tenant, "PRO", 20, 20)
        for i in range(20):
            add_resident(tenant, owner, f"r{i}@example.com")
        make_user("extra@example.com")
        with self.assertRaises(MemberLimitReached):
            InvitationService.create(tenant=tenant, inviter=owner, email="extra@example.com")

    def test_left_members_free_their_seat(self):
        tenant, owner = make_workspace("seats")
        subscribe(tenant, "TINY", 1, 1)
        user, _ = add_resident(tenant, owner, "a@example.com")
        make_user("b@example.com")
        with self.assertRaises(MemberLimitReached):
            InvitationService.create(tenant=tenant, inviter=owner, email="b@example.com")
        MembershipService.leave(user=user, tenant=tenant)
        InvitationService.create(tenant=tenant, inviter=owner, email="b@example.com")

    def test_limit_rejection_via_api_cannot_be_bypassed_by_body(self):
        tenant, owner = make_workspace("bypass")
        subscribe(tenant, "TINY", 1, 0)
        make_user("x@example.com")
        bearer(self.client, owner, tenant)
        resp = self.client.post(
            "/api/invitations/", {"email": "x@example.com", "limit": 999, "max_members_per_workspace": 999}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "member_limit_reached")

    def test_usage_endpoints(self):
        tenant, owner = make_workspace("usage")
        add_resident(tenant, owner, "a@example.com")
        bearer(self.client, owner, tenant)
        self.assertEqual(self.client.get("/api/workspace/usage/").data["members"]["active"], 1)
        bearer(self.client, owner)
        body = self.client.get("/api/account/usage/").data
        self.assertEqual(body["workspaces"], {"used": 1, "limit": 2})


class ConcurrentLimitTests(TransactionTestCase):
    def test_parallel_workspace_creation_respects_limit(self):
        owner = make_user("race@example.com")
        TenantService.create_tenant(owner, "W0", "race-0")
        barrier = threading.Barrier(3)
        results = []

        def attempt(i):
            try:
                barrier.wait()
                TenantService.create_tenant(owner, f"W{i}", f"race-{i}")
                results.append("ok")
            except WorkspaceLimitReached:
                results.append("limit")
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(1, 4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), ["limit", "limit", "ok"])
        self.assertEqual(PlanLimitService.owned_workspace_count(owner), 2)


class MembershipLifecycleTests(APITestCase):
    def setUp(self):
        self.tenant, self.owner = make_workspace("life")
        self.user, self.resident = add_resident(self.tenant, self.owner, "leaver@example.com")

    def test_leave_revokes_access_but_keeps_account_and_history(self):
        bearer(self.client, self.user, self.tenant)
        self.assertEqual(self.client.post("/api/memberships/leave/").status_code, 200)
        self.assertEqual(self.client.get("/api/bills/").status_code, 403)
        membership = Membership.objects.get(user=self.user, tenant=self.tenant)
        self.assertEqual(membership.status, "LEFT")
        self.resident.refresh_from_db()
        self.assertEqual(self.resident.status, "INACTIVE")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        bearer(self.client, self.user)
        self.assertEqual(self.client.get("/api/tenants/me/").data, [])
        # ...and can create their own workspace afterwards.
        self.assertEqual(self.client.post("/api/tenants/", {"name": "Mine", "slug": "mine"}).status_code, 201)

    def test_left_member_can_be_reinvited_on_the_same_row(self):
        MembershipService.leave(user=self.user, tenant=self.tenant)
        add_resident(self.tenant, self.owner, "leaver@example.com")
        self.assertEqual(Membership.objects.filter(user=self.user, tenant=self.tenant).count(), 1)
        self.assertEqual(Membership.objects.get(user=self.user, tenant=self.tenant).status, "ACTIVE")

    def test_sole_owner_cannot_leave(self):
        with self.assertRaises(LastOwnerCannotLeave):
            MembershipService.leave(user=self.owner, tenant=self.tenant)
        bearer(self.client, self.owner, self.tenant)
        self.assertEqual(self.client.post("/api/memberships/leave/").status_code, 409)

    def test_owner_removes_resident(self):
        bearer(self.client, self.owner, self.tenant)
        membership = Membership.objects.get(user=self.user, tenant=self.tenant)
        resp = self.client.post(f"/api/memberships/{membership.id}/remove/")
        self.assertEqual(resp.data["status"], "REMOVED")
        owner_membership = Membership.objects.get(user=self.owner, tenant=self.tenant)
        self.assertEqual(self.client.post(f"/api/memberships/{owner_membership.id}/remove/").status_code, 409)

    def test_transfer_ownership_then_old_owner_may_leave(self):
        bearer(self.client, self.owner, self.tenant)
        target = Membership.objects.get(user=self.user, tenant=self.tenant)
        resp = self.client.post(f"/api/memberships/{target.id}/transfer-ownership/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["role"], "OWNER")
        self.assertEqual(Membership.objects.get(user=self.owner, tenant=self.tenant).role, "MEMBER")
        MembershipService.leave(user=self.owner, tenant=self.tenant)

    def test_close_workspace_requires_it_to_be_empty(self):
        bearer(self.client, self.owner, self.tenant)
        self.assertEqual(self.client.post("/api/workspace/close/").status_code, 409)
        MembershipService.leave(user=self.user, tenant=self.tenant)
        self.assertEqual(self.client.post("/api/workspace/close/").status_code, 200)
        self.tenant.refresh_from_db()
        self.assertIsNotNone(self.tenant.closed_at)
        self.assertEqual(self.client.get("/api/memberships/").status_code, 403)
        self.assertEqual(PlanLimitService.owned_workspace_count(self.owner), 0)

    def test_a_member_leaves_the_workspace_they_pick_not_the_active_one(self):
        # §27.1: belonging to several workspaces must not force leaving them in
        # some order. The target is the one named by X-Tenant-ID on THIS call.
        other, other_owner = make_workspace("second")
        add_resident(other, other_owner, "leaver@example.com")
        third, third_owner = make_workspace("third")
        add_resident(third, third_owner, "leaver@example.com")

        # Operating as `self.tenant`, leave `other` — and stay in both the rest.
        bearer(self.client, self.user, other)
        self.assertEqual(self.client.post("/api/memberships/leave/").status_code, 200)
        self.assertEqual(Membership.objects.get(user=self.user, tenant=other).status, "LEFT")
        self.assertEqual(Membership.objects.get(user=self.user, tenant=self.tenant).status, "ACTIVE")
        self.assertEqual(Membership.objects.get(user=self.user, tenant=third).status, "ACTIVE")

        bearer(self.client, self.user, self.tenant)
        self.assertEqual(self.client.get("/api/bills/").status_code, 200)
        remaining = {t["id"] for t in self.client.get("/api/tenants/me/").data}
        self.assertEqual(remaining, {str(self.tenant.id), str(third.id)})

    def test_leaving_a_workspace_you_do_not_belong_to_is_refused(self):
        stranger, _ = make_workspace("stranger")
        bearer(self.client, self.user, stranger)
        resp = self.client.post("/api/memberships/leave/")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Membership.objects.filter(tenant=stranger, status="LEFT").count(), 0)

    def test_an_owner_closes_the_workspace_they_pick_and_keeps_the_others(self):
        doomed, owner = make_workspace("doomed")
        kept, _ = make_workspace("kept", owner=owner)
        bearer(self.client, owner, doomed)
        self.assertEqual(self.client.post("/api/workspace/close/").status_code, 200)
        doomed.refresh_from_db()
        kept.refresh_from_db()
        self.assertIsNotNone(doomed.closed_at)
        self.assertIsNone(kept.closed_at)
        # The workspace that was kept is untouched and still usable.
        bearer(self.client, owner, kept)
        self.assertEqual(self.client.get("/api/memberships/").status_code, 200)
        self.assertEqual(PlanLimitService.owned_workspace_count(owner), 1)

    def test_a_resident_cannot_close_a_workspace_they_only_belong_to(self):
        bearer(self.client, self.user, self.tenant)
        self.assertEqual(self.client.post("/api/workspace/close/").status_code, 403)
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.closed_at)

    def test_closing_one_workspace_leaves_the_others_billing_history_alone(self):
        doomed, owner = make_workspace("doomed2")
        kept, _ = make_workspace("kept2", owner=owner)
        keeper, _ = add_resident(kept, owner, "stays@example.com")
        bearer(self.client, owner, doomed)
        self.assertEqual(self.client.post("/api/workspace/close/").status_code, 200)
        self.assertEqual(Membership.objects.get(user=keeper, tenant=kept).status, "ACTIVE")
        self.assertEqual(Resident.objects.filter(tenant=kept, status="ACTIVE").count(), 1)

    def test_suspension_check_does_not_leak_to_former_members(self):
        MembershipService.leave(user=self.user, tenant=self.tenant)
        Tenant.objects.filter(pk=self.tenant.pk).update(is_active=False)
        bearer(self.client, self.user, self.tenant)
        resp = self.client.get("/api/bills/")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["detail"].code, "not_a_member")

    def test_accept_blocked_when_workspace_suspended(self):
        make_user("late@example.com")
        invitation = InvitationService.create(tenant=self.tenant, inviter=self.owner, email="late@example.com")
        Tenant.objects.filter(pk=self.tenant.pk).update(is_active=False)
        bearer(self.client, invitation.invited_user)
        with mock.patch.object(PlanLimitService, "assert_can_activate_member") as check:
            resp = self.client.post("/api/invitations/respond/", {"id": str(invitation.id), "action": "accept"}, format="json")
        self.assertEqual(resp.status_code, 409)
        check.assert_not_called()

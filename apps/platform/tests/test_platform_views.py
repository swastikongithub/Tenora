"""
Platform-admin endpoints — docs/platform-admin-spec.md §9.

The signature test here (`test_platform_staff_sees_every_tenant_in_one_response`)
is the deliberate OPPOSITE of every isolation test in this project: it proves
that one response contains three different tenants, owned by three different
users, at once. That is the one place in the codebase where cross-tenant data
is supposed to be returned — see apps/platform/views.py.

Real access tokens, not force_authenticate — same reason as the billing API
tests (force_authenticate skips the authentication class entirely).
"""

from datetime import datetime, timezone as dt_timezone

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.models import Plan, Subscription
from apps.billing.services import SubscriptionService
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

TENANTS_URL = "/api/platform/tenants/"
STATS_URL = "/api/platform/stats/"
PASSWORD = "correct-horse-staple-42"


def _subscribe(tenant, plan, target_status):
    """Create a subscription and walk it to `target_status` via the service."""
    start, end = SubscriptionService.default_period(plan)
    sub = SubscriptionService.create_subscription(
        tenant=tenant, plan=plan, current_period_start=start, current_period_end=end
    )
    path = {
        Subscription.Status.TRIALING: [],
        Subscription.Status.ACTIVE: [Subscription.Status.ACTIVE],
        Subscription.Status.PAST_DUE: [
            Subscription.Status.ACTIVE,
            Subscription.Status.PAST_DUE,
        ],
        Subscription.Status.CANCELED: [Subscription.Status.CANCELED],
    }[target_status]
    for step in path:
        sub = SubscriptionService.transition_status(sub, step)
    return sub


class PlatformAuthTests(APITestCase):
    """Who is allowed through the door at all."""

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

    def test_unauthenticated_gets_401_on_both_endpoints(self):
        for url in (TENANTS_URL, STATS_URL):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )

    def test_non_staff_authenticated_gets_403_not_404_on_both_endpoints(self):
        # 403, not 404: the endpoint exists, the caller just can't use it
        # (spec §8). 404 would wrongly imply it isn't there.
        self._auth(self.ordinary)
        for url in (TENANTS_URL, STATS_URL):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code, status.HTTP_403_FORBIDDEN
                )

    def test_no_tenant_header_required(self):
        # Global path: a staff JWT alone is enough, no X-Tenant-ID.
        self._auth(self.staff)
        for url in (TENANTS_URL, STATS_URL):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code, status.HTTP_200_OK
                )


class PlatformTenantListTests(APITestCase):
    """
    Phase 1 (docs/operator-control-plane-spec.md §C) wraps this endpoint's
    response in a paginated envelope — `resp.data["results"]` where these
    tests used to read `resp.data` directly. This is a deliberate,
    spec-approved contract change to an endpoint that is not tenant-facing
    (platform-admin only), not a weakened test: every original assertion
    about the row *shape* and *content* is unchanged, only the envelope.
    """

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

    def _tenant_with_members(self, name, slug, member_emails):
        tenant = Tenant.objects.create(name=name, slug=slug)
        for email in member_emails:
            user = User.objects.create_user(email=email, password=PASSWORD)
            Membership.objects.create(
                user=user, tenant=tenant, role=Membership.Role.MEMBER
            )
        return tenant

    def test_platform_staff_sees_every_tenant_in_one_response(self):
        """
        THE ANTI-ISOLATION TEST — the intentional inverse of every
        test_isolation.py case. Three tenants, three distinct owners, none
        of whom is a member of the others' tenants. A platform-staff caller
        gets all three back in a single response. This is the one endpoint
        allowed to do this.
        """
        for name, slug in (("Alpha", "alpha"), ("Beta", "beta"), ("Gamma", "gamma")):
            tenant = Tenant.objects.create(name=name, slug=slug)
            owner = User.objects.create_user(
                email=f"{slug}-owner@example.com", password=PASSWORD
            )
            Membership.objects.create(
                user=owner, tenant=tenant, role=Membership.Role.OWNER
            )

        resp = self.client.get(TENANTS_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = {row["name"] for row in resp.data["results"]}
        self.assertEqual(names, {"Alpha", "Beta", "Gamma"})

    def test_member_count_is_a_real_count(self):
        self._tenant_with_members("Alpha", "alpha", ["a1@x.com", "a2@x.com"])
        self._tenant_with_members("Beta", "beta", ["b1@x.com"])

        rows = {
            row["name"]: row
            for row in self.client.get(TENANTS_URL).data["results"]
        }

        self.assertEqual(rows["Alpha"]["member_count"], 2)
        self.assertEqual(rows["Beta"]["member_count"], 1)

    def test_subscription_summary_null_when_absent_populated_when_present(self):
        with_sub = self._tenant_with_members("Alpha", "alpha", ["a1@x.com"])
        self._tenant_with_members("Beta", "beta", ["b1@x.com"])
        _subscribe(with_sub, self.plan, Subscription.Status.ACTIVE)

        rows = {
            row["name"]: row
            for row in self.client.get(TENANTS_URL).data["results"]
        }

        self.assertEqual(
            rows["Alpha"]["subscription"],
            {"plan_name": "Pro", "status": "ACTIVE"},
        )
        self.assertIsNone(rows["Beta"]["subscription"])

    def test_empty_system_returns_empty_list_not_error(self):
        resp = self.client.get(TENANTS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 0)
        self.assertEqual(resp.data["results"], [])


class PlatformStatsTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.staff)}"
        )
        self.pro = Plan.objects.create(
            name="Pro", code="PRO", price_cents=2900, currency="USD"
        )
        self.team = Plan.objects.create(
            name="Team", code="TEAM", price_cents=9900, currency="USD"
        )

    def _tenant(self, slug, created=None):
        tenant = Tenant.objects.create(name=slug.title(), slug=slug)
        if created is not None:
            # auto_now_add only fires on .save(); a raw .update() bypasses it,
            # which is the only way to seed a known historical created_at.
            Tenant.objects.filter(pk=tenant.pk).update(created_at=created)
        return tenant

    def test_empty_system_reports_all_zeros(self):
        data = self.client.get(STATS_URL).data

        self.assertEqual(data["total_tenants"], 0)
        self.assertEqual(
            data["status_breakdown"],
            {
                "TRIALING": 0,
                "ACTIVE": 0,
                "PAST_DUE": 0,
                "CANCELED": 0,
                "NONE": 0,
            },
        )
        self.assertEqual(
            data["plan_distribution"],
            [{"plan_name": "Pro", "count": 0}, {"plan_name": "Team", "count": 0}],
        )
        self.assertEqual(data["signups_over_time"], [])

    def test_aggregates_match_seeded_fixture_exactly(self):
        jan = datetime(2026, 1, 15, tzinfo=dt_timezone.utc)
        feb = datetime(2026, 2, 3, tzinfo=dt_timezone.utc)

        t_active = self._tenant("act", created=jan)
        t_trial = self._tenant("tri", created=jan)
        t_pastdue = self._tenant("pd", created=feb)
        t_canceled = self._tenant("can", created=feb)
        self._tenant("nosub", created=feb)  # no subscription at all

        _subscribe(t_active, self.pro, Subscription.Status.ACTIVE)
        _subscribe(t_trial, self.pro, Subscription.Status.TRIALING)
        _subscribe(t_pastdue, self.team, Subscription.Status.PAST_DUE)
        _subscribe(t_canceled, self.team, Subscription.Status.CANCELED)

        data = self.client.get(STATS_URL).data

        self.assertEqual(data["total_tenants"], 5)
        self.assertEqual(
            data["status_breakdown"],
            {
                "TRIALING": 1,
                "ACTIVE": 1,
                "PAST_DUE": 1,
                "CANCELED": 1,
                "NONE": 1,
            },
        )
        self.assertEqual(
            data["plan_distribution"],
            [{"plan_name": "Pro", "count": 2}, {"plan_name": "Team", "count": 2}],
        )
        self.assertEqual(
            data["signups_over_time"],
            [{"month": "2026-01", "count": 2}, {"month": "2026-02", "count": 3}],
        )

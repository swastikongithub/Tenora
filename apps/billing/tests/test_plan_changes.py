"""
Subscription plan changes: which ones the billing rules allow, what a permitted
one costs the customer, and when a change actually takes effect.

The rules live in `PlanChangePolicy`, and BOTH entry points ask it — so the
answer is the same whether a client PATCHes the subscription or posts to the
checkout endpoint. An upgrade never takes effect because someone clicked: only
a verified activation webhook moves the plan, and until it arrives the current
subscription keeps running untouched.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.billing.gateway import EventType, PaymentGatewayAdapter, ProviderCheckout
from apps.billing.models import Plan, Subscription, SubscriptionCheckout, WebhookEvent
from apps.billing.services import (
    PlanChangeNotAllowed,
    PlanChangePolicy,
    WebhookProcessingService,
)
from apps.tenants.models import Membership, Tenant
from apps.users.models import User

PASSWORD = "correct-horse-staple-42"
PATCH_URL = "/api/subscriptions/current/"
CHECKOUT_URL = "/api/subscriptions/current/checkout/"


def _gateway(sub_id="sub_UPGRADE"):
    gateway = mock.Mock(spec=PaymentGatewayAdapter)
    gateway.create_subscription.return_value = ProviderCheckout(
        provider="cashfree",
        external_subscription_id=sub_id,
        session_token="sess_abc",
        public_key="",
        mode="sandbox",
    )
    return gateway


def _plans():
    basic = Plan.objects.create(
        name="Basic", code="BASIC_MONTHLY", price_cents=50_000,
        currency="INR", interval="MONTHLY", external_plan_id="tenora_basic_monthly",
    )
    pro_monthly = Plan.objects.create(
        name="Pro", code="PRO_MONTHLY", price_cents=200_000,
        currency="INR", interval="MONTHLY", external_plan_id="tenora_pro_monthly",
    )
    pro_annual = Plan.objects.create(
        name="Pro", code="PRO_ANNUAL", price_cents=1_000_000,
        currency="INR", interval="ANNUAL", external_plan_id="tenora_pro_annual",
    )
    return basic, pro_monthly, pro_annual


class PlanChangePolicyTests(TestCase):
    def setUp(self):
        self.basic, self.pro_monthly, self.pro_annual = _plans()

    def test_the_same_plan_is_a_no_op(self):
        for plan in (self.basic, self.pro_monthly, self.pro_annual):
            with self.subTest(plan=plan.code):
                self.assertEqual(
                    PlanChangePolicy.classify(plan, plan), PlanChangePolicy.NO_OP
                )

    def test_moving_up_a_tier_is_a_paid_upgrade(self):
        for target in (self.pro_monthly, self.pro_annual):
            with self.subTest(target=target.code):
                self.assertEqual(
                    PlanChangePolicy.classify(self.basic, target),
                    PlanChangePolicy.UPGRADE,
                )

    def test_moving_down_a_tier_is_refused(self):
        for current in (self.pro_monthly, self.pro_annual):
            with self.subTest(current=current.code):
                with self.assertRaises(PlanChangeNotAllowed) as raised:
                    PlanChangePolicy.classify(current, self.basic)
                self.assertEqual(raised.exception.code, "downgrade_not_supported")

    def test_switching_billing_cycle_within_a_tier_is_refused(self):
        for current, target in (
            (self.pro_monthly, self.pro_annual),
            (self.pro_annual, self.pro_monthly),
        ):
            with self.subTest(change=f"{current.code}->{target.code}"):
                with self.assertRaises(PlanChangeNotAllowed) as raised:
                    PlanChangePolicy.classify(current, target)
                self.assertEqual(
                    raised.exception.code, "billing_cycle_change_not_supported"
                )

    def test_an_unclassified_plan_code_fails_closed(self):
        legacy = Plan.objects.create(
            name="Team", code="TEAM", price_cents=900_000, currency="INR",
            interval="MONTHLY",
        )
        with self.assertRaises(PlanChangeNotAllowed) as raised:
            PlanChangePolicy.classify(self.basic, legacy)
        self.assertEqual(raised.exception.code, "plan_change_not_supported")


class PlanChangeApiTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.owner = User.objects.create_user(
            email="owner@example.com", password=PASSWORD
        )
        Membership.objects.create(
            user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER
        )
        self.basic, self.pro_monthly, self.pro_annual = _plans()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.owner)}",
            HTTP_X_TENANT_ID=str(self.tenant.id),
        )

    def _subscribe(self, plan, external_id="sub_CURRENT"):
        now = timezone.now()
        return Subscription.objects.create(
            tenant=self.tenant, plan=plan, status=Subscription.Status.ACTIVE,
            current_period_start=now - timedelta(days=5),
            current_period_end=now + timedelta(days=25),
            external_subscription_id=external_id,
        )

    # --- same plan -------------------------------------------------------

    @mock.patch("apps.billing.services.get_gateway")
    def test_selecting_the_current_plan_creates_no_checkout(self, get_gateway):
        gateway = _gateway()
        get_gateway.return_value = gateway
        self._subscribe(self.pro_monthly)

        resp = self.client.post(CHECKOUT_URL, {"plan_id": str(self.pro_monthly.id)})

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "already_on_plan")
        gateway.create_subscription.assert_not_called()
        self.assertFalse(SubscriptionCheckout.objects.exists())
        self.assertEqual(Subscription.objects.count(), 1)

    def test_patching_the_current_plan_changes_nothing(self):
        subscription = self._subscribe(self.pro_monthly)

        resp = self.client.patch(PATCH_URL, {"plan_id": str(self.pro_monthly.id)})

        self.assertEqual(resp.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, self.pro_monthly.id)
        self.assertEqual(subscription.external_subscription_id, "sub_CURRENT")

    # --- upgrades --------------------------------------------------------

    @mock.patch("apps.billing.services.get_gateway")
    def test_basic_to_pro_monthly_opens_a_checkout_and_keeps_basic_active(
        self, get_gateway
    ):
        gateway = _gateway()
        get_gateway.return_value = gateway
        subscription = self._subscribe(self.basic)

        resp = self.client.post(CHECKOUT_URL, {"plan_id": str(self.pro_monthly.id)})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["session_token"], "sess_abc")
        gateway.create_subscription.assert_called_once()
        # The paid-for plan is NOT applied yet — that waits for the webhook.
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, self.basic.id)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(subscription.external_subscription_id, "sub_CURRENT")

    @mock.patch("apps.billing.services.get_gateway")
    def test_basic_to_pro_annual_opens_a_checkout(self, get_gateway):
        get_gateway.return_value = _gateway("sub_ANNUAL")
        self._subscribe(self.basic)

        resp = self.client.post(CHECKOUT_URL, {"plan_id": str(self.pro_annual.id)})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SubscriptionCheckout.objects.get().plan_id, self.pro_annual.id)

    @mock.patch("apps.billing.services.get_gateway")
    def test_a_failed_checkout_creation_leaves_the_subscription_untouched(
        self, get_gateway
    ):
        from apps.billing.gateway import ProviderUnavailable

        gateway = _gateway()
        gateway.create_subscription.side_effect = ProviderUnavailable("boom")
        get_gateway.return_value = gateway
        subscription = self._subscribe(self.basic)

        resp = self.client.post(CHECKOUT_URL, {"plan_id": str(self.pro_monthly.id)})

        self.assertEqual(resp.status_code, 503)
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, self.basic.id)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertFalse(
            SubscriptionCheckout.objects.exclude(external_subscription_id=None).exists()
        )

    @mock.patch("apps.billing.services.get_gateway")
    def test_repeated_upgrade_requests_reuse_one_provider_subscription(
        self, get_gateway
    ):
        gateway = _gateway()
        get_gateway.return_value = gateway
        self._subscribe(self.basic)

        first = self.client.post(CHECKOUT_URL, {"plan_id": str(self.pro_monthly.id)})
        second = self.client.post(CHECKOUT_URL, {"plan_id": str(self.pro_monthly.id)})

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(gateway.create_subscription.call_count, 1)
        self.assertEqual(SubscriptionCheckout.objects.count(), 1)

    def test_patching_an_upgrade_is_refused_and_points_at_checkout(self):
        subscription = self._subscribe(self.basic)

        resp = self.client.patch(PATCH_URL, {"plan_id": str(self.pro_monthly.id)})

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "upgrade_requires_checkout")
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan_id, self.basic.id)

    # --- downgrades and billing-cycle changes ----------------------------

    @mock.patch("apps.billing.services.get_gateway")
    def test_downgrades_are_blocked_on_both_endpoints(self, get_gateway):
        gateway = _gateway()
        get_gateway.return_value = gateway
        for current in (self.pro_monthly, self.pro_annual):
            with self.subTest(current=current.code):
                Subscription.objects.all().delete()
                SubscriptionCheckout.objects.all().delete()
                subscription = self._subscribe(current)

                checkout = self.client.post(
                    CHECKOUT_URL, {"plan_id": str(self.basic.id)}
                )
                patch = self.client.patch(PATCH_URL, {"plan_id": str(self.basic.id)})

                self.assertEqual(checkout.status_code, 409)
                self.assertEqual(checkout.data["code"], "downgrade_not_supported")
                self.assertEqual(patch.status_code, 409)
                self.assertEqual(patch.data["code"], "downgrade_not_supported")
                gateway.create_subscription.assert_not_called()
                self.assertFalse(SubscriptionCheckout.objects.exists())
                subscription.refresh_from_db()
                self.assertEqual(subscription.plan_id, current.id)

    @mock.patch("apps.billing.services.get_gateway")
    def test_billing_cycle_switches_are_blocked_both_ways(self, get_gateway):
        gateway = _gateway()
        get_gateway.return_value = gateway
        for current, target in (
            (self.pro_monthly, self.pro_annual),
            (self.pro_annual, self.pro_monthly),
        ):
            with self.subTest(change=f"{current.code}->{target.code}"):
                Subscription.objects.all().delete()
                SubscriptionCheckout.objects.all().delete()
                self._subscribe(current)

                checkout = self.client.post(CHECKOUT_URL, {"plan_id": str(target.id)})
                patch = self.client.patch(PATCH_URL, {"plan_id": str(target.id)})

                for resp in (checkout, patch):
                    self.assertEqual(resp.status_code, 409)
                    self.assertEqual(
                        resp.data["code"], "billing_cycle_change_not_supported"
                    )
                gateway.create_subscription.assert_not_called()
                self.assertFalse(SubscriptionCheckout.objects.exists())


class UpgradeActivationTests(TestCase):
    """An upgrade becomes real only when the new mandate's webhook activates."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.basic, self.pro_monthly, _ = _plans()
        now = timezone.now()
        self.subscription = Subscription.objects.create(
            tenant=self.tenant, plan=self.basic, status=Subscription.Status.ACTIVE,
            current_period_start=now - timedelta(days=5),
            current_period_end=now + timedelta(days=25),
            external_subscription_id="sub_BASIC",
        )
        self.checkout = SubscriptionCheckout.objects.create(
            tenant=self.tenant, plan=self.pro_monthly,
            external_subscription_id="sub_PRO", provider="cashfree",
            session_token="sess_abc",
        )

    def _activate(self, external_id, event_id="evt_1"):
        event = WebhookEvent.objects.create(
            external_event_id=event_id,
            event_type=EventType.ACTIVATED,
            external_subscription_id=external_id,
            raw_payload={},
        )
        return WebhookProcessingService.process_event(event)

    def test_the_new_mandates_activation_applies_the_upgrade(self):
        self._activate("sub_PRO")

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_id, self.pro_monthly.id)
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(self.subscription.external_subscription_id, "sub_PRO")
        self.assertEqual(Subscription.objects.count(), 1)

    def test_a_redelivered_activation_upgrades_once(self):
        self._activate("sub_PRO", event_id="evt_1")
        self._activate("sub_PRO", event_id="evt_2")

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_id, self.pro_monthly.id)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_a_late_webhook_for_the_old_plan_cannot_revert_the_upgrade(self):
        self._activate("sub_PRO")
        # The abandoned Basic mandate's activation arrives afterwards.
        self._activate("sub_BASIC", event_id="evt_old")

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_id, self.pro_monthly.id)
        self.assertEqual(self.subscription.external_subscription_id, "sub_PRO")
        self.assertEqual(Subscription.objects.count(), 1)

    def test_an_activation_for_a_downgrade_checkout_is_refused(self):
        # A checkout that should never have existed must not move a plan DOWN.
        self.checkout.plan = self.basic
        self.checkout.save(update_fields=["plan"])
        Subscription.objects.filter(pk=self.subscription.pk).update(
            plan=self.pro_monthly
        )

        self._activate("sub_PRO")

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_id, self.pro_monthly.id)

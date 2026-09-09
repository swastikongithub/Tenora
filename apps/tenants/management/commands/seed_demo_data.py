"""
Seed a throwaway demo user/tenant/plan/subscription for first-run evaluation
of the Dockerized stack (docs/docker-packaging-spec.md §4.5). Run by
docker-entrypoint.sh on container start, gated behind SEED_DEMO_DATA — the
manual dev workflow never touches this unless invoked by hand.

Idempotent by construction: every step is check-then-create against a real
uniqueness constraint (Plan.code, User.email, Tenant.slug,
UNIQUE(user, tenant), the Subscription-Tenant OneToOne), not a blind insert —
safe to run on every container start without duplicating anything.

Lives under apps/tenants because TenantService (the natural aggregate root
for "create a tenant + its first membership") already does, even though this
command also touches apps.users and apps.billing.
"""

from django.core.management.base import BaseCommand

from apps.billing.models import Plan
from apps.billing.services import SubscriptionService
from apps.tenants.models import Membership, Tenant
from apps.tenants.services import TenantService
from apps.users.models import User

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-pass-12345"
DEMO_TENANT_NAME = "Demo Workspace"
DEMO_TENANT_SLUG = "demo-workspace"

DEMO_PLANS = [
    {"code": "PRO", "name": "Pro", "price_cents": 2900, "currency": "USD", "interval": Plan.Interval.MONTHLY},
    {"code": "TEAM", "name": "Team", "price_cents": 9900, "currency": "USD", "interval": Plan.Interval.MONTHLY},
]


class Command(BaseCommand):
    help = (
        "Seed a throwaway demo user, tenant, plans and subscription for "
        "first-run evaluation of the Dockerized stack. Idempotent — safe to "
        "run on every container start."
    )

    def handle(self, *args, **options):
        plans = {}
        for spec in DEMO_PLANS:
            code = spec["code"]
            plan, _ = Plan.objects.get_or_create(code=code, defaults=spec)
            plans[code] = plan

        email = User.objects.normalize_email(DEMO_EMAIL)
        user, user_created = User.objects.get_or_create(email=email)
        if user_created:
            user.set_password(DEMO_PASSWORD)
            # email-verification-spec.md §8: the grandfathering migration only
            # covers rows that exist at migration-apply time — a fresh
            # container on a clean volume creates this user AFTER that
            # migration is already baked in, so without this it would default
            # to unverified and instantly fail login.
            user.email_verified = True
            user.save(update_fields=["password", "email_verified"])

        tenant = Tenant.objects.filter(slug=DEMO_TENANT_SLUG).first()
        if tenant is None:
            tenant, _ = TenantService.create_tenant(
                user, DEMO_TENANT_NAME, DEMO_TENANT_SLUG
            )
        else:
            Membership.objects.get_or_create(
                user=user, tenant=tenant, defaults={"role": Membership.Role.OWNER}
            )

        if not hasattr(tenant, "subscription"):
            pro = plans["PRO"]
            start, end = SubscriptionService.default_period(pro)
            SubscriptionService.create_subscription(tenant, pro, start, end)

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready — log in with {DEMO_EMAIL} / {DEMO_PASSWORD}"
            )
        )

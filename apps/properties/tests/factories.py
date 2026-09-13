"""Shared builders for property-billing tests. Everything goes through the real
services (invitation acceptance, lease creation, readings), so a test that uses
these exercises the same paths production does."""

from datetime import date
from decimal import Decimal

from rest_framework_simplejwt.tokens import AccessToken

from apps.properties.services import (
    BillingCycleService,
    BillService,
    LeaseService,
    MeterReadingService,
    MeterService,
    PaymentService,
    PropertyService,
    TariffService,
    UnitService,
    WorkspaceSettingsService,
)
from apps.tenants.models import Membership, Tenant
from apps.tenants.services import InvitationService
from apps.users.models import User

PASSWORD = "correct-horse-staple-42"


def make_user(email, **extra):
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


def make_workspace(slug, owner=None):
    owner = owner or make_user(f"owner-{slug}@example.com")
    tenant = Tenant.objects.create(name=slug.replace("-", " ").title(), slug=slug)
    Membership.objects.create(user=owner, tenant=tenant, role=Membership.Role.OWNER)
    return tenant, owner


def add_resident(tenant, owner, email, first_name=""):
    user = User.objects.filter(email=email).first() or make_user(email, first_name=first_name)
    invitation = InvitationService.create(tenant=tenant, inviter=owner, email=email)
    InvitationService.respond(user=user, invitation_id=invitation.id, accept=True)
    return user, user.residencies.get(tenant=tenant)


def bearer(client, user, tenant=None):
    creds = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}
    if tenant is not None:
        creds["HTTP_X_TENANT_ID"] = str(tenant.id)
    client.credentials(**creds)


class Scenario:
    """The plan's §39 scenario: Sunrise, unit 203, Rahul, ₹12,000 rent,
    meter ELEC-203 12,450 -> 12,610, ₹8/unit, ₹500 maintenance."""

    def __init__(self, slug="sunrise", rent=1_200_000, rate="800", maintenance=50_000, email=None):
        self.tenant, self.owner = make_workspace(slug)
        WorkspaceSettingsService.update(
            actor=self.owner,
            tenant=self.tenant,
            changes={"default_maintenance_cents": maintenance, "currency": "INR"},
        )
        self.property = PropertyService.create(actor=self.owner, tenant=self.tenant, name=f"{slug} Building A")
        self.unit = UnitService.create(actor=self.owner, tenant=self.tenant, prop=self.property, identifier="203")
        self.user, self.resident = add_resident(
            self.tenant, self.owner, email or f"rahul-{slug}@example.com", first_name="Rahul"
        )
        self.lease = LeaseService.create(
            actor=self.owner,
            tenant=self.tenant,
            unit=self.unit,
            resident=self.resident,
            start_date=date(2026, 1, 1),
            monthly_rent_cents=rent,
        )
        self.meter = MeterService.create(
            actor=self.owner, tenant=self.tenant, unit=self.unit, meter_number=f"ELEC-203-{slug}"
        )
        if rate is not None:
            self.tariff = TariffService.create(
                actor=self.owner, tenant=self.tenant, rate_per_unit_cents=Decimal(rate), effective_from=date(2026, 1, 1)
            )

    def reading(self, day, value):
        return MeterReadingService.record(
            actor=self.owner, tenant=self.tenant, meter=self.meter, reading_date=day, reading_value=Decimal(str(value))
        )

    def cycle(self, year=2026, month=3):
        cycle, _ = BillingCycleService.open(actor=self.owner, tenant=self.tenant, year=year, month=month)
        return cycle

    def march_bill(self, publish=True):
        self.reading(date(2026, 2, 28), "12450")
        self.reading(date(2026, 3, 31), "12610")
        cycle = self.cycle()
        created, skipped = BillingCycleService.generate(actor=self.owner, cycle=cycle)
        assert created, skipped
        bill = created[0]
        if publish:
            bill = BillService.publish(actor=self.owner, bill=bill)
        return bill

    def pay(self, bill, amount, **kwargs):
        kwargs.setdefault("payment_date", date(2026, 4, 5))
        kwargs.setdefault("method", "UPI")
        return PaymentService.record(actor=self.owner, tenant=self.tenant, bill=bill, amount_cents=amount, **kwargs)

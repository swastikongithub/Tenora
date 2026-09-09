"""
Create a gateway-side plan for every local Plan that doesn't have one yet, and
store the returned id on `Plan.external_plan_id` (stage-d1-spec.md §4.2).

Idempotent: only Plans with `external_plan_id IS NULL` are touched, so a second
run is a no-op for anything already synced. Uses the active gateway adapter
(`settings.PAYMENT_GATEWAY`); with `razorpay` it needs real test-mode API keys.

    python manage.py sync_razorpay_plans

The single narrow gap (create-plan has no idempotency key): a crash between the
gateway call and the local write would orphan a gateway-side plan — see
PlanSyncService.sync_plan.
"""

from django.core.management.base import BaseCommand

from apps.billing.models import Plan
from apps.billing.services import PlanSyncService


class Command(BaseCommand):
    help = "Create gateway plans for local Plans missing an external_plan_id."

    def handle(self, *args, **options):
        unmapped = Plan.objects.filter(external_plan_id__isnull=True).order_by(
            "price_cents", "name"
        )
        already = Plan.objects.exclude(external_plan_id__isnull=True).count()

        if not unmapped.exists():
            self.stdout.write(
                self.style.SUCCESS(
                    f"Nothing to do — all {already} plan(s) already mapped."
                )
            )
            return

        created = 0
        for plan in unmapped:
            external_plan_id = PlanSyncService.sync_plan(plan)
            created += 1
            self.stdout.write(f"  {plan.code} -> {external_plan_id}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {created} plan(s); {already} were already mapped."
            )
        )

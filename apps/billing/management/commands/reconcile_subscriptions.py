"""
Cross-check local `Subscription` status against the payment provider's reported
status and record any drift (docs/stage-d8-spec.md).

    python manage.py reconcile_subscriptions

This is the MANUAL entry point (on-demand runs, debugging). Since Stage D8 the
same sweep also runs hourly on a schedule — both this command and the
`billing.reconcile_subscriptions` Celery task are thin callers of
`ReconciliationService.reconcile_all()`, which owns the orchestration.

READ-ONLY and detection-only: nothing is corrected locally and nothing is
written back to the provider. Eligibility is every `Subscription` that has an
`external_subscription_id` (only those exist at the provider); a
locally-CANCELED subscription with a provider id IS reconciled, because
`local CANCELED / provider still live` is the drift most worth catching.
"""

from django.core.management.base import BaseCommand

from apps.billing.services import ReconciliationService


class Command(BaseCommand):
    help = (
        "Reconcile local subscription status against the payment provider; "
        "record drift as ReconciliationDiscrepancy rows. Read-only, no correction."
    )

    def handle(self, *args, **options):
        result = ReconciliationService.reconcile_all()

        if not result.total:
            self.stdout.write(
                self.style.SUCCESS(
                    "Nothing to do — no subscription has a provider id yet."
                )
            )
            return

        for item in result.checked:
            label = item.external_subscription_id or "(no id)"
            if item.outcome == ReconciliationService.ERROR:
                self.stderr.write(self.style.ERROR(f"  {label}: {item.error}"))
            elif item.outcome == ReconciliationService.DISCREPANCY:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {label} -> DISCREPANCY ({item.category})"
                    )
                )
            else:
                self.stdout.write(f"  {label} -> {item.outcome}")

        summary = (
            f"Reconciled {result.total} subscription(s): "
            f"{len(result.matched)} matched, "
            f"{len(result.discrepancies)} discrepancies, "
            f"{len(result.unavailable)} unavailable, "
            f"{len(result.skipped)} skipped"
        )
        if result.errors:
            summary += f", {len(result.errors)} errors"
        style = self.style.SUCCESS if not result.errors else self.style.WARNING
        self.stdout.write(style(summary + "."))

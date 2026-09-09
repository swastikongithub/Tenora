"""
Snapshot per-tenant usage for the current billing period (docs/stage-d5-spec.md
§4.3).

    python manage.py meter_usage

This is the MANUAL entry point. Since Stage D7 the same snapshot also runs
daily on a schedule — both this command and the `billing.meter_usage` Celery
task are thin callers of `UsageMeteringService.snapshot_all_subscribed()`,
which owns the orchestration.

Eligibility: every tenant that has a `Subscription` row, regardless of its
status — TRIALING, ACTIVE, PAST_DUE and CANCELED are all metered, because the
row's `current_period_start` / `current_period_end` are the real period
boundaries the snapshot records against (spec §8). A tenant with no
`Subscription` row has no real period and is skipped, never given an invented
one.

Idempotent: `UsageRecord`'s `unique_usage_snapshot` constraint absorbs a
re-run for an already-recorded (tenant, metric, period) — a second run in the
same period creates zero new rows.
"""

from django.core.management.base import BaseCommand

from apps.billing.services import UsageMeteringService


class Command(BaseCommand):
    help = (
        "Snapshot per-tenant usage (active member count) for the current "
        "billing period. Meters every tenant with a Subscription row, any status."
    )

    def handle(self, *args, **options):
        result = UsageMeteringService.snapshot_all_subscribed()

        if not result.total:
            self.stdout.write(
                self.style.SUCCESS("Nothing to do — no tenant has a subscription.")
            )
            return

        for record in result.records:
            self.stdout.write(
                f"  {record.tenant.slug}: {record.metric}={record.quantity} "
                f"[{record.period_start:%Y-%m-%d}…{record.period_end:%Y-%m-%d}]"
            )

        summary = (
            f"Metered {result.total} tenant(s): {len(result.records)} new, "
            f"{result.existing} already recorded this period"
        )
        if result.skipped:
            summary += f", {result.skipped} skipped (no subscription)"
        self.stdout.write(self.style.SUCCESS(summary + "."))

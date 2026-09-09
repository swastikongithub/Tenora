"""
Retry / backfill D3 processing for stored webhook events that haven't been
applied yet (stage-d3-v2-spec.md §4.3, stage-d4-spec.md §4.2).

Inline processing in `RazorpayWebhookView` is best-effort — if it raised, the
`WebhookEvent` row is still stored with `processed=False`; a D4 `DEFERRED` row
also stays `processed=False` until its subscription exists. This command sweeps
all such rows.

    python manage.py process_webhook_events

This is the MANUAL entry point (on-demand runs, debugging, recovery). Since
Stage D7 the same sweep also runs on a schedule — both this command and the
`billing.process_webhook_events` Celery task are thin callers of
`WebhookProcessingService.process_pending()`, which owns the orchestration.

Idempotent: `process_event` skips rows already marked processed, and every
handler is a no-op when the state it would set is already in place. A row that
raises is reported and left `processed=False`; the sweep continues.
"""

from django.core.management.base import BaseCommand

from apps.billing.services import WebhookProcessingService


class Command(BaseCommand):
    help = "Retry D3 processing for WebhookEvent rows with processed=False."

    def handle(self, *args, **options):
        result = WebhookProcessingService.process_pending()

        if not result.total:
            self.stdout.write(
                self.style.SUCCESS("Nothing to do — no unprocessed events.")
            )
            return

        for event in result.events:
            label = f"{event.external_event_id} ({event.event_type})"
            if event.error is not None:
                self.stderr.write(self.style.ERROR(f"  {label}: {event.error}"))
            elif event.outcome == WebhookProcessingService.DEFERRED:
                self.stdout.write(f"  {label} -> DEFERRED (will retry)")
            else:
                self.stdout.write(f"  {label} -> {event.outcome}")

        summary = f"Processed {len(result.processed)}/{result.total} event(s)"
        if result.deferred:
            summary += (
                f"; {len(result.deferred)} deferred (still unmatched, will retry)"
            )
        if result.failed:
            summary += f"; {len(result.failed)} failed"
        style = self.style.SUCCESS if not result.failed else self.style.WARNING
        self.stdout.write(style(summary + "."))

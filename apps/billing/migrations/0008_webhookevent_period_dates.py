"""
docs/fix-real-period-dates-spec.md §4.4 — persist the real billing period a
`subscription.charged` webhook reports (`NormalizedEvent.period_start/period_end`)
on the `WebhookEvent` row, so the CHARGED handler and the
`process_webhook_events` backfill command use the provider's dates instead of a
synthesized local period.

Nullable — most event types carry no period. Hand-written to sit legibly beside
0007.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0007_webhook_driven_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhookevent",
            name="period_start",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="webhookevent",
            name="period_end",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]

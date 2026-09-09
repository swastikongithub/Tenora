"""
docs/stage-d4-spec.md — out-of-order event handling.

- `WebhookEvent.event_created_at`: the provider's event-generation time (Razorpay's
  top-level envelope `created_at`), the cross-event-type ordering signal.
- `Subscription.last_event_at`: per-subscription high-water mark — the
  `event_created_at` of the most recent event applied to it. Processing refuses
  to apply an event older than this.

Both nullable (no backfill: the payload may not carry the timestamp, and a
subscription has no mark until a post-creation event applies). Hand-written to
sit legibly beside 0007/0008.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0008_webhookevent_period_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhookevent",
            name="event_created_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="last_event_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]

"""
stage-d3-v2-spec.md §4.1 — the correlation fields that let a verified webhook
event drive `Subscription` state.

- `Subscription.external_subscription_id`: nullable, unique-when-set — the
  gateway-side id D3 stamps on the row it creates from the ACTIVATED event.
- `WebhookEvent.external_subscription_id`: nullable, indexed (NOT unique) — the
  normalized correlation key, copied from `NormalizedEvent` at storage time so
  processing never re-parses `raw_payload`.

Hand-written (not makemigrations) to keep the intent legible alongside 0006.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_rename_gateway_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="external_subscription_id",
            field=models.CharField(
                max_length=255, null=True, blank=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="webhookevent",
            name="external_subscription_id",
            field=models.CharField(
                max_length=255, null=True, blank=True, db_index=True
            ),
        ),
    ]

"""
payment-gateway-adapter-spec.md §4.5 — rename the three provider-specific
external-id fields to generic names while there is no production data, and
widen/constrain WebhookEvent.event_type to the project's EventType vocabulary.

Hand-written (not makemigrations) so the renames are real RenameField ops —
data-preserving column renames, not add+drop.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0005_subscriptioncheckout"),
    ]

    operations = [
        migrations.RenameField(
            model_name="plan",
            old_name="razorpay_plan_id",
            new_name="external_plan_id",
        ),
        migrations.RenameField(
            model_name="subscriptioncheckout",
            old_name="razorpay_subscription_id",
            new_name="external_subscription_id",
        ),
        migrations.RenameField(
            model_name="webhookevent",
            old_name="razorpay_event_id",
            new_name="external_event_id",
        ),
        migrations.AlterField(
            model_name="webhookevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("ACTIVATED", "ACTIVATED"),
                    ("CHARGED", "CHARGED"),
                    ("CANCELLED", "CANCELLED"),
                    ("PAYMENT_TROUBLE", "PAYMENT_TROUBLE"),
                    ("UNKNOWN", "UNKNOWN"),
                ],
                max_length=32,
            ),
        ),
    ]

"""Manual entry point for the P9 online-payment reconciliation sweep (the same
service method the scheduled task calls)."""

from django.core.management.base import BaseCommand

from apps.properties.online_payments import OnlinePaymentService


class Command(BaseCommand):
    help = "Settle or expire open online resident payment checkouts by asking the payment provider."

    def handle(self, *args, **options):
        counts = OnlinePaymentService.reconcile_open()
        self.stdout.write(
            f"checked={counts['checked']} settled={counts['settled']} expired={counts['expired']}"
        )

from django.core.management.base import BaseCommand

from apps.properties.reminders import send_billing_reminders


class Command(BaseCommand):
    help = "Send in-app due-soon / overdue / incomplete-cycle billing reminders (idempotent)."

    def handle(self, *args, **options):
        result = send_billing_reminders()
        self.stdout.write(self.style.SUCCESS(f"Reminders: {result.as_dict()}"))

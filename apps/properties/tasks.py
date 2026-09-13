"""Scheduled entry point for property billing reminders. Calls the same function
as `manage.py send_billing_reminders`; idempotent through notification dedupe
keys, so an overlapping or retried run notifies nobody twice. Billing state is
never changed by this task — manual workflow stays fully usable without a worker.
"""

from celery import shared_task

from apps.properties.reminders import send_billing_reminders


@shared_task(name="properties.send_billing_reminders")
def send_billing_reminders_task():
    return send_billing_reminders().as_dict()

"""
Wraps Django's own mail machinery (django.core.mail.send_mail) — the
provider used whenever EMAIL_PROVIDER is unset or "django" (the safe local/
test default: settings.EMAIL_BACKEND defaults to the console backend, so
this needs no credentials and no network access). A deployment that wants
real SMTP delivery instead of Brevo can still do so through this same
provider by setting EMAIL_BACKEND/EMAIL_HOST/... — those settings are
untouched by the Brevo addition.
"""

from django.conf import settings
from django.core.mail import send_mail

from apps.users.email_delivery.base import EmailDeliveryError, EmailProvider


class DjangoEmailProvider(EmailProvider):
    def send(self, *, to_email: str, subject: str, body: str) -> None:
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
            )
        except OSError as exc:
            # smtplib.SMTPException (and its subclasses) has been a subclass
            # of OSError since Python 3.4 — a real SMTP backend's connection/
            # auth/timeout failures surface this way. The console and locmem
            # backends used by local dev and the automated test suite never
            # raise it.
            raise EmailDeliveryError(f"Django email backend failed: {exc}") from exc

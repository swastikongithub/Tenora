"""
One-time superuser bootstrap for hosts with no shell/SSH access (e.g.
Render's Free plan, where `manage.py createsuperuser`'s interactive prompt
can't be run at all). Called by docker-entrypoint.sh on every container
start, after migrations.

Idempotent and safe to leave wired in permanently, the same way
seed_demo_data is: does nothing unless both DJANGO_SUPERUSER_EMAIL and
DJANGO_SUPERUSER_PASSWORD are set, and even then only creates a user when no
row with that email already exists -- an existing user (superuser or not) is
left completely untouched, password included. The password is read from the
environment and handed straight to set_password(); it is never written to
stdout/stderr.
"""

import os

from django.core.management.base import BaseCommand

from apps.users.models import User


class Command(BaseCommand):
    help = (
        "Create the first Django superuser from the DJANGO_SUPERUSER_EMAIL "
        "and DJANGO_SUPERUSER_PASSWORD environment variables, if both are "
        "set and no user with that email exists yet. A no-op otherwise."
    )

    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not email or not password:
            return

        normalized_email = User.objects.normalize_email(email)
        if User.objects.filter(email=normalized_email).exists():
            self.stdout.write(
                f"Superuser bootstrap: {normalized_email} already exists, "
                "skipping."
            )
            return

        User.objects.create_superuser(
            email=normalized_email,
            password=password,
            is_active=True,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Superuser bootstrap: created {normalized_email}.")
        )

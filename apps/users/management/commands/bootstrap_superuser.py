"""
Superuser bootstrap/promotion for hosts with no shell/SSH access (e.g.
Render's Free plan, where `manage.py createsuperuser`'s interactive prompt
can't be run at all, and there is no other way to grant the first operator
account platform access). Called by docker-entrypoint.sh on every container
start, after migrations.

A no-op unless both DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD are
set — that pair being present in the environment IS the deployment's
authorization to run this; nothing else gates it, and both are Render
environment variables, never request input.

Two cases, both idempotent (safe to run on every deploy, indefinitely):

  - No user with that email exists yet: create one as a fully active,
    verified superuser (is_staff/is_superuser/is_active/email_verified all
    True), password from DJANGO_SUPERUSER_PASSWORD.

  - A user with that email ALREADY exists — this is the real-world case a
    prior version of this command got wrong: it silently did nothing,
    leaving an existing account (e.g. one that signed up normally, or an
    older bootstrap run whose flags didn't yet include email_verified)
    exactly as it was, with no way to promote it short of shell/DB access.
    Now: PROMOTE it in place — set is_staff/is_superuser/is_active/
    email_verified all True — and touch NOTHING else. The password is
    deliberately never read for this branch: DJANGO_SUPERUSER_PASSWORD only
    ever seeds a BRAND NEW account; an existing one keeps whatever
    credential it already has, full stop.

The password (when used, only on the create branch) is handed straight to
set_password() via create_superuser(); it is never written to stdout/stderr
in either branch.
"""

import os

from django.core.management.base import BaseCommand

from apps.users.models import User

# The fields a bootstrap promotes an existing user to, and the same target
# state a freshly created one starts in. Listed once so "what does bootstrap
# actually grant" has one answer, read by both branches below.
_PROMOTED_FIELDS = {
    "is_staff": True,
    "is_superuser": True,
    "is_active": True,
    "email_verified": True,
}


class Command(BaseCommand):
    help = (
        "Bootstrap the first platform operator from DJANGO_SUPERUSER_EMAIL "
        "and DJANGO_SUPERUSER_PASSWORD (a no-op unless both are set). "
        "Creates a fully active, verified superuser if no user with that "
        "email exists; PROMOTES an existing user with that email in place "
        "(is_staff/is_superuser/is_active/email_verified -> True) without "
        "touching its password or any other field. Idempotent."
    )

    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not email or not password:
            return

        normalized_email = User.objects.normalize_email(email)

        try:
            user = User.objects.get(email=normalized_email)
        except User.DoesNotExist:
            User.objects.create_superuser(
                email=normalized_email, password=password, **_PROMOTED_FIELDS
            )
            self.stdout.write(
                self.style.SUCCESS(f"Superuser bootstrap: created {normalized_email}.")
            )
            return

        # Promote in place — explicit about exactly which fields change, and
        # a true no-op (no write) once a user is already fully promoted, so
        # this reads cleanly on every subsequent deploy.
        changed_fields = [
            field
            for field, target in _PROMOTED_FIELDS.items()
            if getattr(user, field) != target
        ]
        if not changed_fields:
            self.stdout.write(
                f"Superuser bootstrap: {normalized_email} already fully "
                "promoted, no-op."
            )
            return

        for field in changed_fields:
            setattr(user, field, _PROMOTED_FIELDS[field])
        user.save(update_fields=changed_fields)
        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser bootstrap: promoted {normalized_email} "
                f"({', '.join(changed_fields)})."
            )
        )

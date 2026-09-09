"""
The email_verified grandfathering migration (users/0003) —
email-verification-spec.md §1/§4.1/§9/§10.6: "a real test against migrated
data, not just a unit assumption."

Uses Django's MigrationExecutor directly to migrate to the state immediately
BEFORE 0003, insert a row via the historical model, migrate forward through
0003, then assert on the row via the current model — proving the RunPython
step actually grandfathers pre-existing rows, not just that the code reads
as if it should.
"""

import uuid

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

APP = "users"
MIGRATE_FROM = [(APP, "0002_alter_user_managers")]
MIGRATE_TO = [(APP, "0003_user_email_verified_emailverificationtoken")]


class GrandfatheringMigrationTests(TransactionTestCase):
    def test_pre_existing_user_is_grandfathered_as_verified(self):
        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_FROM)

        old_apps = executor.loader.project_state(MIGRATE_FROM).apps
        OldUser = old_apps.get_model(APP, "User")
        OldUser.objects.create(
            id=uuid.uuid4(),
            email="preexisting@example.com",
            password="unusable-hash",
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

        # Re-fetch a fresh executor — the loader's migration graph is stale
        # after the first migrate() call.
        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)

        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewUser = new_apps.get_model(APP, "User")
        migrated_user = NewUser.objects.get(email="preexisting@example.com")

        self.assertTrue(migrated_user.email_verified)

    def test_user_created_after_the_migration_defaults_unverified(self):
        # Sanity check the other half of the contract: the field's own
        # default (False) governs everything from here on — grandfathering
        # is a one-time backfill, not an ongoing rule.
        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)

        apps_after = executor.loader.project_state(MIGRATE_TO).apps
        NewUser = apps_after.get_model(APP, "User")
        fresh_user = NewUser.objects.create(
            id=uuid.uuid4(),
            email="fresh@example.com",
            password="unusable-hash",
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

        self.assertFalse(fresh_user.email_verified)

"""
AuditEvent model + AuditService — docs/operator-control-plane-spec.md §B
"Audit semantics: critical vs. observational".

Two explicit write paths, tested for the two different guarantees each
makes: record_critical must roll back its caller's whole transaction on
failure (never a silent, audit-less mutation); record_observational must
never raise, ever (never block the action it's describing).
"""

from unittest import mock

from django.db import transaction
from django.test import TestCase

from apps.platform.models import AuditEvent
from apps.platform.services import AuditService
from apps.tenants.models import Tenant
from apps.users.models import User

PASSWORD = "correct-horse-staple-42"


class AuditServiceCriticalTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )

    def test_record_critical_writes_a_critical_row(self):
        AuditService.record_critical(
            actor=self.actor,
            action="subscription.transitioned",
            target_type="Subscription",
            target_id="sub-123",
            summary="Transitioned subscription from ACTIVE to CANCELED",
            metadata={"from_status": "ACTIVE", "to_status": "CANCELED"},
        )

        event = AuditEvent.objects.get()
        self.assertTrue(event.is_critical)
        self.assertEqual(event.actor, self.actor)
        self.assertEqual(event.action, "subscription.transitioned")
        self.assertEqual(event.target_type, "Subscription")
        self.assertEqual(event.target_id, "sub-123")
        self.assertEqual(
            event.metadata, {"from_status": "ACTIVE", "to_status": "CANCELED"}
        )

    def test_record_critical_failure_rolls_back_the_whole_enclosing_transaction(self):
        # Proves the real mechanism this design depends on: record_critical
        # raises on failure (nothing catches it), and because it runs inside
        # the SAME transaction.atomic() block as a prior write, that prior
        # write is undone too — not just the audit row.
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    Tenant.objects.create(name="Should Not Persist", slug="rollback-me")
                    AuditService.record_critical(
                        actor=self.actor,
                        action="tenant.would_be_critical",
                        target_type="Tenant",
                        target_id="whatever",
                        summary="…",
                    )

        self.assertFalse(Tenant.objects.filter(slug="rollback-me").exists())
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_target_id_is_always_stored_as_a_string(self):
        AuditService.record_critical(
            actor=self.actor,
            action="plan.created",
            target_type="Plan",
            target_id=42,  # e.g. an int/UUID caller — never assume str already
            summary="…",
        )
        event = AuditEvent.objects.get()
        self.assertEqual(event.target_id, "42")
        self.assertIsInstance(event.target_id, str)

    def test_metadata_defaults_to_an_empty_dict_not_none(self):
        AuditService.record_critical(
            actor=self.actor,
            action="plan.archived",
            target_type="Plan",
            target_id="plan-1",
            summary="…",
        )
        self.assertEqual(AuditEvent.objects.get().metadata, {})


class AuditServiceObservationalTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            email="operator@example.com", password=PASSWORD, is_staff=True
        )

    def test_record_observational_writes_a_non_critical_row(self):
        AuditService.record_observational(
            actor=self.actor,
            action="webhook.sweep_triggered",
            target_type="WebhookEvent",
            target_id="*",
            summary="Webhook retry sweep: 3 checked, 3 processed",
            metadata={"total": 3, "processed": 3},
        )
        event = AuditEvent.objects.get()
        self.assertFalse(event.is_critical)
        self.assertEqual(event.metadata, {"total": 3, "processed": 3})

    def test_record_observational_never_raises_on_failure(self):
        with mock.patch(
            "apps.platform.services.AuditEvent.objects.create",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise — this is the whole contract.
            AuditService.record_observational(
                actor=self.actor,
                action="reconciliation.sweep_triggered",
                target_type="Subscription",
                target_id="*",
                summary="…",
            )
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_record_observational_failure_is_logged(self):
        with self.assertLogs("apps.platform.services", level="ERROR") as logs:
            with mock.patch(
                "apps.platform.services.AuditEvent.objects.create",
                side_effect=RuntimeError("boom"),
            ):
                AuditService.record_observational(
                    actor=self.actor,
                    action="usage.sweep_triggered",
                    target_type="Tenant",
                    target_id="*",
                    summary="…",
                )
        self.assertTrue(
            any("usage.sweep_triggered" in message for message in logs.output)
        )


class AuditEventActorDeletionTests(TestCase):
    def test_deleting_the_actor_leaves_audit_actor_null_not_deleted(self):
        actor = User.objects.create_user(email="gone@example.com", password=PASSWORD)
        AuditService.record_critical(
            actor=actor,
            action="subscription.transitioned",
            target_type="Subscription",
            target_id="sub-1",
            summary="…",
        )
        event_id = AuditEvent.objects.get().id

        actor.delete()

        event = AuditEvent.objects.get(pk=event_id)
        self.assertIsNone(event.actor)
        # The row itself survives — the whole point of SET_NULL over CASCADE.
        self.assertEqual(event.action, "subscription.transitioned")

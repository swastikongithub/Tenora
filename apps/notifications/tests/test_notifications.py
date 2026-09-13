from datetime import date

from rest_framework.test import APITestCase

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.properties.reminders import send_billing_reminders
from apps.properties.services import BillCorrectionService
from apps.properties.tests.factories import Scenario, bearer, make_user


class BillingNotificationTests(APITestCase):
    def test_publish_payment_and_receipt_notify_the_resident(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 1_378_000)
        kinds = set(Notification.objects.filter(recipient=s.user).values_list("kind", flat=True))
        self.assertTrue({"INVITATION_RECEIVED", "BILL_PUBLISHED", "PAYMENT_RECORDED", "RECEIPT_ISSUED"} <= kinds)

    def test_correction_notifies_resident(self):
        s = Scenario()
        bill = s.march_bill()
        BillCorrectionService.adjust_amount(actor=s.owner, bill=bill, amount_delta_cents=-100, reason="x")
        self.assertTrue(Notification.objects.filter(recipient=s.user, kind="BILL_CORRECTED").exists())

    def test_overdue_reminders_are_idempotent_and_summarised_for_owner(self):
        s = Scenario()
        s.march_bill()
        first = send_billing_reminders(today=date(2026, 4, 25))
        second = send_billing_reminders(today=date(2026, 4, 25))
        self.assertEqual((first.overdue, first.owner_summaries), (1, 1))
        self.assertEqual((second.overdue, second.owner_summaries), (0, 0))
        self.assertEqual(Notification.objects.filter(recipient=s.user, kind="BILL_OVERDUE").count(), 1)
        # A new aging bucket earns one more reminder.
        self.assertEqual(send_billing_reminders(today=date(2026, 5, 20)).overdue, 1)

    def test_due_soon_reminder(self):
        s = Scenario()
        s.march_bill()  # due 2026-04-10
        self.assertEqual(send_billing_reminders(today=date(2026, 4, 8)).due_soon, 1)

    def test_muted_category_is_not_delivered_but_invitations_always_are(self):
        user = make_user("quiet@example.com")
        NotificationService.update_preferences(user=user, changes={"billing": False, "membership": False})
        self.assertIsNone(NotificationService.notify(recipient=user, kind="BILL_PUBLISHED", title="x"))
        self.assertIsNotNone(NotificationService.notify(recipient=user, kind="INVITATION_RECEIVED", title="x"))


class NotificationApiTests(APITestCase):
    def test_list_count_and_mark_read_are_scoped_to_the_caller(self):
        me = make_user("me@example.com")
        other = make_user("other@example.com")
        mine = NotificationService.notify(recipient=me, kind="BILL_PUBLISHED", title="mine")
        theirs = NotificationService.notify(recipient=other, kind="BILL_PUBLISHED", title="theirs")
        bearer(self.client, me)
        body = self.client.get("/api/notifications/").data
        self.assertEqual([n["id"] for n in body["results"]], [str(mine.id)])
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data, {"unread": 1})
        resp = self.client.post("/api/notifications/read/", {"ids": [str(theirs.id), str(mine.id)]}, format="json")
        self.assertEqual(resp.data, {"updated": 1})
        theirs.refresh_from_db()
        self.assertIsNone(theirs.read_at)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data, {"unread": 0})

    def test_preferences_round_trip(self):
        me = make_user("me@example.com")
        bearer(self.client, me)
        self.assertTrue(self.client.get("/api/notifications/preferences/").data["billing"])
        resp = self.client.patch("/api/notifications/preferences/", {"billing": False}, format="json")
        self.assertFalse(resp.data["billing"])

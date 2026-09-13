"""Account profile, password and deletion (property-billing plan §27.3–27.5)."""

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.properties.models import Bill, Resident
from apps.properties.tests.factories import PASSWORD, Scenario, bearer, make_user
from apps.tenants.models import Membership
from apps.users.models import User


class AccountProfileTests(APITestCase):
    def test_profile_read_and_update(self):
        user = make_user("me@example.com")
        bearer(self.client, user)
        resp = self.client.patch("/api/account/profile/", {"first_name": "Rahul", "phone": "+91 98765 43210", "email": "x@y.z", "is_staff": True}, format="json")
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.phone, user.email, user.is_staff), ("Rahul", "+91 98765 43210", "me@example.com", False))

    def test_password_change_requires_current_password(self):
        user = make_user("me@example.com")
        bearer(self.client, user)
        bad = self.client.post("/api/account/password/", {"current_password": "nope", "new_password": "An0ther-strong-pass"}, format="json")
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post("/api/account/password/", {"current_password": PASSWORD, "new_password": "An0ther-strong-pass"}, format="json")
        self.assertEqual(ok.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("An0ther-strong-pass"))


class AccountDeletionTests(APITestCase):
    def test_requires_typed_email_confirmation(self):
        user = make_user("me@example.com")
        bearer(self.client, user)
        resp = self.client.post("/api/account/delete/", {"confirmation": "DELETE"}, format="json")
        self.assertEqual(resp.status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_owner_of_a_workspace_is_blocked(self):
        s = Scenario()
        bearer(self.client, s.owner)
        resp = self.client.post("/api/account/delete/", {"confirmation": s.owner.email}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "owns_workspaces")
        s.owner.refresh_from_db()
        self.assertTrue(s.owner.is_active)

    def test_resident_deletion_anonymizes_revokes_access_and_keeps_bills(self):
        s = Scenario()
        bill = s.march_bill()
        s.pay(bill, 1_000)
        refresh = RefreshToken.for_user(s.user)
        access = str(AccessToken.for_user(s.user))
        email = s.user.email
        bearer(self.client, s.user)
        resp = self.client.post("/api/account/delete/", {"confirmation": email.upper()}, format="json")
        self.assertEqual(resp.status_code, 200)

        user = User.objects.get(pk=s.user.pk)
        self.assertFalse(user.is_active)
        self.assertNotEqual(user.email, email)
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.deleted_at)
        self.assertEqual(Membership.objects.get(user=user, tenant=s.tenant).status, "LEFT")
        self.assertEqual(Resident.objects.get(pk=s.resident.pk).status, "INACTIVE")

        # Existing tokens no longer work.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get("/api/users/me/").status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": str(refresh)}).status_code, 401)

        # Financial history intact, with its issued snapshot.
        bill.refresh_from_db()
        self.assertEqual(bill.total_cents, 1_378_000)
        self.assertEqual(bill.amount_paid_cents, 1_000)
        self.assertEqual(Bill.objects.filter(resident=s.resident).count(), 1)

        # The email can register a genuinely fresh account with no inherited state.
        fresh = self.client.post("/api/auth/register/", {"email": email, "password": "Fresh-start-99x"}, format="json")
        self.assertIn(fresh.status_code, (201, 502))
        new_user = User.objects.get(email=email)
        self.assertNotEqual(new_user.pk, user.pk)
        self.assertFalse(Membership.objects.filter(user=new_user).exists())

    def test_last_root_cannot_delete_itself(self):
        root = make_user("root@example.com", is_staff=True, is_superuser=True)
        bearer(self.client, root)
        resp = self.client.post("/api/account/delete/", {"confirmation": root.email}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "last_root")

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import MasterProfile, UserProfile


class MasterPhoneUpdateAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            username="superadmin",
            email="admin@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
        )
        UserProfile.objects.create(user=self.admin_user, phone="+18000000000")
        self.client.force_login(self.admin_user)

    def _create_master(self, *, phone: str, first_name: str = "Alice", last_name: str = "Master") -> MasterProfile:
        User = get_user_model()
        user = User.objects.create_user(
            username=phone,
            email=f"{first_name.lower()}_{phone.strip('+')}@example.com",
            password="pass1234",
            first_name=first_name,
            last_name=last_name,
        )
        profile = UserProfile.objects.create(user=user, phone=phone)
        return MasterProfile.objects.create(user=profile, profession="Stylist")

    def _build_change_form_data(self, master: MasterProfile):
        url = reverse("admin:core_masterprofile_change", args=[master.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        form = response.context["adminform"].form
        user_profile = master.user
        auth_user = user_profile.user

        data = {
            "email": auth_user.email,
            "first_name": auth_user.first_name,
            "last_name": auth_user.last_name,
            "phone": user_profile.phone or "",
            "postal_code": user_profile.postal_code or "",
            "profession": master.profession or "",
            "bio": master.bio or "",
            "services": [],
            "_save": "Save",
        }

        # Password read-only hash field must be posted back to avoid validation complaints.
        if "password" in form.fields:
            data["password"] = form.initial.get("password", "")

        birth_date = user_profile.birth_date
        if birth_date:
            data["birth_date_year"] = str(birth_date.year)
            data["birth_date_month"] = str(birth_date.month)
            data["birth_date_day"] = str(birth_date.day)
        else:
            data["birth_date_year"] = ""
            data["birth_date_month"] = ""
            data["birth_date_day"] = ""

        return url, data

    def test_edit_master_without_phone_change_succeeds(self):
        master = self._create_master(phone="+15550000001")
        url, data = self._build_change_form_data(master)

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "already registered", status_code=200)

        master.refresh_from_db()
        self.assertEqual(master.user.phone, "+15550000001")
        self.assertEqual(master.user.user.username, "+15550000001")

    def test_edit_master_with_new_unique_phone_updates_username(self):
        master = self._create_master(phone="+15550000002", first_name="Betty")
        url, data = self._build_change_form_data(master)
        new_phone = "+15550009999"
        data["phone"] = new_phone

        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        master.refresh_from_db()

        self.assertEqual(master.user.phone, new_phone)
        self.assertEqual(master.user.user.username, new_phone)

    def test_edit_master_with_existing_phone_shows_error(self):
        other = self._create_master(phone="+16660000000", first_name="Clara")
        master = self._create_master(phone="+15550000003", first_name="Diana")

        url, data = self._build_change_form_data(master)
        data["phone"] = other.user.phone

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered")

        master.refresh_from_db()
        self.assertEqual(master.user.phone, "+15550000003")
        self.assertEqual(master.user.user.username, "+15550000003")

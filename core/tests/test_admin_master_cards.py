from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import MasterProfile, MasterRoom, UserProfile


class MasterAdminCardsTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
        )
        UserProfile.objects.get_or_create(user=self.superuser, defaults={"phone": "+18000000000"})
        self.client.force_login(self.superuser)
        self.url = reverse("admin:core_masterprofile_changelist")

        self.room_one = MasterRoom.objects.create(room="Room 1")
        self.room_two = MasterRoom.objects.create(room="Room 2")

        self.master_anna = self._make_master(
            username="anna",
            first_name="Anna",
            last_name="Baker",
            email="anna@example.com",
            phone="+15550001",
            room=self.room_one,
            profession="Hair Stylist",
        )
        self.master_bella = self._make_master(
            username="bella",
            first_name="Bella",
            last_name="Clark",
            email="bella@example.com",
            phone="+15550002",
            room=self.room_two,
            profession="Nail Technician",
        )
        self.master_cara = self._make_master(
            username="cara",
            first_name="Cara",
            last_name="Dunn",
            email="cara@example.com",
            phone="+15550003",
            room=None,
            profession="Hair Stylist",
        )

    @staticmethod
    def _make_master(username, first_name, last_name, email, phone, room, profession):
        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=email,
            password="pass1234",
            first_name=first_name,
            last_name=last_name,
        )
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"phone": phone})
        if profile.phone != phone:
            profile.phone = phone
            profile.save(update_fields=["phone"])
        return MasterProfile.objects.create(user=profile, room=room, profession=profession)

    def _names(self, response):
        return [obj.user.user.first_name for obj in response.context["cl"].result_list]

    def test_default_order_a_to_z(self):
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), ["Anna", "Bella", "Cara"])

    def test_sort_z_to_a(self):
        response = self.client.get(self.url, {"name_order": "za"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), ["Cara", "Bella", "Anna"])

    def test_filter_by_room(self):
        response = self.client.get(self.url, {"room": str(self.room_one.pk)}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), ["Anna"])

    def test_filter_by_room_unassigned(self):
        response = self.client.get(self.url, {"room": "none"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), ["Cara"])

    def test_filter_by_profession(self):
        response = self.client.get(self.url, {"profession": "Hair Stylist"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), ["Anna", "Cara"])

    def test_search_by_name(self):
        response = self.client.get(self.url, {"q": "Bella"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), ["Bella"])

    def test_search_by_phone(self):
        response = self.client.get(self.url, {"q": "0002"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), ["Bella"])

    def test_search_by_email(self):
        response = self.client.get(self.url, {"q": "cara@example.com"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), ["Cara"])

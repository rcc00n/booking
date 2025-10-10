from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import UserProfile


class UserAdminCardsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        now = timezone.now()

        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        self.superuser.date_joined = now - timedelta(days=120)
        self.superuser.save()
        self._ensure_profile(self.superuser, "+1000000000")

        self.regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="password123",
        )
        self.regular_user.date_joined = now - timedelta(days=60)
        self.regular_user.save()
        self._ensure_profile(self.regular_user, "+1000000001")

        self.new_user = User.objects.create_user(
            username="newbie",
            email="newbie@example.com",
            password="password123",
        )
        self.new_user.date_joined = now - timedelta(days=5)
        self.new_user.save()
        self._ensure_profile(self.new_user, "+1000000002")

        self.client.force_login(self.superuser)
        self.url = reverse("admin:auth_user_changelist")

    @staticmethod
    def _ensure_profile(user, phone):
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={"phone": phone},
        )
        if not created and profile.phone != phone:
            profile.phone = phone
            profile.save(update_fields=["phone"])
        return profile

    def _dates_from_response(self, response):
        return [user.date_joined for user in response.context["cl"].result_list]

    def test_default_order_newest_first(self):
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        dates = self._dates_from_response(response)
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_sort_oldest_first(self):
        response = self.client.get(self.url, {"user_order": "oldest"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user_order_current"], "oldest")
        dates = self._dates_from_response(response)
        self.assertEqual(dates, sorted(dates))

    def test_filter_new_clients(self):
        response = self.client.get(self.url, {"client_status": "new"}, follow=True)
        self.assertEqual(response.status_code, 200)
        usernames = {user.username for user in response.context["cl"].result_list}
        self.assertSetEqual(usernames, {self.new_user.username})

    def test_filter_regular_clients(self):
        response = self.client.get(self.url, {"client_status": "regular"}, follow=True)
        self.assertEqual(response.status_code, 200)
        usernames = {user.username for user in response.context["cl"].result_list}
        expected = {self.superuser.username, self.regular_user.username}
        self.assertSetEqual(usernames, expected)

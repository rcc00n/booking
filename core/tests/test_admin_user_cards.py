import json
import re
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

    def test_pagination_controls(self):
        User = get_user_model()
        base_time = timezone.now()
        for idx in range(12):
            user = User.objects.create_user(
                username=f"extra{idx}",
                email=f"extra{idx}@example.com",
                password="password123",
            )
            user.date_joined = base_time - timedelta(days=idx + 1)
            user.save()
            self._ensure_profile(user, f"+1999000{idx:03d}")

        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        pagination = response.context["user_pagination"]
        self.assertTrue(pagination["has_next"])
        self.assertFalse(pagination["has_previous"])
        self.assertEqual(pagination["next_page"], 2)

        html = response.content.decode()
        next_link = re.search(r'href="([^"]+)"[^>]*>\s*Next\s*<', html)
        self.assertIsNotNone(next_link)
        self.assertIn("p=2", next_link.group(1))

        response_page2 = self.client.get(self.url, {"p": 2}, follow=True)
        self.assertEqual(response_page2.status_code, 200)
        pagination_page2 = response_page2.context["user_pagination"]
        self.assertTrue(pagination_page2["has_previous"])
        self.assertFalse(pagination_page2["has_next"])
        self.assertEqual(pagination_page2["previous_page"], 1)
        html_page2 = response_page2.content.decode()
        prev_link = re.search(r'href="([^"]+)"[^>]*>\s*Previous\s*<', html_page2)
        self.assertIsNotNone(prev_link)
        self.assertNotIn("p=1", prev_link.group(1))

    def test_ajax_fragment_search(self):
        response = self.client.get(self.url, {"q": "new"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn("newbie", payload["html"])
        self.assertIn("result_count", payload["meta"])

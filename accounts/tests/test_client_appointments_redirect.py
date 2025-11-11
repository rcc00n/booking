from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import UserProfile


class ClientAppointmentsRedirectTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def _make_user(self, username: str) -> tuple:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass12345",
        )
        profile = UserProfile.objects.create(user=user)
        return user, profile

    def test_redirects_to_dashboard_anchor(self):
        user, _ = self._make_user("client-redirect")
        self.client.force_login(user)

        response = self.client.get(reverse("client_appointments"))

        self.assertEqual(response.status_code, 302)
        expected_target = reverse("dashboard") + "#appointments"
        self.assertEqual(response["Location"], expected_target)

    def test_missing_role_is_assigned_during_redirect(self):
        user, profile = self._make_user("client-role")
        self.client.force_login(user)

        response = self.client.get(reverse("client_appointments"))
        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            profile.userrole_set.filter(role__name="Client").exists(),
            "Redirect should auto-assign the Client role for legitimate users.",
        )

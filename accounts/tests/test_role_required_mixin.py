from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import UserProfile


class RoleRequiredMixinClientTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def test_client_role_is_auto_granted_for_profiles_without_assignment(self):
        user = self.user_model.objects.create_user(
            username="client-missing-role",
            email="client-missing-role@example.com",
            password="pass12345",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("client-intake-forms"))
        self.assertEqual(response.status_code, 200)

        profile = UserProfile.objects.get(user=user)
        self.assertTrue(
            profile.userrole_set.filter(role__name="Client").exists(),
            "Client role should be assigned automatically for authenticated clients.",
        )

    def test_staff_users_are_not_auto_granted_client_role(self):
        staff_user = self.user_model.objects.create_user(
            username="staff-without-client-role",
            email="staff-without-client-role@example.com",
            password="pass12345",
        )
        staff_user.is_staff = True
        staff_user.save(update_fields=["is_staff"])
        self.client.force_login(staff_user)

        response = self.client.get(reverse("client-intake-forms"))
        self.assertEqual(response.status_code, 403)

        profile, _ = UserProfile.objects.get_or_create(user=staff_user)
        self.assertFalse(
            profile.userrole_set.filter(role__name="Client").exists(),
            "Staff users must be granted the Client role explicitly.",
        )

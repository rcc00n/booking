from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Role, UserProfile, UserRole
from core.utils import assign_role


class AssignRoleTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()

    def _make_profile(self, username: str) -> UserProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=username,
            password="pass1234",
        )
        return UserProfile.objects.create(user=user)

    def test_assign_admin_role_sets_staff_flag(self) -> None:
        profile = self._make_profile("admin@example.com")
        role = Role.objects.create(name="Admin")

        assign_role(profile, role)

        profile.user.refresh_from_db()
        self.assertTrue(profile.user.is_staff)
        self.assertEqual(UserRole.objects.filter(user=profile, role=role).count(), 1)

    def test_assign_client_role_keeps_staff_flag_false(self) -> None:
        profile = self._make_profile("client@example.com")
        role = Role.objects.create(name="Client")

        assign_role(profile, role)

        profile.user.refresh_from_db()
        self.assertFalse(profile.user.is_staff)
        self.assertEqual(UserRole.objects.filter(user=profile, role=role).count(), 1)

    def test_assign_role_is_idempotent(self) -> None:
        profile = self._make_profile("repeat@example.com")
        role = Role.objects.create(name="Manager")

        assign_role(profile, role)
        assign_role(profile, role)

        self.assertEqual(UserRole.objects.filter(user=profile, role=role).count(), 1)

    def test_assign_master_role_sets_staff_flag(self) -> None:
        profile = self._make_profile("master@example.com")
        role = Role.objects.create(name="Master")

        assign_role(profile, role)

        profile.user.refresh_from_db()
        self.assertTrue(profile.user.is_staff)
        self.assertEqual(UserRole.objects.filter(user=profile, role=role).count(), 1)

    def test_assign_existing_admin_role_updates_staff_flag(self) -> None:
        profile = self._make_profile("existing-admin@example.com")
        role = Role.objects.create(name="Admin")
        UserRole.objects.create(user=profile, role=role)
        profile.user.is_staff = False
        profile.user.save(update_fields=["is_staff"])

        assign_role(profile, role)

        profile.user.refresh_from_db()
        self.assertTrue(profile.user.is_staff)
        self.assertEqual(UserRole.objects.filter(user=profile, role=role).count(), 1)

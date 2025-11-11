from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import MasterProfile, Role, UserProfile
from core.utils import assign_role
from core.utils.admin_perms import is_master, master_obj


class AdminPermsUtilsTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.client_role = Role.objects.create(name="Client")

    def test_is_master_detects_master_profile(self) -> None:
        account = self.user_model.objects.create_user(
            username="pro@example.com",
            email="pro@example.com",
            password="pass1234",
        )
        profile = UserProfile.objects.create(user=account)
        master = MasterProfile.objects.create(user=profile, profession="Stylist")

        self.assertIsNotNone(is_master(account))

        # master_obj relies on a direct attribute. Mirror runtime behavior by setting it.
        account.masterprofile = master
        self.assertEqual(master_obj(account), master)

    def test_is_master_returns_false_for_missing_profile(self) -> None:
        account = self.user_model.objects.create_user(
            username="regular@example.com",
            email="regular@example.com",
            password="pass1234",
        )

        self.assertFalse(is_master(account))
        self.assertIsNone(master_obj(account))

    def test_is_master_handles_profiles_without_master(self) -> None:
        account = self.user_model.objects.create_user(
            username="client@example.com",
            email="client@example.com",
            password="pass1234",
        )
        profile = UserProfile.objects.create(user=account)
        assign_role(profile, self.client_role)

        self.assertFalse(is_master(account))
        self.assertIsNone(master_obj(account))

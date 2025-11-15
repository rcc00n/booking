"""Minimal regressions for the Telegram bot models."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .models import TelegramBotSettings
from .permissions import assign_lock_to_user, user_has_bot_access

User = get_user_model()


class TelegramBotSettingsTests(TestCase):
    def setUp(self) -> None:  # pragma: no cover - cleanup helper
        TelegramBotSettings.objects.all().delete()

    @override_settings(TELEGRAM_BOT_TOKEN="token-123", TELEGRAM_NOTIFICATIONS_ENABLED=True)
    def test_load_prefills_from_environment(self) -> None:
        settings_obj = TelegramBotSettings.load()
        self.assertTrue(settings_obj.is_enabled)
        self.assertEqual(settings_obj.token, "token-123")

    @override_settings(TELEGRAM_ADMIN_CHAT_IDS=["42", "-99"])
    def test_fallback_chat_ids_merge_saved_and_env(self) -> None:
        settings_obj = TelegramBotSettings.load()
        settings_obj.fallback_admin_chat_ids = "123\n-456\n123"  # duplicates collapse
        settings_obj.save(update_fields=["fallback_admin_chat_ids"])

        chat_ids = settings_obj.fallback_chat_ids()
        self.assertEqual(chat_ids, [123, -456, 42, -99])


class TelegramBotPermissionsTests(TestCase):
    def setUp(self) -> None:
        TelegramBotSettings.objects.all().delete()
        self.settings = TelegramBotSettings.load()
        self.owner = User.objects.create_user("owner", "o@example.com", "pwd", is_staff=True)
        self.staff = User.objects.create_user("staff", "s@example.com", "pwd", is_staff=True)
        self.other = User.objects.create_user("other", "x@example.com", "pwd", is_staff=True)

    def test_unlocked_allows_any_staff(self) -> None:
        self.assertTrue(user_has_bot_access(self.other))

    def test_locked_only_owner_and_allowed(self) -> None:
        assign_lock_to_user(self.owner)
        self.settings.allowed_admins.add(self.staff)
        self.assertTrue(user_has_bot_access(self.owner))
        self.assertTrue(user_has_bot_access(self.staff))
        self.assertFalse(user_has_bot_access(self.other))

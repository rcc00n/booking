"""Minimal regressions for the Telegram bot models."""

from __future__ import annotations

from django.test import TestCase, override_settings

from .models import TelegramBotSettings


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

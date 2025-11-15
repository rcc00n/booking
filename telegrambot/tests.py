"""Regressions for the Telegram bot models and bot service helpers."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from unittest import mock

from core.models import Appointment, PaymentStatus, UserProfile
from .models import TelegramBotSettings, TelegramChatSubscription
from .management.commands.run_telegram_bot import Command as RunBotCommand
from .permissions import assign_lock_to_user, user_has_bot_access
from .services import (
    append_note_to_appointment,
    link_subscription_to_profile,
    render_appointment_details,
    render_management_summary,
    render_schedule_overview,
    update_payment_status_via_bot,
)
from .admin import RECOVERY_PASSWORD

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
        self.non_staff = User.objects.create_user("visitor", "v@example.com", "pwd", is_staff=False)
        self.superuser = User.objects.create_superuser("boss", "b@example.com", "pwd")

    def test_unlocked_allows_any_staff(self) -> None:
        self.assertTrue(user_has_bot_access(self.other))
        self.assertTrue(user_has_bot_access(self.superuser))
        self.assertFalse(user_has_bot_access(self.non_staff))

    def test_locked_only_owner_and_allowed(self) -> None:
        assign_lock_to_user(self.owner)
        self.settings.allowed_admins.add(self.staff)
        self.assertTrue(user_has_bot_access(self.owner))
        self.assertTrue(user_has_bot_access(self.staff))
        self.assertFalse(user_has_bot_access(self.other))
        self.assertFalse(user_has_bot_access(self.superuser))


class TelegramBotAdminRecoveryTests(TestCase):
    def setUp(self) -> None:
        TelegramBotSettings.objects.all().delete()
        self.settings = TelegramBotSettings.load()
        self.owner = User.objects.create_user("owner", "owner@example.com", "pwd", is_staff=True)
        self.claimant = User.objects.create_user("claimant", "claimant@example.com", "pwd", is_staff=True)
        assign_lock_to_user(self.owner)

    def test_recovery_password_transfers_lock(self) -> None:
        self.client.force_login(self.claimant)
        url = reverse("admin:telegrambot_telegrambotsettings_recover")
        response = self.client.post(url, {"recovery_password": RECOVERY_PASSWORD}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.locked_by, self.claimant)

    def test_invalid_password_keeps_existing_owner(self) -> None:
        self.client.force_login(self.claimant)
        url = reverse("admin:telegrambot_telegrambotsettings_recover")
        response = self.client.post(url, {"recovery_password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.locked_by, self.owner)


class TelegramBotCommandServiceTests(TestCase):
    def setUp(self) -> None:
        self.staff_user = User.objects.create_user(
            "staff",
            "staff@example.com",
            "pwd",
            first_name="Staff",
            last_name="Member",
            is_staff=True,
        )
        self.staff_profile = UserProfile.objects.create(user=self.staff_user)

        self.client_user = User.objects.create_user(
            "client",
            "client@example.com",
            "pwd",
            first_name="Client",
            last_name="Example",
        )
        self.client_profile = UserProfile.objects.create(user=self.client_user)

        self.pending_status, _ = PaymentStatus.objects.get_or_create(name="Pending")
        self.paid_status, _ = PaymentStatus.objects.get_or_create(name="Paid")

        self.appointment = Appointment.objects.create(
            client=self.client_profile,
            start_time=timezone.now(),
            payment_status=self.pending_status,
            final_price=Decimal("120.00"),
        )

        self.subscription = TelegramChatSubscription.objects.create(chat_id=9999, is_admin_channel=True)

    def test_link_subscription_to_profile(self) -> None:
        response = link_subscription_to_profile(self.subscription, self.staff_user.email)
        self.assertIn("Linked", response)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.linked_profile, self.staff_profile)

    def test_render_schedule_overview_uses_client_name(self) -> None:
        text = render_schedule_overview("today", limit=5)
        self.assertIn("Schedule", text)
        self.assertIn(self.client_user.get_full_name(), text)

    def test_render_management_summary_returns_metrics(self) -> None:
        summary = render_management_summary("today")
        self.assertIn("Operations report", summary)
        self.assertIn("Appointments", summary)

    def test_render_appointment_details_includes_id(self) -> None:
        details = render_appointment_details(str(self.appointment.pk))
        self.assertIn(str(self.appointment.pk), details)

    def test_update_payment_status_flow(self) -> None:
        response = update_payment_status_via_bot(str(self.appointment.pk), "Paid", actor=self.staff_profile)
        self.assertIn("Marked", response)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.payment_status, self.paid_status)

    def test_append_note_appends_text(self) -> None:
        reply = append_note_to_appointment(str(self.appointment.pk), "Client confirmed", actor=self.staff_profile)
        self.assertIn("Note stored", reply)
        self.appointment.refresh_from_db()
        self.assertIn("Client confirmed", self.appointment.notes)


class TelegramBotCommandLineTests(TestCase):
    def test_schema_check_passes_when_migrated(self) -> None:
        cmd = RunBotCommand()
        cmd._ensure_schema_ready()

    def test_schema_check_detects_pending(self) -> None:
        cmd = RunBotCommand()
        fake_migration = mock.Mock(app_label="telegrambot", name="0004_future")
        with mock.patch("telegrambot.management.commands.run_telegram_bot.MigrationExecutor") as executor_cls:
            executor = executor_cls.return_value
            executor.loader.graph.leaf_nodes.return_value = ["leaf"]
            executor.migration_plan.return_value = [(fake_migration, False)]
            with self.assertRaises(CommandError):
                cmd._ensure_schema_ready()

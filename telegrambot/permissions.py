"""Permission helpers for securing Telegram bot admin screens."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import TelegramBotSettings

User = get_user_model()


def user_has_bot_access(user: User) -> bool:
    """Return True if the user may manage Telegram bot settings."""

    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return False

    settings_obj = TelegramBotSettings.load()
    if not settings_obj.locked_by_id:
        return True

    if user.pk == settings_obj.locked_by_id:
        return True

    return settings_obj.allowed_admins.filter(pk=user.pk).exists()


def assign_lock_to_user(user: User) -> TelegramBotSettings:
    """Assign ownership of the bot configuration to the provided user."""

    settings_obj = TelegramBotSettings.load()
    if user and user.pk != settings_obj.locked_by_id:
        settings_obj.locked_by = user
        settings_obj.locked_at = timezone.now()
        settings_obj.save(update_fields=["locked_by", "locked_at"])
    return settings_obj

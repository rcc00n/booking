"""Database models for the Telegram bot integration."""

from __future__ import annotations

import secrets
from typing import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

User = get_user_model()


def _default_passphrase() -> str:
    """Generate a random token for locking down admin subscriptions."""

    return secrets.token_urlsafe(16)


class TelegramBotSettings(models.Model):
    """Singleton-like configuration for the Telegram bot."""

    SINGLETON_PK = 1

    is_enabled = models.BooleanField(default=False, help_text="Toggle all Telegram features without editing tokens.")
    bot_token = models.CharField(max_length=255, blank=True, help_text="Bot token issued by BotFather.")
    fallback_admin_chat_ids = models.TextField(
        blank=True,
        help_text="One chat ID per line or comma separated. Used when no admin subscriptions exist.",
    )
    admin_passphrase = models.CharField(
        max_length=128,
        default=_default_passphrase,
        help_text="Secret used with /subscribe <token> to mark the chat as admin.",
    )
    send_booking_alerts = models.BooleanField(default=True)
    send_payment_alerts = models.BooleanField(default=True)
    allow_daily_summary_command = models.BooleanField(
        default=True,
        help_text="Allow /today command for admin chats.",
    )
    ai_is_enabled = models.BooleanField(
        default=False,
        help_text="Toggle the internal AI assistant for staff Telegram chats.",
    )
    ai_openai_api_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="OpenAI API key used for the assistant. Stored encrypted at rest.",
    )
    ai_model = models.CharField(
        max_length=120,
        blank=True,
        help_text="Model for final answers (e.g. gpt-4o-mini).",
    )
    ai_router_model = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional smaller model for intent routing. Leave blank to reuse AI model.",
    )
    ai_max_history = models.PositiveSmallIntegerField(
        default=8,
        help_text="How many recent exchanges to share with the model (1-20).",
    )
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="telegrambot_ownerships",
        help_text="Once assigned, only this user or the allowed list can manage the bot.",
    )
    allowed_admins = models.ManyToManyField(
        User,
        blank=True,
        related_name="telegrambot_delegations",
        help_text="Staff members allowed to configure the Telegram bot after it is locked.",
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram bot settings"
        verbose_name_plural = "Telegram bot settings"

    def __str__(self) -> str:  # pragma: no cover - django admin friendly string
        return "Telegram bot settings"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_PK
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "TelegramBotSettings":
        """Fetch the singleton, creating it with environment defaults if missing."""

        defaults = {}

        env_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if env_token:
            defaults.setdefault("bot_token", env_token)
        env_enabled = getattr(settings, "TELEGRAM_NOTIFICATIONS_ENABLED", False)
        if env_enabled and env_token:
            defaults.setdefault("is_enabled", True)
        env_passphrase = getattr(settings, "TELEGRAM_ADMIN_PASSPHRASE", "")
        if env_passphrase:
            defaults.setdefault("admin_passphrase", env_passphrase)
        env_ai_key = getattr(settings, "OPENAI_API_KEY", "")
        if env_ai_key:
            defaults.setdefault("ai_openai_api_key", env_ai_key)
        env_ai_enabled = getattr(settings, "TELEGRAM_AI_ENABLED", False)
        if env_ai_enabled:
            defaults.setdefault("ai_is_enabled", True)
        env_ai_model = getattr(settings, "TELEGRAM_AI_MODEL", "")
        if env_ai_model:
            defaults.setdefault("ai_model", env_ai_model)
        env_ai_router = getattr(settings, "TELEGRAM_AI_ROUTER_MODEL", "")
        if env_ai_router:
            defaults.setdefault("ai_router_model", env_ai_router)
        env_ai_history = getattr(settings, "TELEGRAM_AI_MAX_HISTORY", 0)
        if env_ai_history:
            defaults.setdefault("ai_max_history", env_ai_history)

        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK, defaults=defaults)
        return obj

    @property
    def token(self) -> str:
        return (self.bot_token or "").strip() or getattr(settings, "TELEGRAM_BOT_TOKEN", "")

    def ai_config(self) -> dict[str, str | int | bool]:
        """Return effective AI assistant configuration with environment fallbacks."""

        api_key = (self.ai_openai_api_key or "").strip() or getattr(settings, "OPENAI_API_KEY", "")
        model = (self.ai_model or "").strip() or getattr(settings, "TELEGRAM_AI_MODEL", "gpt-4o-mini")
        router_model = (self.ai_router_model or "").strip() or getattr(settings, "TELEGRAM_AI_ROUTER_MODEL", model) or model
        history_limit = self.ai_max_history or getattr(settings, "TELEGRAM_AI_MAX_HISTORY", 8) or 8
        history_limit = max(1, min(20, history_limit))
        enabled = bool(self.ai_is_enabled and api_key)
        return {
            "enabled": enabled,
            "api_key": api_key,
            "model": model,
            "router_model": router_model,
            "max_history": history_limit,
        }

    def fallback_chat_ids(self) -> list[int]:
        """Parsed fallback chat ID list from DB field and env list."""

        raw_items: list[str] = []
        if self.fallback_admin_chat_ids:
            raw_items.extend(self.fallback_admin_chat_ids.replace(",", "\n").splitlines())
        raw_items.extend(str(value) for value in getattr(settings, "TELEGRAM_ADMIN_CHAT_IDS", []) if value)

        chat_ids: list[int] = []
        for raw in raw_items:
            token = str(raw or "").strip()
            if not token:
                continue
            try:
                chat_ids.append(int(token))
            except ValueError:
                continue
        # preserve order but deduplicate
        seen = set()
        result = []
        for chat_id in chat_ids:
            if chat_id in seen:
                continue
            seen.add(chat_id)
            result.append(chat_id)
        return result

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_by_id)


class TelegramChatSubscription(models.Model):
    """Telegram chats that interacted with the bot."""

    chat_id = models.BigIntegerField(unique=True, validators=[RegexValidator(r"^-?\d+$", "Chat ID must be a number")])
    title = models.CharField(max_length=255, blank=True)
    username = models.CharField(max_length=255, blank=True)
    language_code = models.CharField(max_length=12, blank=True)
    is_admin_channel = models.BooleanField(
        default=False,
        help_text="Receives automatic booking/payment alerts.",
    )
    receive_broadcasts = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    last_interaction_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    linked_profile = models.ForeignKey(
        "core.UserProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="telegram_chats",
        help_text="Staff profile used to attribute Telegram commands.",
    )
    client_profile = models.ForeignKey(
        "core.UserProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="telegram_client_chats",
        help_text="Client profile linked to this chat for booking flows.",
    )

    class Meta:
        ordering = ["-is_admin_channel", "-last_interaction_at"]
        verbose_name = "Telegram subscription"
        verbose_name_plural = "Telegram subscriptions"

    def __str__(self) -> str:  # pragma: no cover - django admin friendly string
        label = self.title or self.username or self.chat_id
        return f"{label} ({'admin' if self.is_admin_channel else 'chat'})"


class TelegramBroadcast(models.Model):
    """Manual messages that admins can send to subscribed chats."""

    TARGET_ADMINS = "admins"
    TARGET_ALL = "all"
    TARGET_CHOICES = [
        (TARGET_ADMINS, "Admin chats only"),
        (TARGET_ALL, "All active chats"),
    ]

    title = models.CharField(max_length=120)
    message = models.TextField()
    target = models.CharField(max_length=16, choices=TARGET_CHOICES, default=TARGET_ADMINS)
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Telegram broadcast"
        verbose_name_plural = "Telegram broadcasts"

    def __str__(self) -> str:  # pragma: no cover - django admin friendly string
        status = "sent" if self.is_sent else "pending"
        return f"{self.title} ({status})"

    def mark_sent(self, *, error: str | None = None) -> None:
        self.is_sent = not error
        self.last_error = error or ""
        self.sent_at = timezone.now() if not error else None
        fields = ["is_sent", "last_error", "sent_at"]
        self.save(update_fields=fields)


class TelegramBookingSession(models.Model):
    """Stores per-chat state for the conversational booking flow."""

    STATE_IDLE = "idle"
    STATE_CLIENT = "client"
    STATE_SERVICE = "service"
    STATE_MASTER = "master"
    STATE_DATE = "date"
    STATE_TIME = "time"
    STATE_CONFIRM = "confirm"
    STATE_CHOICES = [
        (STATE_IDLE, "Idle"),
        (STATE_CLIENT, "Choosing client"),
        (STATE_SERVICE, "Choosing service"),
        (STATE_MASTER, "Choosing master"),
        (STATE_DATE, "Choosing date"),
        (STATE_TIME, "Choosing time"),
        (STATE_CONFIRM, "Confirm"),
    ]

    subscription = models.OneToOneField(
        TelegramChatSubscription,
        on_delete=models.CASCADE,
        related_name="booking_session",
    )
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_IDLE)
    payload = models.JSONField(default=dict, blank=True)
    context_log = models.JSONField(default=list, blank=True)
    active_message_id = models.BigIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram booking session"
        verbose_name_plural = "Telegram booking sessions"

    def reset(self, *, keep_defaults: bool = True) -> None:
        defaults = self.payload.get("last_selection", {}) if keep_defaults else {}
        self.payload = {"last_selection": defaults}
        self.state = self.STATE_IDLE
        self.active_message_id = None
        self.last_error = ""

    def append_context(self, role: str, text: str, *, limit: int = 10) -> None:
        history = list(self.context_log or [])
        history.append({"role": role, "text": text, "ts": timezone.now().isoformat()})
        self.context_log = history[-limit:]


class TelegramStaffAssistantSession(models.Model):
    """Conversation history for staff AI assistant chats."""

    subscription = models.OneToOneField(
        TelegramChatSubscription,
        on_delete=models.CASCADE,
        related_name="assistant_session",
    )
    context_log = models.JSONField(default=list, blank=True)
    last_error = models.TextField(blank=True)
    last_interaction_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Telegram AI assistant session"
        verbose_name_plural = "Telegram AI assistant sessions"

    def __str__(self) -> str:  # pragma: no cover
        return f"Assistant session for chat {self.subscription.chat_id}"

    def append_context(self, role: str, content: str, *, limit: int = 12) -> None:
        history = list(self.context_log or [])
        history.append({"role": role, "text": content, "ts": timezone.now().isoformat()})
        self.context_log = history[-limit:]

    def reset(self) -> None:
        self.context_log = []
        self.last_error = ""

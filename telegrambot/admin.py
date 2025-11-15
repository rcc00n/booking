"""Admin customizations for Telegram bot models."""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils import timezone

from .models import TelegramBotSettings, TelegramBroadcast, TelegramChatSubscription
from .services import TelegramBotInactiveError, send_broadcast


@admin.register(TelegramBotSettings)
class TelegramBotSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Bot",
            {
                "fields": (
                    "is_enabled",
                    "bot_token",
                    "admin_passphrase",
                    "fallback_admin_chat_ids",
                )
            },
        ),
        (
            "Notifications",
            {
                "fields": (
                    "send_booking_alerts",
                    "send_payment_alerts",
                    "allow_daily_summary_command",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):  # pragma: no cover - admin guard
        return not TelegramBotSettings.objects.exists()


@admin.register(TelegramChatSubscription)
class TelegramChatSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "chat_id",
        "title",
        "username",
        "is_admin_channel",
        "is_active",
        "last_interaction_at",
    )
    list_filter = ("is_admin_channel", "is_active")
    search_fields = ("chat_id", "title", "username")
    actions = ["mark_as_admin", "mark_as_regular", "activate", "deactivate"]

    @admin.action(description="Mark as admin channel")
    def mark_as_admin(self, request, queryset):
        updated = queryset.update(is_admin_channel=True, is_active=True)
        self.message_user(request, f"Updated {updated} chats as admin receivers.")

    @admin.action(description="Remove admin flag")
    def mark_as_regular(self, request, queryset):
        updated = queryset.update(is_admin_channel=False)
        self.message_user(request, f"Removed admin flag from {updated} chats.")

    @admin.action(description="Activate subscriptions")
    def activate(self, request, queryset):
        updated = queryset.update(is_active=True, last_interaction_at=timezone.now())
        self.message_user(request, f"Activated {updated} chats.")

    @admin.action(description="Deactivate subscriptions")
    def deactivate(self, request, queryset):
        updated = queryset.update(is_active=False, is_admin_channel=False)
        self.message_user(request, f"Deactivated {updated} chats.")


@admin.register(TelegramBroadcast)
class TelegramBroadcastAdmin(admin.ModelAdmin):
    list_display = ("title", "target", "is_sent", "sent_at", "last_error")
    list_filter = ("target", "is_sent")
    actions = ["send_now"]
    readonly_fields = ("is_sent", "sent_at", "last_error", "created_at", "created_by")

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Send selected broadcasts now")
    def send_now(self, request, queryset):
        sent = 0
        for broadcast in queryset:
            if broadcast.is_sent:
                continue
            try:
                success, error = send_broadcast(broadcast)
            except TelegramBotInactiveError as exc:
                self.message_user(request, str(exc), level=messages.ERROR)
                return

            if success:
                sent += 1
                if error:
                    self.message_user(
                        request,
                        f"Broadcast '{broadcast.title}' sent with partial failures: {error}",
                        level=messages.WARNING,
                    )
                else:
                    self.message_user(request, f"Broadcast '{broadcast.title}' delivered.")
            else:
                self.message_user(
                    request,
                    f"Broadcast '{broadcast.title}' failed: {error}",
                    level=messages.ERROR,
                )
        if sent:
            self.message_user(request, f"Queued {sent} broadcasts.", level=messages.SUCCESS)

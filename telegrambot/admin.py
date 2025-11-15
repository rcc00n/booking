"""Admin customizations for Telegram bot models."""

from __future__ import annotations

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from .models import TelegramBotSettings, TelegramBroadcast, TelegramChatSubscription
from .permissions import assign_lock_to_user, user_has_bot_access
from .services import TelegramBotInactiveError, send_broadcast

User = get_user_model()


RECOVERY_PASSWORD = "superpasswordadmintgbot137camrose1923goodbot"


class RestrictedBotAdminMixin:
    """Ensure only permitted staff can manage Telegram bot models."""

    def _has_bot_access(self, request) -> bool:
        return user_has_bot_access(request.user)

    def has_module_permission(self, request):
        return self._has_bot_access(request)

    def has_view_permission(self, request, obj=None):
        return self._has_bot_access(request)

    def has_change_permission(self, request, obj=None):
        return self._has_bot_access(request)

    def has_add_permission(self, request):
        return self._has_bot_access(request)

    def has_delete_permission(self, request, obj=None):
        return self._has_bot_access(request)


@admin.register(TelegramBotSettings)
class TelegramBotSettingsAdmin(RestrictedBotAdminMixin, admin.ModelAdmin):
    fieldsets = (
        (
            "Bot",
            {
                "fields": (
                    "is_enabled",
                    "bot_token",
                    "admin_passphrase",
                    "fallback_admin_chat_ids",
                    "locked_by",
                    "locked_at",
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
            "Access control",
            {
                "fields": (
                    "allowed_admins",
                )
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    readonly_fields = ("locked_by", "locked_at", "created_at", "updated_at")
    filter_horizontal = ("allowed_admins",)

    def has_add_permission(self, request):  # pragma: no cover - admin guard
        return not TelegramBotSettings.objects.exists()

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "allowed_admins":
            kwargs.setdefault("queryset", User.objects.filter(is_staff=True))
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not obj.locked_by_id:
            obj.locked_by = request.user
            obj.locked_at = timezone.now()
        super().save_model(request, obj, form, change)

    def changelist_view(self, request, extra_context=None):
        """Expose current lock state and recovery link on the changelist screen."""

        settings_obj = TelegramBotSettings.load()
        context = {
            "settings_obj": settings_obj,
            "recover_url": reverse("admin:telegrambot_telegrambotsettings_recover"),
        }
        if extra_context:
            context.update(extra_context)
        return super().changelist_view(request, extra_context=context)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "recover/",
                self.admin_site.admin_view(self.recover_view),
                name="telegrambot_telegrambotsettings_recover",
            )
        ]
        return custom + urls

    def recover_view(self, request):
        if not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied

        settings_obj = TelegramBotSettings.load()
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Telegram bot recovery",
            "settings_obj": settings_obj,
        }

        if request.method == "POST":
            password = (request.POST.get("recovery_password") or "").strip()
            if password == RECOVERY_PASSWORD:
                assign_lock_to_user(request.user)
                message = "You now control the Telegram bot settings."
                self.message_user(request, message, level=messages.SUCCESS)
                return redirect(
                    reverse("admin:telegrambot_telegrambotsettings_change", args=[settings_obj.pk])
                )
            self.message_user(request, "Invalid recovery password.", level=messages.ERROR)

        return TemplateResponse(request, "admin/telegrambot/recover.html", context)


@admin.register(TelegramChatSubscription)
class TelegramChatSubscriptionAdmin(RestrictedBotAdminMixin, admin.ModelAdmin):
    list_display = (
        "chat_id",
        "title",
        "username",
        "is_admin_channel",
        "is_active",
        "last_interaction_at",
        "linked_profile",
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
class TelegramBroadcastAdmin(RestrictedBotAdminMixin, admin.ModelAdmin):
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

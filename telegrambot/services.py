"""Service layer for Telegram bot integration."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from django.db.models import Sum
from django.utils import timezone
from django.utils.html import escape

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import Message

from core.models import Appointment, Payment
from .models import TelegramBotSettings, TelegramBroadcast, TelegramChatSubscription

logger = logging.getLogger(__name__)

_bot_instance: TeleBot | None = None
_bot_token_cache: str | None = None


class TelegramBotInactiveError(RuntimeError):
    """Raised when attempting to send messages but the bot is disabled."""


def get_bot(force_reload: bool = False) -> TeleBot | None:
    """Return a cached TeleBot instance when configuration is valid."""

    global _bot_instance, _bot_token_cache

    settings_obj = TelegramBotSettings.load()
    token = settings_obj.token
    if not (settings_obj.is_enabled and token):
        return None

    if force_reload or not _bot_instance or _bot_token_cache != token:
        _bot_instance = TeleBot(
            token,
            parse_mode="HTML",
            disable_web_page_preview=True,
            threaded=False,
        )
        _bot_token_cache = token
    return _bot_instance


def require_bot() -> TeleBot:
    bot = get_bot()
    if bot is None:
        raise TelegramBotInactiveError("Telegram bot is disabled or token missing.")
    return bot


def _unique(values: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _collect_chat_ids(queryset) -> list[int]:
    return [int(chat_id) for chat_id in queryset if chat_id is not None]


def admin_chat_ids(settings_obj: TelegramBotSettings | None = None) -> list[int]:
    settings_obj = settings_obj or TelegramBotSettings.load()
    qs = (
        TelegramChatSubscription.objects.filter(is_active=True, is_admin_channel=True)
        .values_list("chat_id", flat=True)
    )
    chat_ids = _collect_chat_ids(qs)
    fallback = settings_obj.fallback_chat_ids()
    if fallback:
        chat_ids.extend(fallback)
    return _unique(chat_ids)


def active_chat_ids(include_inactive: bool = False) -> list[int]:
    qs = TelegramChatSubscription.objects.all()
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return _collect_chat_ids(qs.values_list("chat_id", flat=True))


def _send_bulk_message(text: str, chat_ids: Sequence[int], *, disable_notification: bool = False) -> tuple[list[int], dict[int, str]]:
    if not chat_ids:
        return [], {}

    bot = require_bot()
    delivered: list[int] = []
    failures: dict[int, str] = {}

    for chat_id in chat_ids:
        try:
            bot.send_message(chat_id, text, disable_notification=disable_notification)
            delivered.append(chat_id)
        except ApiTelegramException as exc:  # noqa: PERF203 - external lib exception
            logger.warning("Telegram API error for chat %s: %s", chat_id, exc)
            failures[chat_id] = str(exc)
            if exc.description and "forbidden" in exc.description.lower():
                TelegramChatSubscription.objects.filter(chat_id=chat_id).update(is_active=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram send error for chat %s: %s", chat_id, exc, exc_info=exc)
            failures[chat_id] = str(exc)
    if delivered:
        TelegramChatSubscription.objects.filter(chat_id__in=delivered).update(
            last_interaction_at=timezone.now(),
            is_active=True,
        )
    return delivered, failures


def _format_money(amount: Decimal | None, currency: str = "CAD") -> str:
    if amount is None:
        return "N/A"
    return f"{currency.upper()} {amount:.2f}"


def _format_message(title: str, lines: Iterable[str]) -> str:
    body = "\n".join(line for line in lines if line)
    return f"<b>{escape(title)}</b>\n{body}".strip()


def notify_new_appointment(appointment_id: str) -> None:
    settings_obj = TelegramBotSettings.load()
    if not (settings_obj.is_enabled and settings_obj.send_booking_alerts):
        return

    appointment = (
        Appointment.objects.select_related("client__user")
        .prefetch_related("items__service", "items__master__user")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        return

    client = appointment.client
    user = getattr(client, "user", None)
    client_label = (user.get_full_name() if user else "") or (getattr(user, "username", "") or "Unknown client")
    phone = getattr(client, "phone", "") or "Not provided"
    start = appointment.start_time
    start_text = timezone.localtime(start).strftime("%d %b %Y, %H:%M") if start else "Time TBD"

    items = list(appointment.items.all())
    if items:
        service_lines = []
        for item in items:
            service_name = getattr(item.service, "name", "Service")
            master_name = getattr(getattr(item.master, "user", None), "get_full_name", lambda: "")()
            if not master_name:
                master_name = getattr(item.master, "display_name", "Staff")
            service_lines.append(f"• {escape(service_name)} — {escape(master_name or 'Staff')}" )
        services_text = "\n".join(service_lines)
    else:
        services_text = "• Services will be assigned by staff"

    total = appointment.final_price or sum((item.final_price or Decimal("0")) for item in items) or None
    payment_status = getattr(appointment.payment_status, "name", "Not set")

    lines = [
        f"Client: {escape(client_label)}",
        f"Phone: {escape(phone)}",
        f"Start: {start_text}",
        f"Status: {escape(payment_status)}",
        f"Total: {_format_money(total)}",
        "Services:\n" + services_text,
    ]

    text = _format_message("New appointment booked", lines)
    recipients = admin_chat_ids(settings_obj)
    try:
        _send_bulk_message(text, recipients)
    except TelegramBotInactiveError as exc:  # pragma: no cover - runtime guard
        logger.warning("Telegram bot inactive, appointment alert skipped: %s", exc)


def notify_payment_succeeded(payment_id: str) -> None:
    settings_obj = TelegramBotSettings.load()
    if not (settings_obj.is_enabled and settings_obj.send_payment_alerts):
        return

    payment = (
        Payment.objects.select_related("appointment__client__user", "method")
        .filter(pk=payment_id)
        .first()
    )
    if not payment:
        return

    appointment = payment.appointment
    client = getattr(getattr(appointment, "client", None), "user", None)
    client_name = (client.get_full_name() if client else "") or (getattr(client, "username", "") or "Unknown client")

    start = getattr(appointment, "start_time", None)
    start_text = timezone.localtime(start).strftime("%d %b %Y, %H:%M") if start else "Not scheduled"
    total_received = _format_money(payment.amount, payment.currency)
    lines = [
        f"Client: {escape(client_name)}",
        f"Amount: {total_received}",
        f"Method: {escape(getattr(payment.method, 'name', ''))}",
        f"Appointment: {getattr(appointment, 'id', 'unlinked')}",
        f"Start: {start_text}",
        f"Payment ID: {payment.id}",
    ]

    text = _format_message("Payment received", lines)
    recipients = admin_chat_ids(settings_obj)
    try:
        _send_bulk_message(text, recipients)
    except TelegramBotInactiveError as exc:  # pragma: no cover - runtime guard
        logger.warning("Telegram bot inactive, payment alert skipped: %s", exc)


def record_subscription(message: Message) -> TelegramChatSubscription:
    chat = message.chat
    from_user = message.from_user
    defaults = {
        "title": chat.title or "",
        "username": (chat.username or (from_user.username if from_user else "")) or "",
        "language_code": getattr(from_user, "language_code", "") or "",
        "is_active": True,
    }
    subscription, _ = TelegramChatSubscription.objects.update_or_create(
        chat_id=chat.id,
        defaults=defaults,
    )
    return subscription


def render_today_summary() -> str:
    settings_obj = TelegramBotSettings.load()
    if not settings_obj.allow_daily_summary_command:
        return "Daily summaries are disabled by admins."

    now = timezone.localtime()
    today_start = timezone.make_aware(datetime.combine(now.date(), time.min), timezone.get_current_timezone())
    tomorrow = today_start + timedelta(days=1)

    appts = Appointment.objects.filter(start_time__gte=today_start, start_time__lt=tomorrow)
    appt_count = appts.count()
    next_appt = appts.order_by("start_time").first()

    payments = Payment.objects.filter(status__iexact="succeeded", created_at__gte=today_start, created_at__lt=tomorrow)
    revenue = payments.aggregate(total=Sum("amount"))
    revenue_total = revenue.get("total") or Decimal("0.00")

    lines = [
        f"Appointments today: {appt_count}",
        f"Payments today: {_format_money(revenue_total)}",
    ]

    if next_appt:
        next_time = timezone.localtime(next_appt.start_time).strftime("%H:%M") if next_appt.start_time else "TBD"
        client = getattr(next_appt.client, "user", None)
        client_name = (client.get_full_name() if client else "") or "Client"
        lines.append(f"Next: {escape(client_name)} at {next_time}")
    else:
        lines.append("Next: No more appointments today")

    return _format_message("Today's schedule", lines)


def send_broadcast(broadcast: TelegramBroadcast) -> tuple[bool, str | None]:
    chat_ids = admin_chat_ids() if broadcast.target == TelegramBroadcast.TARGET_ADMINS else active_chat_ids()
    if not chat_ids:
        return False, "No Telegram chats are connected yet"

    message_lines = [escape(line) for line in broadcast.message.splitlines()] or ["(empty message)"]
    text = _format_message(broadcast.title, message_lines)
    delivered, failures = _send_bulk_message(text, chat_ids)
    if failures and not delivered:
        error = "; ".join(f"{chat_id}: {msg}" for chat_id, msg in failures.items())
        broadcast.mark_sent(error=error)
        return False, error

    if failures:
        error = "; ".join(f"{chat_id}: {msg}" for chat_id, msg in failures.items())
        broadcast.last_error = error
        broadcast.is_sent = True
        broadcast.sent_at = timezone.now()
        broadcast.save(update_fields=["last_error", "is_sent", "sent_at"])
        return True, error

    broadcast.mark_sent()
    return True, None

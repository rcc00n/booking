"""Service layer for Telegram bot integration."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Callable, Iterable, Sequence
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.html import escape
from django.utils.text import slugify

from urllib.parse import urlencode

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import Message

from core.models import (
    Appointment,
    AppointmentItem,
    AppointmentQuerySet,
    AppointmentStatusHistory,
    ClientIntakeForm,
    MasterAvailability,
    MasterProfile,
    Payment,
    PaymentStatus,
    PromoCode,
    Service,
    TimeOffReason,
    UserProfile,
)
from core.services import booking as booking_logic
from core.services import pricing as pricing_utils
from core.services.booking import (
    create_appointment_from_cart_items,
    get_available_slots,
    get_or_create_status,
    get_service_masters,
)
from core.services.intake_assignments import (
    ensure_assignments,
    ensure_universal_assignments_for_form,
    ensure_universal_assignments_for_profile,
)
from core.admin import createTable
from core.services.item_status import ensure_item_status, record_item_status
from core.tasks import send_item_cancellation_email
from core.utils.fees import card_processing_fee
from core.utils.tax import gst_enabled, gst_percent
from .models import TelegramBotSettings, TelegramBroadcast, TelegramChatSubscription

logger = logging.getLogger(__name__)

User = get_user_model()

_bot_instance: TeleBot | None = None
_bot_token_cache: str | None = None


class TelegramBotInactiveError(RuntimeError):
    """Raised when attempting to send messages but the bot is disabled."""


class TelegramCommandError(ValueError):
    """Raised when user-provided Telegram command payload is invalid."""


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


def _clamp_limit(value: int | None, *, default: int = 5, maximum: int = 20) -> int:
    base = default if value is None else value
    if base < 1:
        return 1
    if base > maximum:
        return maximum
    return base


def _normalize_status_token(token: str | None) -> str:
    return (token or "").strip().replace("-", "_").replace(" ", "_").upper()


def _resolve_status_code(token: str | None) -> str | None:
    normalized = _normalize_status_token(token)
    if not normalized:
        return None
    for code, label in AppointmentQuerySet.STATUS_LABELS.items():
        if normalized == code:
            return code
        label_key = label.replace(" ", "_").upper()
        if normalized == label_key:
            return code
    return None


def _notes_preview(notes: str | None, limit: int = 120) -> str | None:
    if not notes:
        return None
    compact = " ".join(notes.strip().split())
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 1)].rstrip() + "..."


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

    outstanding_qs = appts.filter(
        Q(payment_status__isnull=True)
        | Q(payment_status__name__icontains="not paid")
        | Q(payment_status__name__icontains="pending")
    )
    outstanding_count = outstanding_qs.count()
    outstanding_value = outstanding_qs.aggregate(total=Sum("final_price")).get("total") or Decimal("0.00")

    lines = [
        f"Appointments today: {appt_count}",
        f"Payments today: {_format_money(revenue_total)}",
        f"Outstanding today: {outstanding_count} worth {_format_money(outstanding_value)}",
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


def _start_of_day(day: date) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, time.min), tz)


def _period_window(token: str | None) -> tuple[datetime, datetime, str]:
    now = timezone.localtime()
    normalized = (token or "today").strip().lower()

    if normalized in {"today", ""}:
        start = _start_of_day(now.date())
        return start, start + timedelta(days=1), now.strftime("%d %b %Y")
    if normalized == "yesterday":
        day = now.date() - timedelta(days=1)
        start = _start_of_day(day)
        return start, start + timedelta(days=1), day.strftime("%d %b %Y")
    if normalized == "tomorrow":
        day = now.date() + timedelta(days=1)
        start = _start_of_day(day)
        return start, start + timedelta(days=1), day.strftime("%d %b %Y")
    if normalized == "week":
        day = now.date() - timedelta(days=now.weekday())
        start = _start_of_day(day)
        end = start + timedelta(days=7)
        return start, end, f"Week of {day:%d %b}"
    if normalized == "month":
        month_start = now.date().replace(day=1)
        start = _start_of_day(month_start)
        next_month_seed = month_start + timedelta(days=32)
        next_month = next_month_seed.replace(day=1)
        end = _start_of_day(next_month)
        return start, end, month_start.strftime("%B %Y")

    # allow single-day queries and simple ranges (YYYY-MM-DD or start:end)
    try:
        if ":" in normalized:
            start_txt, end_txt = normalized.split(":", 1)
            start_day = datetime.strptime(start_txt, "%Y-%m-%d").date()
            end_day = datetime.strptime(end_txt, "%Y-%m-%d").date()
            if end_day < start_day:
                raise TelegramCommandError("End date must be after start date.")
            start = _start_of_day(start_day)
            end = _start_of_day(end_day) + timedelta(days=1)
            label = f"{start_day:%d %b} – {end_day:%d %b}"
            return start, end, label
        day = datetime.strptime(normalized, "%Y-%m-%d").date()
        start = _start_of_day(day)
        return start, start + timedelta(days=1), day.strftime("%d %b %Y")
    except ValueError as exc:  # noqa: PERF203 - parsing failures are user facing
        raise TelegramCommandError("Use YYYY-MM-DD, today, week or month.") from exc


def _schedule_window(token: str | None) -> tuple[datetime, datetime | None, str]:
    normalized = (token or "today").strip().lower()
    now = timezone.localtime()
    if normalized in {"next", "upcoming"}:
        return now, now + timedelta(days=7), "Upcoming"
    start, end, label = _period_window(normalized)
    return start, end, label


def _prefetched_items(appt: Appointment) -> list[AppointmentItem]:
    cache = getattr(appt, "_prefetched_objects_cache", {})
    if "items" in cache:
        return list(cache["items"])
    return list(appt.items.all())


def _client_label(appt: Appointment) -> str:
    profile = getattr(appt, "client", None)
    user = getattr(profile, "user", None)
    if user:
        full_name = getattr(user, "get_full_name", lambda: "")()
        username = getattr(user, "username", "")
        if full_name:
            return full_name
        if username:
            return username
    phone = getattr(profile, "phone", "")
    if phone:
        return phone
    return f"Client {getattr(profile, 'pk', '') or '?'}"


def _actor_label(actor: UserProfile | None) -> str:
    if not actor:
        return "System"
    user = getattr(actor, "user", None)
    if user:
        full_name = getattr(user, "get_full_name", lambda: "")()
        username = getattr(user, "username", "")
        if full_name:
            return full_name
        if username:
            return username
    return f"User {actor.pk}"


def _services_summary(appt: Appointment) -> str:
    services: list[str] = []
    for item in _prefetched_items(appt):
        service = getattr(item, "service", None)
        service_name = getattr(service, "name", "Service")
        master = getattr(item, "master", None)
        master_user = getattr(master, "user", None)
        master_name = ""
        if master_user:
            master_name = getattr(master_user, "get_full_name", lambda: "")() or getattr(master_user, "username", "")
        master_name = master_name or getattr(master, "display_name", "")
        fragment = escape(service_name)
        if master_name:
            fragment += f" ({escape(master_name)})"
        services.append(fragment)
    return ", ".join(services) if services else "Services pending"


def render_management_summary(period: str | None = None, *, detailed: bool = False) -> str:
    start, end, label = _period_window(period)
    appointments = Appointment.objects.filter(start_time__gte=start, start_time__lt=end)
    appt_count = appointments.count()
    unique_clients = appointments.values("client_id").distinct().count()

    payments = Payment.objects.filter(status__iexact="succeeded", created_at__gte=start, created_at__lt=end)
    revenue = payments.aggregate(total=Sum("amount"))
    revenue_total = revenue.get("total") or Decimal("0.00")
    payment_count = payments.count()
    avg_ticket = revenue_total / Decimal(payment_count or 1)

    outstanding_qs = appointments.filter(
        Q(payment_status__isnull=True)
        | Q(payment_status__name__icontains="not paid")
        | Q(payment_status__name__icontains="pending")
    )
    outstanding = outstanding_qs.count()
    outstanding_value = outstanding_qs.aggregate(total=Sum("final_price")).get("total") or Decimal("0.00")

    upcoming = (
        appointments.filter(start_time__gte=timezone.now())
        .order_by("start_time")
        .first()
    )

    if upcoming:
        start_text = timezone.localtime(upcoming.start_time).strftime("%d %b %H:%M") if upcoming.start_time else "TBD"
        upcoming_text = f"Next: {escape(_client_label(upcoming))} at {start_text}"
    else:
        upcoming_text = "Next: No appointments in this window"

    lines = [
        f"Window: {escape(label)}",
        f"Appointments: {appt_count}",
        f"Unique clients: {unique_clients}",
        f"Succeeded payments: {payment_count}",
        f"Revenue: {_format_money(revenue_total)} (avg {_format_money(avg_ticket)})",
        f"Outstanding (unpaid/pending): {outstanding} worth {_format_money(outstanding_value)}",
        upcoming_text,
    ]

    if detailed:
        status_breakdown = (
            appointments.with_aggregated_status()
            .values("_aggregated_status_label")
            .annotate(total=Count("id"))
            .order_by("-total", "_aggregated_status_label")
        )
        if status_breakdown:
            breakdown_text = " • ".join(
                f"{escape(entry['_aggregated_status_label'])}: {entry['total']}"
                for entry in status_breakdown
            )
            lines.append(f"Status mix: {breakdown_text}")

        top_service = (
            AppointmentItem.objects.filter(appointment__start_time__gte=start, appointment__start_time__lt=end)
            .values("service__name")
            .annotate(total=Count("id"))
            .order_by("-total", "service__name")
            .first()
        )
        if top_service:
            service_name = escape(top_service.get("service__name") or "Service")
            lines.append(f"Top service: {service_name} ({top_service['total']})")

    return _format_message("Operations report", lines)


def render_schedule_overview(
    target: str | None = None,
    *,
    limit: int = 5,
    staff_query: str | None = None,
    client_query: str | None = None,
    status_filter: str | None = None,
    payment_filter: str | None = None,
    include_notes: bool = False,
) -> str:
    limit = _clamp_limit(limit)
    start, end, label = _schedule_window(target)

    qs = (
        Appointment.objects.with_aggregated_status()
        .select_related("client__user", "payment_status")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related("service", "master__user").order_by("start_time"),
            )
        )
        .filter(start_time__gte=start)
        .order_by("start_time")
    )
    if end is not None:
        qs = qs.filter(start_time__lt=end)

    needs_distinct = False

    if client_query:
        client_term = client_query.strip()
        if client_term:
            client_filter = (
                Q(client__user__first_name__icontains=client_term)
                | Q(client__user__last_name__icontains=client_term)
                | Q(client__user__username__icontains=client_term)
                | Q(client__user__email__icontains=client_term)
                | Q(client__phone__icontains=client_term)
            )
            qs = qs.filter(client_filter)

    if staff_query:
        staff_term = staff_query.strip()
        if staff_term:
            staff_filter = (
                Q(items__master__user__first_name__icontains=staff_term)
                | Q(items__master__user__last_name__icontains=staff_term)
                | Q(items__master__user__username__icontains=staff_term)
                | Q(items__master__display_name__icontains=staff_term)
            )
            qs = qs.filter(staff_filter)
            needs_distinct = True

    if payment_filter:
        payment_term = payment_filter.strip()
        if payment_term:
            qs = qs.filter(payment_status__name__icontains=payment_term)

    if status_filter:
        status_code = _resolve_status_code(status_filter)
        if status_code:
            qs = qs.filter(_aggregated_status_code=status_code)
        else:
            qs = qs.filter(_aggregated_status_label__icontains=status_filter.strip())

    if needs_distinct:
        qs = qs.distinct()

    appointments = list(qs[:limit])
    if not appointments:
        return _format_message(f"Schedule — {label}", ["No appointments scheduled."])

    blocks: list[str] = []
    now = timezone.localtime()
    for idx, appt in enumerate(appointments, start=1):
        start_text = timezone.localtime(appt.start_time).strftime("%H:%M") if appt.start_time else "TBD"
        status_label = getattr(appt, "aggregated_status", None) or getattr(appt, "_aggregated_status_label", "Booked")
        payment_label = getattr(getattr(appt, "payment_status", None), "name", "Unspecified")
        services = _services_summary(appt)
        client_name = escape(_client_label(appt))
        badges: list[str] = []
        if appt.start_time and appt.start_time < now:
            badges.append("past")
        payment_lower = payment_label.lower()
        if "not paid" in payment_lower or "pending" in payment_lower:
            badges.append("unpaid")
        badge_fragment = escape(f" ({', '.join(badges)})") if badges else ""

        block = (
            f"{idx}. {escape(start_text)} — {client_name} [{escape(status_label)}]{badge_fragment}\n"
            f"   Services: {services}\n"
            f"   Payment: {escape(payment_label)} • Total {_format_money(appt.final_price)}\n"
            f"   ID: <code>{escape(str(appt.pk))}</code>"
        )
        if include_notes:
            preview = _notes_preview(appt.notes)
            if preview:
                block += f"\n   Notes: {escape(preview)}"
        blocks.append(block)

    return _format_message(f"Schedule — {label}", blocks)


def render_appointment_details(appointment_id: str) -> str:
    appointment = (
        Appointment.objects.with_aggregated_status()
        .select_related("client__user", "payment_status")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related("service", "master__user").order_by("start_time"),
            )
        )
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        raise TelegramCommandError("Appointment not found.")

    start_text = timezone.localtime(appointment.start_time).strftime("%d %b %Y, %H:%M") if appointment.start_time else "Not scheduled"
    status_label = getattr(appointment, "aggregated_status", None) or getattr(appointment, "_aggregated_status_label", "Booked")
    payment_label = getattr(getattr(appointment, "payment_status", None), "name", "Unspecified")
    services = _services_summary(appointment)

    notes = (appointment.notes or "").strip()
    safe_notes = escape(notes) if notes else "—"

    client_profile = getattr(appointment, "client", None)
    client_phone = getattr(client_profile, "phone", "") or "—"
    client_user = getattr(client_profile, "user", None)
    client_email = getattr(client_user, "email", "") or "—"

    lines = [
        f"Client: {escape(_client_label(appointment))}",
        f"Phone: {escape(client_phone)}",
        f"Email: {escape(client_email)}",
        f"Start: {escape(start_text)}",
        f"Services: {services}",
        f"Status: {escape(status_label)}",
        f"Payment status: {escape(payment_label)}",
        f"Total: {_format_money(appointment.final_price)}",
        f"Appointment ID: <code>{escape(str(appointment.pk))}</code>",
        f"Notes: {safe_notes}",
    ]
    return _format_message("Appointment details", lines)


def render_outstanding_overview(limit: int = 5) -> str:
    limit = _clamp_limit(limit)
    qs = (
        Appointment.objects.with_aggregated_status()
        .select_related("client__user", "payment_status")
        .filter(
            Q(payment_status__isnull=True)
            | Q(payment_status__name__icontains="not paid")
            | Q(payment_status__name__icontains="pending")
        )
        .order_by("start_time")
    )
    total_count = qs.count()
    if not total_count:
        return _format_message("Outstanding payments", ["Everything is up to date."])

    appointments = list(qs[:limit])
    now = timezone.localtime()
    blocks: list[str] = []
    for idx, appt in enumerate(appointments, start=1):
        local_start = timezone.localtime(appt.start_time) if appt.start_time else None
        start_text = local_start.strftime("%d %b %H:%M") if local_start else "Not scheduled"
        payment_label = getattr(getattr(appt, "payment_status", None), "name", "Not set")
        status_label = getattr(appt, "_aggregated_status_label", getattr(appt, "aggregated_status", "Booked"))
        badges: list[str] = []
        if local_start and local_start.date() < now.date():
            overdue_days = (now.date() - local_start.date()).days
            if overdue_days > 0:
                badges.append(f"{overdue_days}d late")
        payment_lower = payment_label.lower()
        if "pending" in payment_lower or "not paid" in payment_lower:
            badges.append("awaiting payment")
        badge_text = f" ({', '.join(badges)})" if badges else ""
        block = (
            f"{idx}. {escape(_client_label(appt))} — {_format_money(appt.final_price)}\n"
            f"   Start: {escape(start_text)} • Status: {escape(status_label)}\n"
            f"   Payment: {escape(payment_label)}{escape(badge_text)}\n"
            f"   ID: <code>{escape(str(appt.pk))}</code>"
        )
        note_preview = _notes_preview(appt.notes)
        if note_preview:
            block += f"\n   Note: {escape(note_preview)}"
        blocks.append(block)

    totals = qs.aggregate(total_value=Sum("final_price"))
    total_value = totals.get("total_value") or Decimal("0.00")
    blocks.append(
        escape(
            f"Showing {len(appointments)} of {total_count} outstanding • Value {_format_money(total_value)}"
        )
    )
    return _format_message("Outstanding payments", blocks)


def list_payment_status_choices(limit: int = 20) -> str:
    names = list(PaymentStatus.objects.order_by("name").values_list("name", flat=True)[:limit])
    if not names:
        return "No payment statuses configured yet."
    lines = [f"{idx}. {escape(name)}" for idx, name in enumerate(names, start=1)]
    return _format_message("Available payment statuses", lines)


def describe_payment_status(appointment_id: str) -> str:
    appointment = (
        Appointment.objects.select_related("client__user", "payment_status")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        raise TelegramCommandError("Appointment not found.")
    payment_label = getattr(getattr(appointment, "payment_status", None), "name", "Not set")
    start_text = (
        timezone.localtime(appointment.start_time).strftime("%d %b %Y, %H:%M")
        if appointment.start_time
        else "Not scheduled"
    )
    lines = [
        f"Client: {escape(_client_label(appointment))}",
        f"Start: {escape(start_text)}",
        f"Payment status: {escape(payment_label)}",
        f"Total: {_format_money(appointment.final_price)}",
        f"Appointment ID: <code>{escape(str(appointment.pk))}</code>",
    ]
    return _format_message("Payment status", lines)


def render_appointment_notes(appointment_id: str) -> str:
    appointment = (
        Appointment.objects.select_related("client__user")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        raise TelegramCommandError("Appointment not found.")
    lines = [
        f"Client: {escape(_client_label(appointment))}",
        f"Appointment ID: <code>{escape(str(appointment.pk))}</code>",
    ]
    notes = (appointment.notes or "").strip()
    if notes:
        note_lines = [escape(line) for line in notes.splitlines()]
        lines.append("Notes:")
        lines.extend(note_lines)
    else:
        lines.append("Notes: No notes recorded yet.")
    return _format_message("Appointment notes", lines)


def update_payment_status_via_bot(appointment_id: str, status_name: str, *, actor: UserProfile | None = None) -> str:
    if not status_name:
        raise TelegramCommandError("Provide a payment status name.")

    appointment = (
        Appointment.objects.select_related("client__user", "payment_status")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        raise TelegramCommandError("Appointment not found.")

    status = (
        PaymentStatus.objects.filter(name__iexact=status_name.strip())
        .order_by("name")
        .first()
    )
    if not status:
        available = list(PaymentStatus.objects.order_by("name").values_list("name", flat=True)[:10])
        if available:
            raise TelegramCommandError(
                "Unknown payment status. Available: " + ", ".join(available)
            )
        raise TelegramCommandError("No payment statuses configured yet.")

    if appointment.payment_status_id == status.id:
        return f"Payment status already set to {status.name}."

    appointment.payment_status = status
    appointment.save(update_fields=["payment_status"])

    actor_label = _actor_label(actor)
    return (
        f"Marked {escape(_client_label(appointment))}'s appointment as {escape(status.name)} via {escape(actor_label)}."
    )


def append_note_to_appointment(appointment_id: str, note: str, *, actor: UserProfile | None = None) -> str:
    text = (note or "").strip()
    if not text:
        raise TelegramCommandError("Provide note text after the command.")

    appointment = Appointment.objects.filter(pk=appointment_id).first()
    if not appointment:
        raise TelegramCommandError("Appointment not found.")

    timestamp = timezone.localtime().strftime("%d %b %Y %H:%M")
    actor_label = _actor_label(actor)
    entry = f"[{timestamp}] {actor_label}: {text}"
    existing = (appointment.notes or "").strip()
    appointment.notes = f"{existing}\n{entry}".strip() if existing else entry
    appointment.save(update_fields=["notes"])
    return "Note stored successfully."


def link_subscription_to_profile(subscription: TelegramChatSubscription, identifier: str) -> str:
    token = (identifier or "").strip()
    if not token:
        raise TelegramCommandError("Provide a staff email or username.")

    user = (
        User.objects.filter(
            Q(email__iexact=token) | Q(username__iexact=token),
            is_active=True,
            is_staff=True,
        )
        .select_related("userprofile")
        .first()
    )
    if not user:
        raise TelegramCommandError("Staff account not found or not active.")

    profile = getattr(user, "userprofile", None)
    if profile is None:
        profile = UserProfile.objects.create(user=user)

    subscription.linked_profile = profile
    subscription.save(update_fields=["linked_profile"])
    display = user.get_full_name() or user.username or user.email
    return f"Linked this chat to {display}."


# ---------------------------------------------------------------------------
# ChatOps command processing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpsCommandContext:
    subscription: TelegramChatSubscription
    actor: UserProfile | None


@dataclass(frozen=True)
class OpsCommandSpec:
    name: str
    usage: str
    description: str
    handler: Callable[[dict[str, str], OpsCommandContext, "OpsCommandSpec"], str]
    requires_admin: bool = True
    requires_actor: bool = False


@dataclass
class _AdHocCartItem:
    service: Service
    master: MasterProfile
    start_time: datetime
    pk: str = field(default_factory=lambda: str(uuid4()))


def _ops_usage(spec: OpsCommandSpec) -> str:
    return f"Usage: {spec.usage}\n{spec.description}"


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_kv_args(payload: str) -> dict[str, str]:
    args: dict[str, str] = {}
    if not payload:
        return args
    length = len(payload)
    idx = 0
    while idx < length:
        while idx < length and payload[idx].isspace():
            idx += 1
        if idx >= length:
            break
        key_start = idx
        while idx < length and payload[idx] not in {' ', '\t', '='}:
            idx += 1
        key = payload[key_start:idx].strip()
        if not key:
            break
        if idx >= length or payload[idx] != '=':
            args[key.lower()] = ""
            continue
        idx += 1
        depth = 0
        quote = ''
        value_chars: list[str] = []
        while idx < length:
            ch = payload[idx]
            if quote:
                value_chars.append(ch)
                idx += 1
                if ch == quote:
                    quote = ''
                continue
            if ch in {'"', "'"}:
                quote = ch
                value_chars.append(ch)
                idx += 1
                continue
            if ch in {'[', '{', '('}:
                depth += 1
                value_chars.append(ch)
                idx += 1
                continue
            if ch in {']', '}', ')'}:
                if depth > 0:
                    depth -= 1
                value_chars.append(ch)
                idx += 1
                continue
            if ch.isspace() and depth == 0:
                break
            value_chars.append(ch)
            idx += 1
        args[key.lower()] = _strip_quotes("".join(value_chars).strip())
    return args


def _parse_list(value: str) -> list[str]:
    trimmed = value.strip()
    if trimmed.startswith('[') and trimmed.endswith(']'):
        trimmed = trimmed[1:-1]
    if not trimmed:
        return []
    return [part.strip() for part in trimmed.split(',') if part.strip()]


def _parse_bool(value: str | None, *, default: bool | None = None) -> bool:
    if value is None or value == "":
        if default is None:
            raise TelegramCommandError("Provide true/false.")
        return default
    normalized = value.strip().lower()
    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off"}
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    raise TelegramCommandError("Use true/false for boolean options.")


def _parse_date_value(token: str, label: str) -> date:
    parsed = parse_date(token)
    if not parsed:
        try:
            parsed = datetime.strptime(token, "%Y-%m-%d").date()
        except Exception as exc:  # noqa: BLE001
            raise TelegramCommandError(f"Invalid {label}; use YYYY-MM-DD.") from exc
    return parsed


def _parse_datetime_value(token: str, label: str) -> datetime:
    parsed = parse_datetime(token)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(token)
        except Exception as exc:  # noqa: BLE001
            raise TelegramCommandError(f"Invalid {label}; provide ISO-8601 with timezone.") from exc
    if not timezone.is_aware(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _require_arg(args: dict[str, str], key: str, spec: OpsCommandSpec) -> str:
    value = args.get(key)
    if not value:
        raise TelegramCommandError(_ops_usage(spec))
    return value


def _resolve_profile(profile_id: str, *, label: str) -> UserProfile:
    try:
        profile = UserProfile.objects.select_related("user").get(pk=profile_id)
    except (UserProfile.DoesNotExist, ValueError, TypeError) as exc:
        raise TelegramCommandError(f"{label} not found.") from exc
    return profile


def _resolve_service(service_id: str) -> Service:
    try:
        service = Service.objects.get(pk=service_id)
    except (Service.DoesNotExist, ValueError, TypeError) as exc:
        raise TelegramCommandError("Service not found.") from exc
    return service


def _resolve_master(master_id: str) -> MasterProfile:
    try:
        master = MasterProfile.objects.select_related("user__user").get(pk=master_id)
    except (MasterProfile.DoesNotExist, ValueError, TypeError) as exc:
        raise TelegramCommandError("Master not found.") from exc
    return master


def _resolve_form(form_id: str) -> ClientIntakeForm:
    try:
        form = ClientIntakeForm.objects.get(pk=form_id)
    except (ClientIntakeForm.DoesNotExist, ValueError, TypeError) as exc:
        raise TelegramCommandError("Intake form not found.") from exc
    return form


def _parse_items_payload(value: str, *, require_start: bool = True) -> list[dict[str, Any]]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise TelegramCommandError("Items must be valid JSON.") from exc
    if not isinstance(data, list) or not data:
        raise TelegramCommandError("Provide at least one item in items=[...] block.")
    parsed: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise TelegramCommandError("Each cart item must be an object with service/master/start_time.")
        if "service" not in entry or "master" not in entry:
            raise TelegramCommandError("Each item needs service and master fields.")
        if require_start and not entry.get("start_time"):
            raise TelegramCommandError("Each item must include start_time.")
        parsed.append(entry)
    return parsed


def _build_ad_hoc_items(payload: list[dict[str, Any]], *, default_start: datetime | None = None) -> list[_AdHocCartItem]:
    items: list[_AdHocCartItem] = []
    for entry in payload:
        service = _resolve_service(entry["service"])
        master = _resolve_master(entry["master"])
        start_raw = entry.get("start_time")
        start_time = (
            _parse_datetime_value(start_raw, "start_time")
            if start_raw
            else default_start or timezone.now()
        )
        items.append(_AdHocCartItem(service=service, master=master, start_time=start_time))
    return items


def _master_label(master: MasterProfile) -> str:
    user = getattr(master, "user", None)
    if user and getattr(user, "user", None):
        auth_user = user.user
        full_name = auth_user.get_full_name()
        if full_name:
            return full_name
        if auth_user.username:
            return auth_user.username
    if user and hasattr(user, "get_full_name"):
        name = user.get_full_name()
        if name:
            return name
    return getattr(master, "display_name", "") or f"Master {master.pk}"


def _profile_label(profile: UserProfile) -> str:
    if profile is None:
        return "Client"
    user = getattr(profile, "user", None)
    if user:
        full_name = user.get_full_name()
        if full_name:
            return full_name
        if getattr(user, "username", ""):
            return user.username
        if getattr(user, "email", ""):
            return user.email
    return f"Client {profile.pk}"


def _escape_pre(text: str) -> str:
    return f"<pre>{escape(text)}</pre>"


def _parse_ops_command(text: str) -> tuple[OpsCommandSpec, dict[str, str]] | None:
    normalized = (text or "").strip()
    if not normalized:
        return None
    if normalized.startswith('/'):
        normalized = normalized[1:]
    command, _, rest = normalized.partition(' ')
    command_key = command.lower()
    spec = OPS_COMMANDS.get(command_key)
    if not spec:
        return None
    args = _parse_kv_args(rest.strip()) if rest else {}
    return spec, args


def is_ops_command(text: str | None) -> bool:
    return _parse_ops_command(text or "") is not None


def execute_ops_command(text: str, subscription: TelegramChatSubscription) -> str:
    parsed = _parse_ops_command(text)
    if not parsed:
        raise TelegramCommandError("Unsupported command. Send /help for options.")
    spec, args = parsed
    if spec.requires_admin and not subscription.is_admin_channel:
        raise TelegramCommandError("Link this chat with /subscribe <token> to run admin commands.")
    actor = subscription.linked_profile
    if spec.requires_actor and not actor:
        raise TelegramCommandError("Link your staff profile via /link <email> before modifying data.")
    context = OpsCommandContext(subscription=subscription, actor=actor)
    return spec.handler(args, context, spec)


def list_ops_commands() -> list[OpsCommandSpec]:
    return list(OPS_COMMAND_LIST)


# Handler implementations ----------------------------------------------------


def _actor_user_id(context: OpsCommandContext) -> int | None:
    actor = context.actor
    if not actor:
        return None
    user = getattr(actor, "user", None)
    return getattr(user, "id", None) if user else None


def _handle_slots_list(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    service = _resolve_service(_require_arg(args, "service", spec))
    day_token = _require_arg(args, "date", spec)
    day = _parse_date_value(day_token, "date")
    step_value = args.get("step")
    step_minutes = 15
    if step_value:
        try:
            step_minutes = max(5, min(120, int(step_value)))
        except (TypeError, ValueError) as exc:
            raise TelegramCommandError("Step must be a number of minutes.") from exc
    master_value = args.get("master")
    master_obj = _resolve_master(master_value) if master_value else None

    seed = datetime(day.year, day.month, day.day, 12, 0)
    day_dt = timezone.make_aware(seed, timezone.get_current_timezone())
    slots_map = get_available_slots(service, day_dt, master=master_obj, step_minutes=step_minutes)

    masters: list[MasterProfile]
    if master_obj:
        masters = [master_obj]
    else:
        masters = list(get_service_masters(service))

    lines = [
        f"Service: {escape(service.name)}",
        f"Date: {day.isoformat()} (step {step_minutes} min)",
    ]
    if not masters or not slots_map:
        lines.append("No masters available for this selection.")
        return _format_message("Available slots", lines)

    for master in masters:
        master_slots = slots_map.get(master.id) or []
        if not master_slots:
            lines.append(f"{escape(_master_label(master))}: no free slots")
            continue
        slot_list = ", ".join(slot.isoformat() for slot in master_slots[:50])
        lines.append(f"{escape(_master_label(master))}: {escape(slot_list)}")

    return _format_message("Available slots", lines)


def _handle_appointment_create(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    profile = _resolve_profile(_require_arg(args, "client", spec), label="Client profile")
    items_raw = _require_arg(args, "items", spec)
    payload = _parse_items_payload(items_raw, require_start=True)
    ad_hoc_items = _build_ad_hoc_items(payload)
    try:
        appointment = create_appointment_from_cart_items(profile=profile, items=ad_hoc_items)
    except ValidationError as exc:
        raise TelegramCommandError("; ".join(exc.messages)) from exc
    except Exception as exc:  # noqa: BLE001
        raise TelegramCommandError("Unable to create appointment.") from exc

    appointment.refresh_from_db()
    appointment_items = list(
        appointment.items.select_related("service", "master__user__user").order_by("start_time")
    )
    item_lines = [
        f"• {escape(getattr(item.service, 'name', 'Service'))} with {escape(_master_label(item.master))} at {escape(item.start_time.isoformat())}"
        for item in appointment_items
    ]
    payment_label = getattr(getattr(appointment, "payment_status", None), "name", "Pending")
    start_text = (
        timezone.localtime(appointment.start_time).isoformat()
        if appointment.start_time
        else "Not scheduled"
    )
    lines = [
        f"Appointment ID: <code>{escape(str(appointment.pk))}</code>",
        f"Client: {escape(_client_label(appointment))}",
        f"Start: {escape(start_text)}",
        f"Payment status: {escape(payment_label)}",
        f"Total: {_format_money(appointment.final_price)}",
        "Items:",
        *item_lines,
    ]
    return _format_message("Appointment created", lines)


def _handle_appointment_add_item(args: dict[str, str], context: OpsCommandContext, spec: OpsCommandSpec) -> str:
    appointment_id = _require_arg(args, "appointment", spec)
    appointment = (
        Appointment.objects.select_related("client__user", "payment_status")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        raise TelegramCommandError("Appointment not found.")

    service = _resolve_service(_require_arg(args, "service", spec))
    master = _resolve_master(_require_arg(args, "master", spec))
    start_token = args.get("start_time")
    start_time = (
        _parse_datetime_value(start_token, "start_time")
        if start_token
        else appointment.start_time or timezone.now()
    )

    item = AppointmentItem(
        appointment=appointment,
        service=service,
        master=master,
        start_time=start_time,
    )
    now_ts = timezone.now()
    item._initial_status_code = "BOOKED"
    item._initial_status_user_id = _actor_user_id(context)
    item._initial_status_timestamp = now_ts
    item._initial_status_note = "bot-add-item"
    item._created_via_admin = True
    try:
        item.full_clean()
        item.save()
    except ValidationError as exc:
        raise TelegramCommandError("; ".join(exc.messages)) from exc

    appointment.sync_start_time_from_items(save=True)
    appointment.recompute_totals(save=True)

    lines = [
        f"Appointment ID: <code>{escape(str(appointment.pk))}</code>",
        f"New item ID: <code>{escape(str(item.pk))}</code>",
        f"Service: {escape(service.name)}",
        f"Master: {escape(_master_label(master))}",
        f"Start: {escape(item.start_time.isoformat())}",
        f"Total now: {_format_money(appointment.final_price)}",
    ]
    return _format_message("Item added", lines)


def _handle_appointment_cancel(args: dict[str, str], context: OpsCommandContext, spec: OpsCommandSpec) -> str:
    appointment_id = _require_arg(args, "appointment", spec)
    appointment = (
        Appointment.objects.select_related("client__user", "payment_status")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        raise TelegramCommandError("Appointment not found.")

    reason = args.get("reason") or ""
    actor_user_id = _actor_user_id(context)
    cancellable = list(
        AppointmentItem.objects.with_current_status()
        .select_related("service", "status", "appointment")
        .filter(appointment=appointment)
    )
    updated: list[AppointmentItem] = []
    for item in cancellable:
        current_code = (item.current_status_code or getattr(getattr(item, "status", None), "code", "")) or ""
        if current_code.upper() == "CANCELLED":
            continue
        record_item_status(item, "CANCELLED", set_by_user_id=actor_user_id, note=reason or "bot-cancel")
        send_item_cancellation_email.delay(str(item.pk), reason=reason)
        updated.append(item)

    if not updated:
        raise TelegramCommandError("All items are already cancelled.")

    with transaction.atomic():
        status = get_or_create_status("Cancelled")
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            status=status,
            set_by=context.actor,
        )

    lines = [
        f"Appointment ID: <code>{escape(str(appointment.pk))}</code>",
        f"Items cancelled: {len(updated)}",
        f"Reason: {escape(reason or 'not provided')}",
    ]
    return _format_message("Appointment cancelled", lines)


def _handle_item_set_status(args: dict[str, str], context: OpsCommandContext, spec: OpsCommandSpec) -> str:
    item_id = _require_arg(args, "item", spec)
    status_token = _require_arg(args, "status", spec)
    note = args.get("note")
    item = (
        AppointmentItem.objects.select_related("service", "appointment__client__user", "status")
        .filter(pk=item_id)
        .first()
    )
    if not item:
        raise TelegramCommandError("Item not found.")

    status_code = status_token.strip().upper()
    actor_user_id = _actor_user_id(context)
    result = record_item_status(
        item,
        status_code,
        set_by_user_id=actor_user_id,
        note=note or "bot-status",
    )

    lines = [
        f"Item ID: <code>{escape(str(item.pk))}</code>",
        f"Service: {escape(getattr(item.service, 'name', 'Service'))}",
        f"Status: {escape(result.status.name)}",
    ]
    return _format_message("Item status updated", lines)


def _handle_item_reschedule(args: dict[str, str], context: OpsCommandContext, spec: OpsCommandSpec) -> str:
    item_id = _require_arg(args, "item", spec)
    new_start = _parse_datetime_value(_require_arg(args, "start_time", spec), "start_time")
    item = (
        AppointmentItem.objects.select_related("service", "appointment", "master__user__user")
        .filter(pk=item_id)
        .first()
    )
    if not item:
        raise TelegramCommandError("Item not found.")

    update_fields = ["start_time"]
    master_arg = args.get("master")
    if master_arg:
        item.master = _resolve_master(master_arg)
        update_fields.append("master")

    item.start_time = new_start
    computed_end = item.compute_end_time()
    if computed_end:
        item.end_time = computed_end
        update_fields.append("end_time")

    try:
        item.full_clean()
        item.save(update_fields=update_fields)
    except ValidationError as exc:
        raise TelegramCommandError("; ".join(exc.messages)) from exc

    appointment = getattr(item, "appointment", None)
    if appointment:
        appointment.sync_start_time_from_items(save=True)

    lines = [
        f"Item ID: <code>{escape(str(item.pk))}</code>",
        f"New start: {escape(item.start_time.isoformat())}",
        f"Master: {escape(_master_label(item.master))}",
    ]
    return _format_message("Item rescheduled", lines)


def _handle_timeoff_add(args: dict[str, str], context: OpsCommandContext, spec: OpsCommandSpec) -> str:
    master = _resolve_master(_require_arg(args, "master", spec))
    start_dt = _parse_datetime_value(_require_arg(args, "start", spec), "start")
    end_dt = _parse_datetime_value(_require_arg(args, "end", spec), "end")
    if end_dt <= start_dt:
        raise TelegramCommandError("End must be after start.")
    note = (args.get("note") or "").strip()

    if note:
        slug = slugify(note)[:50] or "manual-block"
        reason, _ = TimeOffReason.objects.get_or_create(code=slug, defaults={"name": note[:100]})
    else:
        reason = TimeOffReason.objects.order_by("name").first()
        if not reason:
            reason = TimeOffReason.objects.create(code="manual-block", name="Manual block")

    availability = MasterAvailability(master=master, start_time=start_dt, end_time=end_dt, reason=reason)
    try:
        availability.full_clean()
        availability.save()
    except ValidationError as exc:
        raise TelegramCommandError("; ".join(exc.messages)) from exc

    lines = [
        f"Master: {escape(_master_label(master))}",
        f"Window: {escape(start_dt.isoformat())} → {escape(end_dt.isoformat())}",
        f"Reason: {escape(reason.name)}",
    ]
    return _format_message("Time off recorded", lines)


def _handle_timeoff_list(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    master = _resolve_master(_require_arg(args, "master", spec))
    date_token = args.get("date")
    qs = MasterAvailability.objects.filter(master=master)
    if date_token:
        day = _parse_date_value(date_token, "date")
        start_of_day = timezone.make_aware(datetime(day.year, day.month, day.day, 0, 0), timezone.get_current_timezone())
        end_of_day = start_of_day + timedelta(days=1)
        qs = qs.filter(start_time__lt=end_of_day, end_time__gt=start_of_day)
    else:
        qs = qs.filter(end_time__gte=timezone.now() - timedelta(days=1))
    entries = list(qs.order_by("start_time")[:20])
    if not entries:
        return _format_message("Time off blocks", ["No active blocks found."])

    lines = [f"Master: {escape(_master_label(master))}"]
    for entry in entries:
        lines.append(
            f"• {entry.start_time.isoformat()} → {entry.end_time.isoformat()} ({escape(getattr(entry.reason, 'name', 'Reason'))})"
        )
    return _format_message("Time off blocks", lines)


def _handle_calendar_view(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    day_token = _require_arg(args, "date", spec)
    day = _parse_date_value(day_token, "date")
    tz = timezone.get_current_timezone()
    start_of_day = timezone.make_aware(datetime(day.year, day.month, day.day, 0, 0), tz)
    end_of_day = start_of_day + timedelta(days=1)

    items_qs = (
        AppointmentItem.objects.with_current_status()
        .select_related(
            "appointment__client__user",
            "appointment__payment_status",
            "service",
            "master__user__user",
            "status",
        )
        .prefetch_related(
            "appointment__items__service",
            "appointment__items__status",
            "appointment__product_sales",
            Prefetch(
                "appointment__payments",
                queryset=Payment.objects.filter(status="succeeded").only("amount_received", "amount_refunded", "status"),
                to_attr="prefetched_succeeded_payments",
            ),
        )
        .filter(start_time__lt=end_of_day, end_time__gt=start_of_day)
    )

    service_filter = args.get("service")
    if service_filter:
        items_qs = items_qs.filter(service_id=service_filter)

    status_filters = _parse_list(args.get("status", ""))
    if status_filters:
        items_qs = items_qs.filter(status_id__in=status_filters)

    payment_filters = _parse_list(args.get("payment_status", ""))
    if payment_filters:
        items_qs = items_qs.filter(appointment__payment_status_id__in=payment_filters)

    master_filters = _parse_list(args.get("master", ""))
    base_masters = list(
        MasterProfile.objects.select_related("user__user").order_by(
            "user__user__first_name",
            "user__user__last_name",
        )
    )
    if master_filters:
        master_set = {str(mid) for mid in master_filters}
        masters = [m for m in base_masters if str(m.pk) in master_set]
        if not masters:
            items_qs = items_qs.none()
    else:
        masters = base_masters

    availabilities = MasterAvailability.objects.filter(start_time__lte=end_of_day, end_time__gte=start_of_day)

    time_pointer = datetime(2000, 1, 1, 8, 0)
    end_pointer = datetime(2000, 1, 1, 21, 0)
    calendar_table = createTable(day, time_pointer, end_pointer, [], items_qs, masters, availabilities)

    context = {
        "calendar_table": calendar_table,
        "masters": masters,
        "filter_masters": base_masters,
        "selected_masters": master_filters,
    }
    fragment = render_to_string("admin/appointments_calendar_partial.html", context)

    filters_summary = []
    if status_filters:
        filters_summary.append(f"status={','.join(status_filters)}")
    if payment_filters:
        filters_summary.append(f"payment_status={','.join(payment_filters)}")
    if master_filters:
        filters_summary.append(f"master={','.join(master_filters)}")
    if service_filter:
        filters_summary.append(f"service={service_filter}")

    lines = [
        f"Date: {day.isoformat()}",
        f"Filters: {', '.join(filters_summary) if filters_summary else 'none'}",
        _escape_pre(fragment),
    ]
    return _format_message("Calendar view", lines)


def _handle_calendar_export(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    day_token = _require_arg(args, "date", spec)
    day = _parse_date_value(day_token, "date")
    params: list[tuple[str, str]] = [("date", day.isoformat())]
    for key in ("status", "payment_status", "master"):
        values = _parse_list(args.get(key, ""))
        params.extend((key, value) for value in values)
    service_value = args.get("service")
    if service_value:
        params.append(("service", service_value))

    try:
        base_url = reverse("admin:core_appointment_export_xlsx")
    except NoReverseMatch as exc:
        raise TelegramCommandError("Export endpoint is not configured.") from exc

    query = urlencode(params, doseq=True) if params else ""
    url = f"{base_url}?{query}" if query else base_url

    lines = [
        f"Date: {day.isoformat()}",
        f"Link: <a href=\"{escape(url)}\">Download XLSX</a>",
    ]
    return _format_message("Calendar export", lines)


def _handle_masters_for_service(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    service = _resolve_service(_require_arg(args, "service", spec))
    masters = list(get_service_masters(service))
    if not masters:
        return _format_message("Service masters", ["No masters linked to this service yet."])
    lines = [f"Service: {escape(service.name)}"]
    for master in masters:
        lines.append(f"• {escape(_master_label(master))} (ID {escape(str(master.pk))})")
    return _format_message("Service masters", lines)


def _handle_services_for_master(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    master = _resolve_master(_require_arg(args, "master", spec))
    services = list(
        Service.objects.filter(servicemaster__master=master, is_active=True).order_by("name")
    )
    if not services:
        return _format_message("Master services", ["No services assigned to this master."])
    lines = [f"Master: {escape(_master_label(master))}"]
    for service in services:
        duration = (service.duration_min or 0) + (service.extra_time_min or 0)
        lines.append(
            f"• {escape(service.name)} (ID {escape(str(service.pk))}, {duration} min)"
        )
    return _format_message("Master services", lines)


def _handle_rooms_check(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    service = _resolve_service(_require_arg(args, "service", spec))
    start_dt = _parse_datetime_value(_require_arg(args, "start", spec), "start")
    end_dt = _parse_datetime_value(_require_arg(args, "end", spec), "end")
    if end_dt <= start_dt:
        raise TelegramCommandError("End must be after start.")
    allowed_rooms = list(service.allowed_rooms.all())
    if not allowed_rooms:
        return _format_message("Room check", ["Service is not restricted by rooms."])

    room_ids = [room.pk for room in allowed_rooms]
    room_blocks = booking_logic._room_busy_intervals(room_ids, start_dt)
    has_capacity = booking_logic._room_has_capacity(room_blocks, room_ids, start_dt, end_dt)

    if has_capacity:
        lines = [
            f"Service: {escape(service.name)}",
            f"Window: {escape(start_dt.isoformat())} → {escape(end_dt.isoformat())}",
            "Rooms available: yes",
        ]
        return _format_message("Room check", lines)

    conflict_lines = []
    for room in allowed_rooms:
        blocks = room_blocks.get(room.pk, [])
        for busy_start, busy_end in blocks:
            if start_dt < busy_end and end_dt > busy_start:
                conflict_lines.append(
                    f"• {escape(getattr(room, 'room', f'Room {room.pk}'))} busy {escape(busy_start.isoformat())} → {escape(busy_end.isoformat())}"
                )
                break
    if not conflict_lines:
        conflict_lines.append("• Conflicts detected but could not resolve specific rooms.")

    lines = [
        f"Service: {escape(service.name)}",
        f"Window: {escape(start_dt.isoformat())} → {escape(end_dt.isoformat())}",
        "Rooms available: no",
        *conflict_lines,
    ]
    return _format_message("Room check", lines)


def _handle_intake_assign(args: dict[str, str], context: OpsCommandContext, spec: OpsCommandSpec) -> str:
    profile = _resolve_profile(_require_arg(args, "client", spec), label="Client profile")
    forms_token = _require_arg(args, "forms", spec)
    form_ids = _parse_list(forms_token)
    if not form_ids:
        raise TelegramCommandError("Provide at least one form id in forms=[...].")
    forms = [_resolve_form(fid) for fid in form_ids]
    assigned_by = getattr(context.actor, "user", None)
    created = ensure_assignments(profile=profile, forms=forms, assigned_by=assigned_by)
    lines = [
        f"Client: {escape(_profile_label(profile))}",
        f"Forms processed: {len(forms)}",
        f"Assignments created: {created}",
    ]
    return _format_message("Intake assignments", lines)


def _handle_intake_universal_profile(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    profile = _resolve_profile(_require_arg(args, "client", spec), label="Client profile")
    created = ensure_universal_assignments_for_profile(profile)
    lines = [
        f"Client: {escape(_profile_label(profile))}",
        f"Assignments ensured: {created}",
    ]
    return _format_message("Universal intake assignments", lines)


def _handle_intake_universal_form(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    form = _resolve_form(_require_arg(args, "form", spec))
    created = ensure_universal_assignments_for_form(form)
    lines = [
        f"Form: {escape(form.name)}",
        f"Assignments created: {created}",
    ]
    return _format_message("Universal form enforcement", lines)


def _handle_promo_list(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    service = _resolve_service(_require_arg(args, "service", spec))
    today = timezone.localdate()
    promos = (
        PromoCode.objects.filter(active=True, start_date__lte=today, end_date__gte=today)
        .filter(Q(applicable_services__isnull=True) | Q(applicable_services=service))
        .distinct()
        .order_by("code")
    )
    promos_list = list(promos)
    if not promos_list:
        return _format_message("Promotions", ["No active promo codes for this service."])
    lines = [f"Service: {escape(service.name)}"]
    for promo in promos_list[:20]:
        window = f"{promo.start_date}–{promo.end_date}"
        lines.append(f"• {escape(promo.code)} — {promo.discount_percent}% ({escape(window)})")
    return _format_message("Promotions", lines)


def _handle_client_search(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    query = _require_arg(args, "q", spec)
    text = query.strip()
    if not text:
        raise TelegramCommandError("Provide a search query.")
    digits = re.sub(r"\D+", "", text)
    q_obj = (
        Q(user__first_name__icontains=text)
        | Q(user__last_name__icontains=text)
        | Q(user__email__icontains=text)
        | Q(user__username__icontains=text)
    )
    if digits:
        pattern = r"\D*".join(re.escape(d) for d in digits)
        q_obj |= Q(phone__iregex=pattern)
    profiles = list(
        UserProfile.objects.select_related("user")
        .filter(q_obj)
        .order_by("user__first_name", "user__last_name")[:10]
    )
    if not profiles:
        return _format_message("Client search", ["No matches found."])
    lines = [f"Query: {escape(text)}"]
    for profile in profiles:
        phone = getattr(profile, "phone", "") or "—"
        email = getattr(getattr(profile, "user", None), "email", "") or "—"
        lines.append(
            f"• {escape(_profile_label(profile))} (ID {escape(str(profile.pk))}, phone {escape(phone)}, email {escape(email)})"
        )
    return _format_message("Client search", lines)


def _handle_appointment_quote(args: dict[str, str], context: OpsCommandContext, spec: OpsCommandSpec) -> str:
    items_raw = _require_arg(args, "items", spec)
    payload = _parse_items_payload(items_raw, require_start=False)
    ad_hoc_items = _build_ad_hoc_items(payload, default_start=timezone.now())
    if not ad_hoc_items:
        raise TelegramCommandError("Provide at least one service in items list.")

    client_arg = args.get("client")
    if client_arg:
        profile_context: UserProfile | SimpleNamespace = _resolve_profile(client_arg, label="Client profile")
    elif context.actor:
        profile_context = context.actor
    else:
        profile_context = SimpleNamespace(personal_discount_percent=0)

    tax_enabled_flag = gst_enabled()
    gst_value = args.get("gst_enabled")
    if gst_value is not None:
        tax_enabled_flag = _parse_bool(gst_value, default=tax_enabled_flag)

    currency = (getattr(settings, "STRIPE_CURRENCY", "cad") or "cad").lower()
    tax_percent = gst_percent()
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    item_lines: list[str] = []
    for entry in ad_hoc_items:
        payload = pricing_utils._build_item_pricing(
            entry,
            profile_context,
            currency,
            tax_percent=tax_percent,
            tax_enabled=tax_enabled_flag,
        )
        subtotal += Decimal(payload["subtotal_decimal"])
        tax_total += Decimal(payload["tax_decimal"])
        item_lines.append(
            f"• {escape(payload['name'])}: {escape(payload['total_with_tax_display'])} (tax {escape(payload['tax_display'])})"
        )

    pre_fee_total = subtotal + tax_total
    fee_amount = card_processing_fee(pre_fee_total)
    grand_total = pre_fee_total + fee_amount

    lines = [
        f"Items: {len(ad_hoc_items)}",
        *item_lines,
        f"Subtotal: {_format_money(subtotal, currency)}",
        f"Tax: {_format_money(tax_total, currency)} (GST {'on' if tax_enabled_flag else 'off'})",
        f"Processing fee: {_format_money(fee_amount, currency)}",
        f"Grand total: {_format_money(grand_total, currency)}",
    ]
    return _format_message("Quote", lines)


def _handle_payment_set_status(args: dict[str, str], _: OpsCommandContext, spec: OpsCommandSpec) -> str:
    appointment_id = _require_arg(args, "appointment", spec)
    status_token = _require_arg(args, "status", spec)
    appointment = (
        Appointment.objects.select_related("client__user", "payment_status")
        .filter(pk=appointment_id)
        .first()
    )
    if not appointment:
        raise TelegramCommandError("Appointment not found.")

    status_obj = (
        PaymentStatus.objects.filter(pk=status_token).first()
        or PaymentStatus.objects.filter(name__iexact=status_token).first()
    )
    if not status_obj:
        raise TelegramCommandError("Payment status not found.")
    if appointment.payment_status_id == status_obj.id:
        return _format_message("Payment status", [f"Already set to {escape(status_obj.name)}."])

    appointment.payment_status = status_obj
    appointment.save(update_fields=["payment_status"])

    lines = [
        f"Appointment ID: <code>{escape(str(appointment.pk))}</code>",
        f"Payment status: {escape(status_obj.name)}",
    ]
    return _format_message("Payment status updated", lines)


OPS_COMMAND_LIST: list[OpsCommandSpec] = [
    OpsCommandSpec(
        name="slots:list",
        usage="slots:list service=<SERVICE_ID> date=<YYYY-MM-DD> [master=<MASTER_ID>] [step=<minutes>]",
        description="List available start slots for a service on a specific day.",
        handler=_handle_slots_list,
    ),
    OpsCommandSpec(
        name="appointment:create",
        usage="appointment:create client=<PROFILE_ID> items=[{\"service\":...,\"master\":...,\"start_time\":...},…]",
        description="Create a multi-service appointment from cart-like items.",
        handler=_handle_appointment_create,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="appointment:add-item",
        usage="appointment:add-item appointment=<APPT_ID> service=<SERVICE_ID> master=<MASTER_ID> [start_time=<ISO>]",
        description="Append another service item to an existing appointment.",
        handler=_handle_appointment_add_item,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="appointment:cancel",
        usage="appointment:cancel appointment=<APPT_ID> [reason=<TEXT>]",
        description="Cancel all active items inside an appointment.",
        handler=_handle_appointment_cancel,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="item:set-status",
        usage="item:set-status item=<ITEM_ID> status=<BOOKED|CONFIRMED|CANCELLED|COMPLETED|NO_SHOW> [note=<TEXT>]",
        description="Force a specific status on an appointment item.",
        handler=_handle_item_set_status,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="item:reschedule",
        usage="item:reschedule item=<ITEM_ID> start_time=<ISO> [master=<MASTER_ID>]",
        description="Move an appointment item to a new start time and/or master.",
        handler=_handle_item_reschedule,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="timeoff:add",
        usage="timeoff:add master=<MASTER_ID> start=<ISO> end=<ISO> [note=<TEXT>]",
        description="Block off a master’s availability window.",
        handler=_handle_timeoff_add,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="timeoff:list",
        usage="timeoff:list master=<MASTER_ID> [date=<YYYY-MM-DD>]",
        description="List existing time off blocks for a master.",
        handler=_handle_timeoff_list,
    ),
    OpsCommandSpec(
        name="calendar:view",
        usage="calendar:view date=<YYYY-MM-DD> [status=<ID,…>] [payment_status=<ID,…>] [master=<ID,…>] [service=<ID>]",
        description="Render the admin calendar table for a given day and filters.",
        handler=_handle_calendar_view,
    ),
    OpsCommandSpec(
        name="calendar:export-xlsx",
        usage="calendar:export-xlsx date=<YYYY-MM-DD> [filters…]",
        description="Build an export link for the filtered calendar view.",
        handler=_handle_calendar_export,
    ),
    OpsCommandSpec(
        name="masters:for-service",
        usage="masters:for-service service=<SERVICE_ID>",
        description="List masters who can perform the service.",
        handler=_handle_masters_for_service,
    ),
    OpsCommandSpec(
        name="services:for-master",
        usage="services:for-master master=<MASTER_ID>",
        description="List services linked to a master profile.",
        handler=_handle_services_for_master,
    ),
    OpsCommandSpec(
        name="rooms:check",
        usage="rooms:check service=<SERVICE_ID> start=<ISO> end=<ISO>",
        description="Validate room capacity for a service time window.",
        handler=_handle_rooms_check,
    ),
    OpsCommandSpec(
        name="intake:assign",
        usage="intake:assign client=<PROFILE_ID> forms=[<FORM_ID>,…]",
        description="Assign specific intake forms to a client profile.",
        handler=_handle_intake_assign,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="intake:ensure-universal-for-profile",
        usage="intake:ensure-universal-for-profile client=<PROFILE_ID>",
        description="Ensure a client has all universal active forms.",
        handler=_handle_intake_universal_profile,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="intake:ensure-universal-for-form",
        usage="intake:ensure-universal-for-form form=<FORM_ID>",
        description="Push a universal form to every client lacking it.",
        handler=_handle_intake_universal_form,
        requires_actor=True,
    ),
    OpsCommandSpec(
        name="promo:list",
        usage="promo:list service=<SERVICE_ID>",
        description="List active promo codes applicable to a service.",
        handler=_handle_promo_list,
    ),
    OpsCommandSpec(
        name="client:search",
        usage='client:search q="<name/email/phone>"',
        description="Search client profiles by name, email, username, or phone digits.",
        handler=_handle_client_search,
    ),
    OpsCommandSpec(
        name="appointment:quote",
        usage="appointment:quote items=[…] [gst_enabled=<true|false>] [client=<PROFILE_ID>]",
        description="Calculate totals, tax, and card fees for given service items.",
        handler=_handle_appointment_quote,
    ),
    OpsCommandSpec(
        name="payment:set-status",
        usage="payment:set-status appointment=<APPT_ID> status=<STATUS_ID|NAME>",
        description="Update the payment status of an appointment.",
        handler=_handle_payment_set_status,
        requires_actor=True,
    ),
]

OPS_COMMANDS: dict[str, OpsCommandSpec] = {spec.name: spec for spec in OPS_COMMAND_LIST}

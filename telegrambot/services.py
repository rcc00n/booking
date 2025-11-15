"""Service layer for Telegram bot integration."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone
from django.utils.html import escape

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import Message

from core.models import Appointment, AppointmentItem, AppointmentQuerySet, Payment, PaymentStatus, UserProfile
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

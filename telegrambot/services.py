"""Service layer for Telegram bot integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from math import ceil
from typing import Iterable, Sequence
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch, Q, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.html import escape

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from core.models import (
    Appointment,
    AppointmentItem,
    AppointmentQuerySet,
    MasterProfile,
    Payment,
    PaymentStatus,
    Service,
    UserProfile,
)
from core.services.booking import create_appointment_from_cart_items, get_available_slots, get_service_masters
from core.services.intake_assignments import ensure_assignments, ensure_universal_assignments_for_profile
from core.services.item_status import record_item_status
from .models import (
    TelegramBookingSession,
    TelegramBotSettings,
    TelegramBroadcast,
    TelegramChatSubscription,
)

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


# ---------------------------------------------------------------------------
# Client-facing booking flow helpers
# ---------------------------------------------------------------------------

MAIN_MENU_BOOK = "📅 Book"
MAIN_MENU_BOOKINGS = "🧾 My bookings"
MAIN_MENU_HELP = "❓ Help"
BOOKING_CALLBACK_PREFIX = "b|"
OPS_CALLBACK_PREFIX = "ops|"


def _main_menu_markup() -> ReplyKeyboardMarkup:
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton(MAIN_MENU_BOOK), KeyboardButton(MAIN_MENU_BOOKINGS))
    markup.row(KeyboardButton(MAIN_MENU_HELP))
    return markup


def send_client_menu(bot: TeleBot, chat_id: int, *, subtitle: str | None = None) -> None:
    heading = "Welcome back to Malva Booking" if subtitle is None else subtitle
    bot.send_message(
        chat_id,
        f"{heading}\nChoose an option below:",
        reply_markup=_main_menu_markup(),
    )


def _ensure_booking_session(subscription: TelegramChatSubscription) -> TelegramBookingSession:
    session, _ = TelegramBookingSession.objects.get_or_create(subscription=subscription)
    if not session.payload:
        session.reset()
        session.save(update_fields=["payload", "state", "active_message_id", "last_error"])
    return session


def append_booking_context(subscription: TelegramChatSubscription, role: str, text: str) -> None:
    session = _ensure_booking_session(subscription)
    session.append_context(role, text)
    session.save(update_fields=["context_log"])


def _ensure_client_profile(subscription: TelegramChatSubscription, telegram_user=None) -> UserProfile:
    profile = subscription.client_profile
    if profile:
        return profile

    username = None
    first_name = ""
    last_name = ""
    if telegram_user:
        username = getattr(telegram_user, "username", None)
        first_name = getattr(telegram_user, "first_name", "") or ""
        last_name = getattr(telegram_user, "last_name", "") or ""
    username = username or f"tg_{abs(subscription.chat_id)}"
    email = f"{username}@telegram.local"

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password", "email", "first_name", "last_name"])

    profile = getattr(user, "userprofile", None)
    if profile is None:
        profile = UserProfile.objects.create(user=user)

    if subscription.client_profile_id != profile.id:
        subscription.client_profile = profile
        subscription.save(update_fields=["client_profile"])

    return profile


def _public_url(path: str) -> str:
    base = getattr(settings, "PUBLIC_ROOT_URL", "") or ""
    if not base:
        return path
    normalized_base = base if base.endswith("/") else f"{base}/"
    return urljoin(normalized_base, path.lstrip("/"))


def _master_display(master: MasterProfile | None, *, fallback: str | None = None) -> str:
    if master is None:
        return fallback or "Team"
    profile = getattr(master, "user", None)
    if profile:
        auth_user = getattr(profile, "user", None)
        if auth_user:
            full_name = auth_user.get_full_name()
            if full_name:
                return full_name
            if auth_user.username:
                return auth_user.username
        if hasattr(profile, "get_full_name"):
            name = profile.get_full_name()
            if name:
                return name
    display = getattr(master, "display_name", None)
    if display:
        return display
    profession = getattr(master, "profession", None)
    if profession:
        return profession
    return fallback or f"Master {getattr(master, 'pk', '?')}"


_SENTINEL = object()


@dataclass
class _BotCartItem:
    service: Service
    master: MasterProfile
    start_time: datetime


def _chunk(items: Sequence, size: int) -> list[list]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _inline_markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for row in rows:
        markup.row(*row)
    return markup


def _format_date_label(day: date) -> str:
    return day.strftime("%a %d %b")


def _format_time_label(slot: datetime) -> str:
    return timezone.localtime(slot).strftime("%H:%M")


def _date_token(day: date) -> str:
    return day.strftime("%Y%m%d")


def _parse_date_token(token: str) -> date:
    return datetime.strptime(token, "%Y%m%d").date()


class ClientBookingFlow:
    SERVICE_PAGE_SIZE = 6
    MASTER_PAGE_SIZE = 6
    TIME_PAGE_SIZE = 12

    def __init__(self, bot: TeleBot, subscription: TelegramChatSubscription, *, session: TelegramBookingSession | None = None):
        self.bot = bot
        self.subscription = subscription
        self.session = session or _ensure_booking_session(subscription)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def payload(self) -> dict:
        return dict(self.session.payload or {})

    def start(self, *, reuse_defaults: bool = True) -> None:
        payload = self.payload
        payload.pop("date", None)
        payload.pop("slot_iso", None)
        payload.pop("slot_label", None)
        payload.pop("reschedule_item_id", None)

        last_selection = payload.get("last_selection", {})
        service_id = last_selection.get("service_id") if reuse_defaults else None
        master_id = last_selection.get("master_id") if reuse_defaults else None
        if service_id and master_id:
            service = Service.objects.filter(pk=service_id, is_active=True).first()
            master = MasterProfile.objects.filter(pk=master_id).first()
            if service and master:
                payload["service_id"] = str(service.pk)
                payload["master_id"] = str(master.pk)
                self._commit(payload=payload, state=TelegramBookingSession.STATE_DATE)
                self.show_date_picker(info="Using your recent selection. Change it anytime with ◀ Back.")
                return

        payload.pop("service_id", None)
        payload.pop("master_id", None)
        self._commit(payload=payload, state=TelegramBookingSession.STATE_SERVICE)
        self.show_service_picker()

    def show_service_picker(self, *, page: int = 0, info: str | None = None) -> None:
        services = list(Service.objects.filter(is_active=True).order_by("name"))
        if not services:
            self._send_or_edit("We do not have active services yet. Please come back later.", InlineKeyboardMarkup())
            return

        total_pages = max(1, ceil(len(services) / self.SERVICE_PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))
        start = page * self.SERVICE_PAGE_SIZE
        rows = []
        for service in services[start : start + self.SERVICE_PAGE_SIZE]:
            rows.append([InlineKeyboardButton(service.name, callback_data=self._cb("svc", str(service.pk)))])

        if total_pages > 1:
            nav_row: list[InlineKeyboardButton] = []
            if page > 0:
                nav_row.append(InlineKeyboardButton("◀ Prev", callback_data=self._cb("svcpg", str(page - 1))))
            nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=self._cb("noop")))
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("Next ▶", callback_data=self._cb("svcpg", str(page + 1))))
            rows.append(nav_row)

        rows.append([InlineKeyboardButton("✖ Cancel", callback_data=self._cb("cancel"))])
        markup = _inline_markup(rows)

        lines = ["<b>Choose a service</b>", "Pick what you'd like to book today."]
        if info:
            lines.append(info)
        self._commit(state=TelegramBookingSession.STATE_SERVICE)
        self._send_or_edit("\n".join(lines), markup)

    def select_service(self, service_id: str) -> None:
        service = Service.objects.filter(pk=service_id, is_active=True).first()
        if not service:
            self.show_service_picker(info="Service is no longer available; please pick another one.")
            return
        payload = self.payload
        payload["service_id"] = str(service.pk)
        payload.pop("master_id", None)
        payload.pop("date", None)
        payload.pop("slot_iso", None)
        payload.pop("slot_label", None)
        self._commit(payload=payload, state=TelegramBookingSession.STATE_MASTER)
        self.show_master_picker()

    def show_master_picker(self, *, page: int = 0, info: str | None = None) -> None:
        service = self._selected_service()
        masters = list(get_service_masters(service))
        if not masters:
            self.show_service_picker(info="No staff available for this service. Please choose a different service.")
            return
        total_pages = max(1, ceil(len(masters) / self.MASTER_PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))
        start = page * self.MASTER_PAGE_SIZE
        rows = []
        for master in masters[start : start + self.MASTER_PAGE_SIZE]:
            label = _master_display(master, fallback=f"Master {master.pk}")
            rows.append([InlineKeyboardButton(label, callback_data=self._cb("mst", str(master.pk)))])

        if total_pages > 1:
            nav_row: list[InlineKeyboardButton] = []
            if page > 0:
                nav_row.append(InlineKeyboardButton("◀ Prev", callback_data=self._cb("mstpg", str(page - 1))))
            nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=self._cb("noop")))
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("Next ▶", callback_data=self._cb("mstpg", str(page + 1))))
            rows.append(nav_row)

        rows.append(
            [
                InlineKeyboardButton("◀ Back", callback_data=self._cb("back", "service")),
                InlineKeyboardButton("✖ Cancel", callback_data=self._cb("cancel")),
            ]
        )
        markup = _inline_markup(rows)

        lines = [f"<b>Who would you like for {escape(service.name)}?</b>"]
        if info:
            lines.append(info)
        self._commit(state=TelegramBookingSession.STATE_MASTER)
        self._send_or_edit("\n".join(lines), markup)

    def select_master(self, master_id: str) -> None:
        master = MasterProfile.objects.filter(pk=master_id).first()
        if not master:
            self.show_master_picker(info="This master is no longer available.")
            return
        payload = self.payload
        payload["master_id"] = str(master.pk)
        payload.pop("date", None)
        payload.pop("slot_iso", None)
        payload.pop("slot_label", None)
        self._commit(payload=payload, state=TelegramBookingSession.STATE_DATE)
        self.show_date_picker()

    def show_date_picker(self, *, info: str | None = None) -> None:
        service = self._selected_service()
        master = self._selected_master()
        now = timezone.localtime()
        today = now.date()
        days = [today + timedelta(days=offset) for offset in range(0, 7)]
        weekend_delta = (5 - today.weekday()) % 7
        weekend_day = today + timedelta(days=weekend_delta)

        rows = [
            [
                InlineKeyboardButton("Today", callback_data=self._cb("day", _date_token(today))),
                InlineKeyboardButton("Tomorrow", callback_data=self._cb("day", _date_token(today + timedelta(days=1)))),
                InlineKeyboardButton("This weekend", callback_data=self._cb("day", _date_token(weekend_day))),
            ]
        ]

        for chunk in _chunk(days, 3):
            row = [InlineKeyboardButton(_format_date_label(day), callback_data=self._cb("day", _date_token(day))) for day in chunk]
            rows.append(row)

        rows.append(
            [
                InlineKeyboardButton("◀ Back", callback_data=self._cb("back", "master")),
                InlineKeyboardButton("✖ Cancel", callback_data=self._cb("cancel")),
            ]
        )
        rows.append([InlineKeyboardButton("🧑‍💼 Talk to manager", callback_data=self._cb("manager"))])

        markup = _inline_markup(rows)
        lines = [
            f"<b>Select date for {escape(service.name)}</b>",
            f"With {escape(_master_display(master, fallback='our team'))}",
        ]
        if info:
            lines.append(info)
        self._commit(state=TelegramBookingSession.STATE_DATE)
        self._send_or_edit("\n".join(lines), markup)

    def select_date(self, token: str) -> None:
        try:
            selected = _parse_date_token(token)
        except ValueError:
            self.show_date_picker(info="Please pick a valid date.")
            return
        payload = self.payload
        payload["date"] = selected.isoformat()
        payload.pop("slot_iso", None)
        payload.pop("slot_label", None)
        self._commit(payload=payload, state=TelegramBookingSession.STATE_TIME)
        self.show_time_picker()

    def show_time_picker(self, *, page: int = 0, info: str | None = None) -> None:
        slots = self._available_slots()
        if not slots:
            self._commit(state=TelegramBookingSession.STATE_TIME)
            self._send_or_edit(
                "No slots remain for this date. Pick a different date or talk to our manager.",
                _inline_markup(
                    [
                        [InlineKeyboardButton("◀ Pick another date", callback_data=self._cb("back", "date"))],
                        [InlineKeyboardButton("🧑‍💼 Talk to manager", callback_data=self._cb("manager"))],
                    ]
                ),
            )
            return

        total_pages = max(1, ceil(len(slots) / self.TIME_PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))
        start = page * self.TIME_PAGE_SIZE
        slice_slots = slots[start : start + self.TIME_PAGE_SIZE]

        rows = []
        for chunk in _chunk(slice_slots, 4):
            row = [InlineKeyboardButton(_format_time_label(slot), callback_data=self._cb("time", slot.isoformat())) for slot in chunk]
            rows.append(row)

        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀ Earlier", callback_data=self._cb("tmpg", str(page - 1))))
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=self._cb("noop")))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Later ▶", callback_data=self._cb("tmpg", str(page + 1))))
        rows.append(nav_row)
        rows.append(
            [
                InlineKeyboardButton("◀ Back", callback_data=self._cb("back", "date")),
                InlineKeyboardButton("✖ Cancel", callback_data=self._cb("cancel")),
            ]
        )
        rows.append([InlineKeyboardButton("🧑‍💼 Talk to manager", callback_data=self._cb("manager"))])

        service = self._selected_service()
        master = self._selected_master()
        date_label = _format_date_label(self._selected_date())
        lines = [
            f"<b>Pick a time on {date_label}</b>",
            f"{escape(service.name)} with {escape(_master_display(master, fallback='our team'))}",
        ]
        if info:
            lines.append(info)
        self._commit(state=TelegramBookingSession.STATE_TIME)
        self._send_or_edit("\n".join(lines), _inline_markup(rows))

    def select_time(self, iso_value: str) -> None:
        slots = {slot.isoformat(): slot for slot in self._available_slots()}
        slot = slots.get(iso_value)
        if not slot:
            self.show_time_picker(info="That slot was just taken. Refreshed the list for you.")
            return
        payload = self.payload
        payload["slot_iso"] = slot.isoformat()
        payload["slot_label"] = _format_time_label(slot)
        self._commit(payload=payload, state=TelegramBookingSession.STATE_CONFIRM)
        self.show_confirmation()

    def show_confirmation(self, *, info: str | None = None) -> None:
        service = self._selected_service()
        master = self._selected_master()
        booking_date = self._selected_date()
        slot_label = self.payload.get("slot_label", "")
        price = service.get_discounted_price() if hasattr(service, "get_discounted_price") else service.base_price
        lines = [
            "<b>Review your booking</b>",
            f"Service: {escape(service.name)}",
            f"Master: {escape(_master_display(master))}",
            f"When: {_format_date_label(booking_date)} at {slot_label}",
            f"Price: CAD {price:.2f}",
        ]
        if info:
            lines.append(info)

        rows = [
            [InlineKeyboardButton("✅ Confirm", callback_data=self._cb("confirm"))],
            [
                InlineKeyboardButton("◀ Back", callback_data=self._cb("back", "time")),
                InlineKeyboardButton("✖ Cancel", callback_data=self._cb("cancel")),
            ],
            [InlineKeyboardButton("🧑‍💼 Talk to manager", callback_data=self._cb("manager"))],
        ]
        self._commit(state=TelegramBookingSession.STATE_CONFIRM)
        self._send_or_edit("\n".join(lines), _inline_markup(rows))

    def confirm(self) -> None:
        slot_iso = self.payload.get("slot_iso")
        if not slot_iso:
            self.show_time_picker(info="Pick a time first.")
            return

        try:
            slot_dt = datetime.fromisoformat(slot_iso)
        except ValueError:
            self.show_time_picker(info="Time selection expired. Please pick again.")
            return

        profile = _ensure_client_profile(self.subscription)
        service = self._selected_service()
        master = self._selected_master()
        cart_item = _BotCartItem(service=service, master=master, start_time=slot_dt)

        assign_count = 0
        try:
            appointment = create_appointment_from_cart_items(profile=profile, items=[cart_item])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram booking failed: %s", exc, exc_info=exc)
            self.show_time_picker(info="Unable to create booking. Please choose another slot.")
            return

        service_forms = list(service.active_forms()) if hasattr(service, "active_forms") else []
        if service_forms:
            assign_count += ensure_assignments(profile=profile, forms=service_forms)
        assign_count += ensure_universal_assignments_for_profile(profile)

        payload = self.payload
        reschedule_item_id = payload.get("reschedule_item_id")
        last = payload.get("last_selection", {})
        last.update({"service_id": str(service.pk), "master_id": str(master.pk)})
        new_payload = {"last_selection": last}

        if reschedule_item_id:
            old_item = (
                AppointmentItem.objects.select_related("appointment")
                .filter(pk=reschedule_item_id, appointment__client=profile)
                .first()
            )
            if old_item:
                record_item_status(old_item, "CANCELLED", note="telegram-reschedule")

        self._commit(payload=new_payload, state=TelegramBookingSession.STATE_IDLE, message_id=None)

        start_local = timezone.localtime(appointment.start_time) if appointment.start_time else None
        details = ["✅ <b>Booking confirmed!</b>"]
        if start_local:
            details.append(f"When: {start_local:%a %d %b, %H:%M}")
        else:
            details.append("When: We'll confirm the start time shortly.")
        details.append(f"Service: {escape(service.name)}")
        details.append(f"Master: {escape(_master_display(master))}")
        if assign_count:
            try:
                forms_link = _public_url(reverse("client-intake-forms"))
            except NoReverseMatch:
                forms_link = _public_url("/accounts/forms/")
            details.append(
                f"We assigned {assign_count} intake form{'s' if assign_count != 1 else ''}. Complete them here: {forms_link}"
            )
        if reschedule_item_id:
            details.append("Your previous slot was freed up automatically.")

        self.bot.send_message(self.subscription.chat_id, "\n".join(details))

    def cancel(self, *, message: str | None = None) -> None:
        self.session.reset()
        self._commit(payload=self.session.payload, state=TelegramBookingSession.STATE_IDLE, message_id=None)
        notice = message or "Booking flow cancelled. Tap 📅 Book to start again."
        self.bot.send_message(self.subscription.chat_id, notice, reply_markup=_main_menu_markup())

    def go_back(self, target: str) -> None:
        if target == "service":
            self.show_service_picker()
        elif target == "master":
            self.show_master_picker()
        elif target == "date":
            self.show_date_picker()
        elif target == "time":
            self.show_time_picker()
        else:
            self.show_service_picker()

    def start_reschedule(self, item: AppointmentItem) -> None:
        payload = self.payload
        payload["service_id"] = str(item.service_id)
        payload["master_id"] = str(item.master_id)
        payload["reschedule_item_id"] = str(item.pk)
        payload.pop("date", None)
        payload.pop("slot_iso", None)
        payload.pop("slot_label", None)
        self._commit(payload=payload, state=TelegramBookingSession.STATE_DATE)
        self.show_date_picker(info="Rescheduling your visit. Pick a new date.")

    def talk_to_manager(self) -> None:
        context = list(self.session.context_log or [])
        selection = self._selection_snapshot()
        admin_lines = ["🧑‍💼 Telegram handoff"]
        admin_lines.append(f"Chat: {self.subscription.chat_id}")
        admin_lines.extend(selection)
        if context:
            admin_lines.append("Recent messages:")
            for entry in context[-6:]:
                role = entry.get("role", "client")
                text = entry.get("text", "")
                admin_lines.append(f"• {role}: {text}")
        self.session.append_context("user", "Requested manager handoff")
        self.session.save(update_fields=["context_log"])
        _send_bulk_message("\n".join(admin_lines), admin_chat_ids())
        self.bot.send_message(
            self.subscription.chat_id,
            "Got it! Our manager will reach out shortly via Telegram or phone.",
        )

    def _selection_snapshot(self) -> list[str]:
        lines: list[str] = []
        service_id = self.payload.get("service_id")
        master_id = self.payload.get("master_id")
        date_label = self.payload.get("date")
        slot_label = self.payload.get("slot_label")
        if service_id:
            service = Service.objects.filter(pk=service_id).first()
            if service:
                lines.append(f"Service: {service.name}")
        if master_id:
            master = MasterProfile.objects.filter(pk=master_id).first()
            if master:
                lines.append(f"Master: {_master_display(master)}")
        if date_label:
            lines.append(f"Date: {date_label}")
        if slot_label:
            lines.append(f"Time: {slot_label}")
        return lines

    def _selected_service(self) -> Service:
        service_id = self.payload.get("service_id")
        if not service_id:
            raise TelegramCommandError("Select a service first.")
        service = Service.objects.filter(pk=service_id, is_active=True).first()
        if not service:
            raise TelegramCommandError("Selected service is not available anymore.")
        return service

    def _selected_master(self) -> MasterProfile:
        master_id = self.payload.get("master_id")
        if not master_id:
            raise TelegramCommandError("Choose a master first.")
        master = MasterProfile.objects.filter(pk=master_id).first()
        if not master:
            raise TelegramCommandError("Selected master is not available anymore.")
        return master

    def _selected_date(self) -> date:
        date_token = self.payload.get("date")
        if not date_token:
            raise TelegramCommandError("Pick a date first.")
        return datetime.fromisoformat(date_token).date()

    def _available_slots(self) -> list[datetime]:
        service = self._selected_service()
        master = self._selected_master()
        selected_date = self._selected_date()
        anchor = timezone.make_aware(datetime.combine(selected_date, time.min), timezone.get_current_timezone())
        slots_map = get_available_slots(service, anchor, master=master)
        return slots_map.get(master.id, [])

    def _send_or_edit(self, text: str, reply_markup: InlineKeyboardMarkup) -> None:
        chat_id = self.subscription.chat_id
        message_id = self.session.active_message_id
        try:
            if message_id:
                self.bot.edit_message_text(
                    text,
                    chat_id,
                    message_id,
                    reply_markup=reply_markup,
                )
                return
        except ApiTelegramException:
            message_id = None

        sent = self.bot.send_message(chat_id, text, reply_markup=reply_markup)
        self._commit(message_id=sent.message_id)

    def _commit(self, *, payload=_SENTINEL, state=_SENTINEL, message_id=_SENTINEL) -> None:
        updates: list[str] = []
        if payload is not _SENTINEL:
            self.session.payload = payload
            updates.append("payload")
        if state is not _SENTINEL:
            self.session.state = state
            updates.append("state")
        if message_id is not _SENTINEL:
            self.session.active_message_id = message_id
            updates.append("active_message_id")
        if updates:
            self.session.save(update_fields=updates)

    def _cb(self, action: str, value: str | None = None) -> str:
        if action == "noop":
            return BOOKING_CALLBACK_PREFIX + "noop"
        token = value or ""
        return f"{BOOKING_CALLBACK_PREFIX}{action}|{token}"


def start_client_booking(
    bot: TeleBot,
    subscription: TelegramChatSubscription,
    *,
    reuse_defaults: bool = True,
    telegram_user=None,
) -> None:
    if telegram_user:
        _ensure_client_profile(subscription, telegram_user)
    flow = ClientBookingFlow(bot, subscription)
    flow.start(reuse_defaults=reuse_defaults)


def handle_booking_callback(bot: TeleBot, callback: CallbackQuery) -> bool:
    data = callback.data or ""
    if not data.startswith(BOOKING_CALLBACK_PREFIX):
        return False

    subscription = TelegramChatSubscription.objects.filter(chat_id=callback.message.chat.id).first()
    if not subscription:
        bot.answer_callback_query(callback.id, text="Please send /start first.", show_alert=True)
        return True

    action, value = _parse_booking_callback(data)
    flow = ClientBookingFlow(bot, subscription)

    if action == "noop":
        bot.answer_callback_query(callback.id)
        return True

    try:
        if action == "svc":
            flow.select_service(value)
        elif action == "svcpg":
            flow.show_service_picker(page=int(value or 0))
        elif action == "mst":
            flow.select_master(value)
        elif action == "mstpg":
            flow.show_master_picker(page=int(value or 0))
        elif action == "day":
            flow.select_date(value)
        elif action == "tmpg":
            flow.show_time_picker(page=int(value or 0))
        elif action == "time":
            flow.select_time(value)
        elif action == "confirm":
            flow.confirm()
        elif action == "cancel":
            flow.cancel()
        elif action == "back":
            flow.go_back(value)
        elif action == "manager":
            flow.talk_to_manager()
        elif action == "resched":
            _begin_reschedule(flow, value)
        elif action == "cancelitem":
            _cancel_item(flow, value)
        else:
            flow.show_service_picker()
    except TelegramCommandError as exc:
        bot.answer_callback_query(callback.id, text=str(exc), show_alert=True)
        return True

    bot.answer_callback_query(callback.id)
    return True


def handle_admin_status_callback(bot: TeleBot, callback: CallbackQuery) -> bool:
    data = callback.data or ""
    if not data.startswith(OPS_CALLBACK_PREFIX):
        return False
    parts = data.split("|")
    if len(parts) < 4 or parts[1] != "status":
        return False
    item_id, code = parts[2], parts[3]

    subscription = TelegramChatSubscription.objects.filter(chat_id=callback.message.chat.id).first()
    if not subscription or not subscription.is_admin_channel:
        bot.answer_callback_query(callback.id, text="Admins only.", show_alert=True)
        return True

    item = AppointmentItem.objects.select_related("service").filter(pk=item_id).first()
    if not item:
        bot.answer_callback_query(callback.id, text="Item already updated.", show_alert=True)
        return True

    result = record_item_status(item, code.upper(), note="telegram-admin")
    bot.answer_callback_query(callback.id, text=f"Set to {result.status.code.title()}.")
    return True


def _parse_booking_callback(data: str) -> tuple[str, str]:
    body = data[len(BOOKING_CALLBACK_PREFIX) :]
    action, _, rest = body.partition("|")
    return action, rest


def _begin_reschedule(flow: ClientBookingFlow, item_id: str) -> None:
    if not item_id:
        return
    profile = _ensure_client_profile(flow.subscription)
    item = (
        AppointmentItem.objects.select_related("service", "master", "appointment")
        .filter(pk=item_id, appointment__client=profile)
        .first()
    )
    if not item:
        flow.bot.send_message(flow.subscription.chat_id, "We could not find that booking anymore.")
        return
    flow.start_reschedule(item)


def _cancel_item(flow: ClientBookingFlow, item_id: str) -> None:
    if not item_id:
        return
    profile = _ensure_client_profile(flow.subscription)
    item = (
        AppointmentItem.objects.select_related("appointment", "service")
        .filter(pk=item_id, appointment__client=profile)
        .first()
    )
    if not item:
        flow.bot.send_message(flow.subscription.chat_id, "Booking already updated.")
        return
    record_item_status(item, "CANCELLED", note="telegram-client")
    flow.bot.send_message(
        flow.subscription.chat_id,
        f"Cancelled {escape(getattr(item.service, 'name', 'service'))} on {item.start_time:%d %b %H:%M}.",
    )


def send_upcoming_bookings(bot: TeleBot, subscription: TelegramChatSubscription, *, limit: int = 3) -> None:
    profile = _ensure_client_profile(subscription)
    now = timezone.now() - timedelta(hours=1)
    items = (
        AppointmentItem.objects.select_related("service", "master", "appointment")
        .filter(appointment__client=profile, appointment__start_time__gte=now)
        .order_by("appointment__start_time")[:limit]
    )
    if not items:
        bot.send_message(subscription.chat_id, "You have no upcoming bookings yet.", reply_markup=_main_menu_markup())
        return

    for item in items:
        start = timezone.localtime(item.start_time)
        master_name = _master_display(getattr(item, "master", None))
        lines = [
            f"<b>{escape(getattr(item.service, 'name', 'Service'))}</b>",
            f"When: {start:%a %d %b, %H:%M}",
            f"With: {escape(master_name or 'Team')}",
        ]
        status = getattr(getattr(item, "status", None), "code", "CONFIRMED")
        lines.append(f"Status: {status.title()}")
        markup = _inline_markup(
            [
                [
                    InlineKeyboardButton("🔄 Reschedule", callback_data=f"{BOOKING_CALLBACK_PREFIX}resched|{item.pk}"),
                    InlineKeyboardButton("🗑 Cancel", callback_data=f"{BOOKING_CALLBACK_PREFIX}cancelitem|{item.pk}"),
                ],
                [InlineKeyboardButton("🧑‍💼 Talk to manager", callback_data=f"{BOOKING_CALLBACK_PREFIX}manager")],
            ]
        )
        bot.send_message(subscription.chat_id, "\n".join(lines), reply_markup=markup)


def send_client_help(bot: TeleBot, subscription: TelegramChatSubscription) -> None:
    text = (
        "Need a hand?\n"
        "• 📅 Book — start a 4-tap wizard: Service → Master → Date → Time.\n"
        "• 🧾 My bookings — review, reschedule or cancel upcoming visits.\n"
        "• 🧑‍💼 Talk to manager anytime for custom requests."
    )
    markup = _inline_markup(
        [[InlineKeyboardButton("🧑‍💼 Talk to manager", callback_data=f"{BOOKING_CALLBACK_PREFIX}manager")]]
    )
    bot.send_message(subscription.chat_id, text, reply_markup=_main_menu_markup())
    bot.send_message(subscription.chat_id, "Need direct assistance?", reply_markup=markup)


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


def _status_action_markup(item_id: str) -> InlineKeyboardMarkup:
    return _inline_markup(
        [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"{OPS_CALLBACK_PREFIX}status|{item_id}|CONFIRMED"),
                InlineKeyboardButton("🟢 Complete", callback_data=f"{OPS_CALLBACK_PREFIX}status|{item_id}|COMPLETED"),
            ],
            [
                InlineKeyboardButton("⚠ No-show", callback_data=f"{OPS_CALLBACK_PREFIX}status|{item_id}|NO_SHOW"),
                InlineKeyboardButton("🗑 Cancel", callback_data=f"{OPS_CALLBACK_PREFIX}status|{item_id}|CANCELLED"),
            ],
        ]
    )


def _send_status_cards(appointment: Appointment, chat_ids: Sequence[int], items: list[AppointmentItem]) -> None:
    if not chat_ids or not items:
        return
    bot = require_bot()
    for chat_id in chat_ids:
        for item in items:
            service_name = getattr(item.service, "name", "Service")
            master = _master_display(getattr(item, "master", None), fallback="Staff")
            start_label = timezone.localtime(item.start_time).strftime("%d %b %H:%M") if item.start_time else "TBD"
            text = (
                f"<b>{escape(service_name)}</b> — {escape(master or 'Staff')}\n"
                f"{escape(start_label)} • Item {escape(str(item.pk))}"
            )
            try:
                bot.send_message(chat_id, text, reply_markup=_status_action_markup(str(item.pk)))
            except ApiTelegramException as exc:  # noqa: PERF203
                logger.warning("Unable to send status actions to %s: %s", chat_id, exc)


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
            master_name = _master_display(getattr(item, "master", None), fallback="Staff")
            service_lines.append(f"• {escape(service_name)} — {escape(master_name)}" )
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
        delivered, _ = _send_bulk_message(text, recipients)
        if delivered:
            _send_status_cards(appointment, delivered, items)
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
        master_name = _master_display(master, fallback="")
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
                Q(items__master__user__user__first_name__icontains=staff_term)
                | Q(items__master__user__user__last_name__icontains=staff_term)
                | Q(items__master__user__user__username__icontains=staff_term)
                | Q(items__master__user__user__email__icontains=staff_term)
                | Q(items__master__profession__icontains=staff_term)
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

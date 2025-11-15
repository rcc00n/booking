"""TeleBot message handlers."""

from __future__ import annotations

import logging
import secrets

from telebot import TeleBot
from telebot.types import CallbackQuery, Message

from .models import TelegramBotSettings, TelegramBookingSession, TelegramChatSubscription
from .services import (
    ClientBookingFlow,
    MAIN_MENU_BOOK,
    MAIN_MENU_BOOKINGS,
    MAIN_MENU_HELP,
    TelegramCommandError,
    append_booking_context,
    append_note_to_appointment,
    describe_payment_status,
    handle_booking_callback,
    handle_admin_status_callback,
    link_subscription_to_profile,
    list_payment_status_choices,
    record_subscription,
    render_appointment_details,
    render_appointment_notes,
    render_management_summary,
    render_outstanding_overview,
    render_schedule_overview,
    render_today_summary,
    send_client_help,
    send_client_menu,
    send_upcoming_bookings,
    start_client_booking,
    update_payment_status_via_bot,
)
from .assistant import StaffAssistant, StaffAssistantError

logger = logging.getLogger(__name__)


def _subscription_for(message: Message) -> TelegramChatSubscription | None:
    return TelegramChatSubscription.objects.filter(chat_id=message.chat.id).first()


def _awaiting_client_search(message: Message) -> bool:
    subscription = _subscription_for(message)
    if not subscription:
        return False
    session = getattr(subscription, "booking_session", None)
    if not session:
        return False
    payload = session.payload or {}
    return session.state == TelegramBookingSession.STATE_CLIENT and bool(payload.get("awaiting_client_query"))


def register_handlers(bot: TeleBot) -> None:
    """Attach command handlers to the given bot instance."""

    def _extract_argument(text: str | None) -> str:
        parts = (text or "").split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    def _safe_int(value: str | None) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _log_command(message: Message, command: str) -> None:
        username = getattr(getattr(message, "from_user", None), "username", "") or "unknown"
        logger.info("Telegram command %s from chat %s (%s)", command, message.chat.id, username)

    def _require_admin(message: Message) -> TelegramChatSubscription | None:
        subscription = record_subscription(message)
        if not subscription.is_admin_channel:
            bot.reply_to(message, "This command is available to admin chats only. Use /subscribe <token> first.")
            return None
        return subscription

    def _require_actor(subscription: TelegramChatSubscription, message: Message) -> TelegramChatSubscription | None:
        if subscription.linked_profile_id:
            return subscription
        bot.reply_to(
            message,
            "Link this chat to a staff profile with /link <work email or username> before modifying data.",
        )
        return None

    @bot.callback_query_handler(func=lambda c: bool(c.data and c.data.startswith("b|")))
    def handle_booking_callbacks(callback: CallbackQuery) -> None:
        handle_booking_callback(bot, callback)

    @bot.callback_query_handler(func=lambda c: bool(c.data and c.data.startswith("ops|")))
    def handle_admin_callbacks(callback: CallbackQuery) -> None:
        handle_admin_status_callback(bot, callback)

    @bot.message_handler(commands=["start", "help"])
    def handle_help(message: Message) -> None:
        _log_command(message, "/help")
        subscription = record_subscription(message)
        send_client_menu(bot, message.chat.id)
        send_client_help(bot, subscription)
        if subscription.is_admin_channel:
            help_lines = [
                "<b>Admin quick guide</b>",
                "",
                "<b>Setup</b>",
                "/subscribe <token> — register this chat and enable alerts.",
                "/link <staff email> — connect this chat to your staff profile (needed for edits).",
                "/unsubscribe — stop notifications.",
                "",
                "<b>Insights</b>",
                "/today — snapshot of today's KPIs.",
                "/summary [today|yesterday|week|YYYY-MM-DD[:YYYY-MM-DD]] [detailed] — operations report.",
                "/schedule [window] [limit] [client:term] [staff:term] [status:code] [payment:name] [notes] — inspect the calendar.",
                "/outstanding [limit] — show unpaid appointments.",
                "",
                "<b>Appointments</b>",
                "/appointment <id> — appointment snapshot.",
                "/paystatus <id> [status|list] — review or update payment status.",
                "/note <id> [text] — view notes or append a new entry.",
                "",
                "<b>AI assistant</b>",
                "/assistant <question> — natural language access to KPIs, schedules, payments, and booking actions.",
            ]
            bot.send_message(message.chat.id, "\n".join(help_lines))
        logger.info("Telegram chat %s connected (admin=%s)", subscription.chat_id, subscription.is_admin_channel)

    @bot.message_handler(func=lambda msg: (msg.text or "").strip() == MAIN_MENU_BOOK)
    def handle_menu_book(message: Message) -> None:
        subscription = record_subscription(message)
        append_booking_context(subscription, "user", message.text or "")
        start_client_booking(bot, subscription, telegram_user=message.from_user)

    @bot.message_handler(func=lambda msg: (msg.text or "").strip() == MAIN_MENU_BOOKINGS)
    def handle_menu_bookings(message: Message) -> None:
        subscription = record_subscription(message)
        append_booking_context(subscription, "user", message.text or "")
        send_upcoming_bookings(bot, subscription)

    @bot.message_handler(func=lambda msg: (msg.text or "").strip() == MAIN_MENU_HELP)
    def handle_menu_help(message: Message) -> None:
        subscription = record_subscription(message)
        append_booking_context(subscription, "user", message.text or "")
        send_client_help(bot, subscription)

    @bot.message_handler(func=_awaiting_client_search)
    def handle_client_search_query(message: Message) -> None:
        subscription = record_subscription(message)
        query = (message.text or "").strip()
        if query:
            append_booking_context(subscription, "user", query)
        flow = ClientBookingFlow(bot, subscription)
        normalized = query.lower()
        if not query or normalized in {"cancel", "stop", "exit"}:
            flow.clear_client_search()
            return
        flow.apply_client_search_query(query)

    @bot.message_handler(commands=["subscribe"])
    def handle_subscribe(message: Message) -> None:
        _log_command(message, "/subscribe")
        text = message.text or ""
        parts = text.split(maxsplit=1)
        provided_token = parts[1].strip() if len(parts) > 1 else ""
        settings_obj = TelegramBotSettings.load()
        subscription = record_subscription(message)

        response = "Subscription updated."
        if provided_token and secrets.compare_digest(provided_token, settings_obj.admin_passphrase):
            if not subscription.is_admin_channel:
                subscription.is_admin_channel = True
                subscription.save(update_fields=["is_admin_channel"])
            response = "Admin alerts enabled."
        elif provided_token:
            response = "Incorrect admin token. You remain a regular subscriber."
        else:
            response = "Subscription refreshed. Provide /subscribe <token> to enable admin alerts."

        bot.send_message(message.chat.id, response)

    @bot.message_handler(commands=["unsubscribe"])
    def handle_unsubscribe(message: Message) -> None:
        _log_command(message, "/unsubscribe")
        updated = TelegramChatSubscription.objects.filter(chat_id=message.chat.id).update(
            is_active=False,
            is_admin_channel=False,
        )
        if updated:
            bot.send_message(message.chat.id, "You will no longer receive notifications here.")
        else:
            bot.send_message(message.chat.id, "This chat was not subscribed.")

    @bot.message_handler(commands=["today"])
    def handle_today(message: Message) -> None:
        _log_command(message, "/today")
        subscription = _subscription_for(message)
        if not subscription or not subscription.is_admin_channel:
            bot.reply_to(message, "Only admin chats can call /today.")
            return

        summary = render_today_summary()
        bot.send_message(message.chat.id, summary)

    @bot.message_handler(commands=["link"])
    def handle_link(message: Message) -> None:
        _log_command(message, "/link")
        subscription = record_subscription(message)
        identifier = _extract_argument(message.text)
        if not identifier:
            bot.reply_to(message, "Usage: /link <staff email or username>.")
            return
        try:
            response = link_subscription_to_profile(subscription, identifier)
        except TelegramCommandError as exc:
            bot.reply_to(message, str(exc))
            return
        bot.reply_to(message, response)

    @bot.message_handler(commands=["summary", "report"])
    def handle_summary(message: Message) -> None:
        _log_command(message, "/summary")
        subscription = _require_admin(message)
        if not subscription:
            return
        raw_args = _extract_argument(message.text)
        tokens = raw_args.split()
        period = None
        detailed = False
        for token in tokens:
            normalized = token.lower()
            if normalized in {"detailed", "--detailed", "full"}:
                detailed = True
                continue
            if normalized in {"brief", "summary"}:
                detailed = False
                continue
            if period is None:
                period = token
        period = period or "today"
        try:
            summary = render_management_summary(period, detailed=detailed)
        except TelegramCommandError as exc:
            bot.reply_to(message, f"Unable to build report: {exc}")
            return
        bot.send_message(message.chat.id, summary)

    @bot.message_handler(commands=["schedule"])
    def handle_schedule(message: Message) -> None:
        _log_command(message, "/schedule")
        subscription = _require_admin(message)
        if not subscription:
            return

        raw_args = _extract_argument(message.text)
        tokens = raw_args.split()
        target = None
        limit_value: int | None = None
        staff_query: str | None = None
        client_query: str | None = None
        status_filter: str | None = None
        payment_filter: str | None = None
        include_notes = False
        loose_terms: list[str] = []

        for token in tokens:
            normalized = token.lower()
            if normalized in {"notes", "--notes"}:
                include_notes = True
                continue
            if normalized.startswith("client:"):
                client_query = token.split(":", 1)[1]
                continue
            if normalized.startswith("staff:"):
                staff_query = token.split(":", 1)[1]
                continue
            if normalized.startswith("status:"):
                status_filter = token.split(":", 1)[1]
                continue
            if normalized.startswith("payment:"):
                payment_filter = token.split(":", 1)[1]
                continue
            if normalized.startswith("limit:"):
                limit_candidate = _safe_int(token.split(":", 1)[1])
                if limit_candidate is None:
                    bot.reply_to(message, "Limit must be a number between 1 and 20.")
                    return
                limit_value = limit_candidate
                continue
            if target is None:
                target = token
                continue
            if limit_value is None:
                parsed_limit = _safe_int(token)
                if parsed_limit is not None:
                    limit_value = parsed_limit
                    continue
            loose_terms.append(token)

        if loose_terms and not client_query:
            client_query = " ".join(loose_terms)

        if limit_value is not None and (limit_value < 1 or limit_value > 20):
            bot.reply_to(message, "Limit must stay between 1 and 20.")
            return

        target = target or "today"

        try:
            overview = render_schedule_overview(
                target,
                limit=limit_value or 5,
                staff_query=staff_query,
                client_query=client_query,
                status_filter=status_filter,
                payment_filter=payment_filter,
                include_notes=include_notes,
            )
        except TelegramCommandError as exc:
            bot.reply_to(message, f"Unable to load schedule: {exc}")
            return
        bot.send_message(message.chat.id, overview)

    @bot.message_handler(commands=["appointment"])
    def handle_appointment_details(message: Message) -> None:
        _log_command(message, "/appointment")
        subscription = _require_admin(message)
        if not subscription:
            return
        appt_id = _extract_argument(message.text)
        if not appt_id:
            bot.reply_to(message, "Usage: /appointment <appointment id>.")
            return
        try:
            details = render_appointment_details(appt_id)
        except TelegramCommandError as exc:
            bot.reply_to(message, str(exc))
            return
        bot.send_message(message.chat.id, details)

    @bot.message_handler(commands=["outstanding", "pending"])
    def handle_outstanding(message: Message) -> None:
        _log_command(message, "/outstanding")
        subscription = _require_admin(message)
        if not subscription:
            return

        raw_arg = _extract_argument(message.text).strip()
        limit_value: int | None = None
        if raw_arg:
            if raw_arg.lower().startswith("limit:"):
                raw_arg = raw_arg.split(":", 1)[1]
            parsed = _safe_int(raw_arg)
            if parsed is None:
                bot.reply_to(message, "Usage: /outstanding [limit].")
                return
            limit_value = parsed
            if limit_value < 1 or limit_value > 20:
                bot.reply_to(message, "Limit must stay between 1 and 20.")
                return

        overview = render_outstanding_overview(limit=limit_value or 5)
        bot.send_message(message.chat.id, overview)

    @bot.message_handler(commands=["paystatus"])
    def handle_payment_status(message: Message) -> None:
        _log_command(message, "/paystatus")
        subscription = _require_admin(message)
        if not subscription:
            return
        args = _extract_argument(message.text)
        tokens = args.split()
        if not tokens:
            bot.reply_to(message, "Usage: /paystatus <appointment id> <status name> or /paystatus list.")
            return

        first = tokens[0].lower()
        if first in {"list", "help"}:
            bot.reply_to(message, list_payment_status_choices())
            return

        appointment_id = tokens[0]
        if len(tokens) == 1:
            try:
                summary = describe_payment_status(appointment_id)
            except TelegramCommandError as exc:
                bot.reply_to(message, str(exc))
                return
            bot.reply_to(message, summary)
            return

        if not _require_actor(subscription, message):
            return

        status_name = " ".join(tokens[1:])
        try:
            response = update_payment_status_via_bot(
                appointment_id,
                status_name,
                actor=subscription.linked_profile,
            )
        except TelegramCommandError as exc:
            bot.reply_to(message, str(exc))
            return
        bot.reply_to(message, response)

    @bot.message_handler(commands=["note", "addnote"])
    def handle_add_note(message: Message) -> None:
        _log_command(message, "/note")
        subscription = _require_admin(message)
        if not subscription:
            return

        args = _extract_argument(message.text)
        parts = args.split(maxsplit=1)
        if not parts or not parts[0]:
            bot.reply_to(message, "Usage: /note <appointment id> <text> or /note <appointment id> to read notes.")
            return

        appt_id = parts[0]
        if len(parts) == 1:
            try:
                payload = render_appointment_notes(appt_id)
            except TelegramCommandError as exc:
                bot.reply_to(message, str(exc))
                return
            bot.reply_to(message, payload)
            return

        if not _require_actor(subscription, message):
            return

        note_text = parts[1]
        try:
            response = append_note_to_appointment(appt_id, note_text, actor=subscription.linked_profile)
        except TelegramCommandError as exc:
            bot.reply_to(message, str(exc))
            return
        bot.reply_to(message, response)

    @bot.message_handler(commands=["assistant", "ai"])
    def handle_ai_assistant(message: Message) -> None:
        _log_command(message, "/assistant")
        subscription = _require_admin(message)
        if not subscription:
            return
        prompt = _extract_argument(message.text)
        if not prompt:
            bot.reply_to(
                message,
                "Usage: /assistant <question>. Example: /assistant Summarize tomorrow's schedule workload.",
            )
            return
        assistant = StaffAssistant(subscription)
        try:
            reply = assistant.answer(prompt)
        except StaffAssistantError as exc:
            bot.reply_to(message, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI assistant failed")
            bot.reply_to(message, "AI assistant failed to process the request. Try again in a moment.")
            return
        bot.send_message(message.chat.id, reply)

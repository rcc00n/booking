"""TeleBot message handlers."""

from __future__ import annotations

import logging
import secrets

from telebot import TeleBot
from telebot.types import Message

from .models import TelegramBotSettings, TelegramChatSubscription
from .services import (
    TelegramCommandError,
    append_note_to_appointment,
    link_subscription_to_profile,
    record_subscription,
    render_appointment_details,
    render_management_summary,
    render_schedule_overview,
    render_today_summary,
    update_payment_status_via_bot,
)

logger = logging.getLogger(__name__)


def _subscription_for(message: Message) -> TelegramChatSubscription | None:
    return TelegramChatSubscription.objects.filter(chat_id=message.chat.id).first()


def register_handlers(bot: TeleBot) -> None:
    """Attach command handlers to the given bot instance."""

    def _extract_argument(text: str | None) -> str:
        parts = (text or "").split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

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

    @bot.message_handler(commands=["start", "help"])
    def handle_help(message: Message) -> None:
        _log_command(message, "/help")
        subscription = record_subscription(message)
        help_text = (
            "Hello! I will push booking and payment alerts for admins.\n\n"
            "Use /subscribe <token> if you were given an admin token to receive alerts.\n"
            "Use /today for the basic daily summary.\n"
            "Use /summary <today|yesterday|week|YYYY-MM-DD> to request reports.\n"
            "Use /schedule <today|tomorrow|next> [limit] to inspect the calendar.\n"
            "Use /appointment <id> for full details.\n"
            "Use /link <email> once to map this chat to a staff profile.\n"
            "After linking you can run /paystatus and /note to update records.\n"
            "Use /unsubscribe to pause all notifications."
        )
        bot.reply_to(message, help_text)
        logger.info("Telegram chat %s connected (admin=%s)", subscription.chat_id, subscription.is_admin_channel)

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
        period = _extract_argument(message.text) or "today"
        try:
            summary = render_management_summary(period)
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

        tokens = (message.text or "").split()
        target = tokens[1] if len(tokens) > 1 else "today"
        limit_token = tokens[2] if len(tokens) > 2 else "5"
        try:
            limit = int(limit_token)
        except ValueError:
            bot.reply_to(message, "Limit must be a number between 1 and 20.")
            return
        if limit < 1 or limit > 20:
            bot.reply_to(message, "Limit must stay between 1 and 20.")
            return

        try:
            overview = render_schedule_overview(target, limit=limit)
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

    @bot.message_handler(commands=["paystatus"])
    def handle_payment_status(message: Message) -> None:
        _log_command(message, "/paystatus")
        subscription = _require_admin(message)
        if not subscription:
            return
        if not _require_actor(subscription, message):
            return

        args = _extract_argument(message.text)
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /paystatus <appointment id> <status name>.")
            return
        appt_id, status_name = parts[0], parts[1]
        try:
            response = update_payment_status_via_bot(appt_id, status_name, actor=subscription.linked_profile)
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
        if not _require_actor(subscription, message):
            return

        args = _extract_argument(message.text)
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Usage: /note <appointment id> <text>.")
            return
        appt_id, note_text = parts[0], parts[1]
        try:
            response = append_note_to_appointment(appt_id, note_text, actor=subscription.linked_profile)
        except TelegramCommandError as exc:
            bot.reply_to(message, str(exc))
            return
        bot.reply_to(message, response)

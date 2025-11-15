"""TeleBot message handlers."""

from __future__ import annotations

import logging
import secrets

from telebot import TeleBot
from telebot.types import Message

from .models import TelegramBotSettings, TelegramChatSubscription
from .services import record_subscription, render_today_summary

logger = logging.getLogger(__name__)


def _subscription_for(message: Message) -> TelegramChatSubscription | None:
    return TelegramChatSubscription.objects.filter(chat_id=message.chat.id).first()


def register_handlers(bot: TeleBot) -> None:
    """Attach command handlers to the given bot instance."""

    @bot.message_handler(commands=["start", "help"])
    def handle_help(message: Message) -> None:
        subscription = record_subscription(message)
        settings_obj = TelegramBotSettings.load()
        help_text = (
            "Hello! I will push booking and payment alerts for admins.\n\n"
            "Use /subscribe <token> if you were given an admin token to receive alerts.\n"
            "Use /today to see today's appointments summary.\n"
            "Use /unsubscribe to pause all notifications."
        )
        bot.reply_to(message, help_text)
        logger.info("Telegram chat %s connected (admin=%s)", subscription.chat_id, subscription.is_admin_channel)

    @bot.message_handler(commands=["subscribe"])
    def handle_subscribe(message: Message) -> None:
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
        subscription = _subscription_for(message)
        if not subscription or not subscription.is_admin_channel:
            bot.reply_to(message, "Only admin chats can call /today.")
            return

        summary = render_today_summary()
        bot.send_message(message.chat.id, summary)

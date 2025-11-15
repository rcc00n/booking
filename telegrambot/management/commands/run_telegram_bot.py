"""Management command to run the Telegram bot long-polling worker."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from telegrambot.handlers import register_handlers
from telegrambot.services import TelegramBotInactiveError, get_bot


class Command(BaseCommand):
    help = "Run the Telegram bot using long polling."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reload-token",
            action="store_true",
            help="Force recreation of the TeleBot instance from the latest settings.",
        )

    def handle(self, *args, **options):
        bot = get_bot(force_reload=options.get("reload_token", False))
        if bot is None:
            raise CommandError("Telegram bot is disabled or token missing. Enable it from admin settings.")

        register_handlers(bot)
        self.stdout.write(self.style.SUCCESS("Telegram bot connected. Listening for updates..."))

        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except TelegramBotInactiveError as exc:  # pragma: no cover - runtime guard
            raise CommandError(str(exc)) from exc
        except KeyboardInterrupt:  # pragma: no cover - manual stop
            self.stdout.write("Telegram bot stopped.")
        except Exception as exc:  # pragma: no cover - crash logging
            raise CommandError(f"Telegram bot crashed: {exc}") from exc

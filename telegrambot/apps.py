from django.apps import AppConfig


class TelegrambotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "telegrambot"
    verbose_name = "Telegram Bot"

    def ready(self) -> None:  # pragma: no cover - import-time side effects
        from . import listeners  # noqa: F401

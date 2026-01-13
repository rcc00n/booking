from django.conf import settings
from django.db import migrations, models


def populate_ai_defaults(apps, schema_editor):
    Settings = apps.get_model("telegrambot", "TelegramBotSettings")
    try:
        obj = Settings.objects.get(pk=1)
    except Settings.DoesNotExist:
        return

    updated = []

    env_api_key = getattr(settings, "OPENAI_API_KEY", "")
    if env_api_key and not obj.ai_openai_api_key:
        obj.ai_openai_api_key = env_api_key
        updated.append("ai_openai_api_key")

    env_model = getattr(settings, "TELEGRAM_AI_MODEL", "")
    if env_model and not obj.ai_model:
        obj.ai_model = env_model
        updated.append("ai_model")

    env_router = getattr(settings, "TELEGRAM_AI_ROUTER_MODEL", "")
    if env_router and not obj.ai_router_model:
        obj.ai_router_model = env_router
        updated.append("ai_router_model")

    env_history = getattr(settings, "TELEGRAM_AI_MAX_HISTORY", None)
    if env_history and not obj.ai_max_history:
        obj.ai_max_history = env_history
        updated.append("ai_max_history")

    env_enabled = getattr(settings, "TELEGRAM_AI_ENABLED", False)
    if env_enabled and not obj.ai_is_enabled:
        obj.ai_is_enabled = True
        updated.append("ai_is_enabled")

    if updated:
        obj.save(update_fields=updated)


class Migration(migrations.Migration):

    dependencies = [
        ("telegrambot", "0005_telegramstaffassistantsession"),
    ]

    operations = [
        migrations.AddField(
            model_name="telegrambotsettings",
            name="ai_is_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Toggle the internal AI assistant for staff Telegram chats.",
            ),
        ),
        migrations.AddField(
            model_name="telegrambotsettings",
            name="ai_max_history",
            field=models.PositiveSmallIntegerField(
                default=8,
                help_text="How many recent exchanges to share with the model (1-20).",
            ),
        ),
        migrations.AddField(
            model_name="telegrambotsettings",
            name="ai_model",
            field=models.CharField(
                blank=True,
                help_text="Model for final answers (e.g. gpt-4o-mini).",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="telegrambotsettings",
            name="ai_openai_api_key",
            field=models.CharField(
                blank=True,
                help_text="OpenAI API key used for the assistant. Stored encrypted at rest.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="telegrambotsettings",
            name="ai_router_model",
            field=models.CharField(
                blank=True,
                help_text="Optional smaller model for intent routing. Leave blank to reuse AI model.",
                max_length=120,
            ),
        ),
        migrations.RunPython(populate_ai_defaults, migrations.RunPython.noop),
    ]

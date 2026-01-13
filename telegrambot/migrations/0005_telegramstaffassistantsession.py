from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("telegrambot", "0004_booking_sessions"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramStaffAssistantSession",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("context_log", models.JSONField(blank=True, default=list)),
                ("last_error", models.TextField(blank=True)),
                ("last_interaction_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "subscription",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assistant_session",
                        to="telegrambot.telegramchatsubscription",
                    ),
                ),
            ],
            options={
                "verbose_name": "Telegram AI assistant session",
                "verbose_name_plural": "Telegram AI assistant sessions",
            },
        ),
    ]

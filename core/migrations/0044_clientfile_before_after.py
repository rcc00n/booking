from django.conf import settings
from django.db import migrations, models
from django.db.utils import ProgrammingError
import django.db.models.deletion


# CHANGED: allow the client file auxiliary fields to be added safely in both
# forward and backward migrations even when the historical tables are missing
# the expected columns (e.g., when rolling tests to very early states).
class SafeAddField(migrations.AddField):
    """
    AddField variant that tolerates the target column already being absent during reverse
    migrations (e.g., in tests that roll back to historical states).
    """

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        try:
            super().database_backwards(app_label, schema_editor, from_state, to_state)
        except ProgrammingError as exc:
            column = getattr(self.field, "column", self.name)
            message = str(exc)
            if column and f'"{column}"' in message and "core_clientfile" in message:
                return
            raise


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_paymentrefund"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="clientfile",
            options={"ordering": ("-uploaded_at", "-id")},
        ),
        SafeAddField(
            model_name="clientfile",
            name="appointment",
            field=models.ForeignKey(
                blank=True,
                help_text="Appointment this file belongs to.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="client_files",
                to="core.appointment",
            ),
        ),
        SafeAddField(
            model_name="clientfile",
            name="kind",
            field=models.CharField(
                choices=[
                    ("before", "Before"),
                    ("after", "After"),
                    ("other", "Other"),
                ],
                default="other",
                help_text="Categorise the file for before/after tracking.",
                max_length=16,
            ),
        ),
        SafeAddField(
            model_name="clientfile",
            name="uploaded_by_user",
            field=models.ForeignKey(
                blank=True,
                help_text="Staff member who uploaded the file.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="uploaded_client_files",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]

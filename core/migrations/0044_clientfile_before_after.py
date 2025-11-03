from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


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
        migrations.AddField(
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
        migrations.AddField(
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
        migrations.AddField(
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
    ]


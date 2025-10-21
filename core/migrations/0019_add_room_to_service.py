from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_service_is_active_alter_payment_receipt_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="room",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="services",
                to="core.masterroom",
            ),
        ),
        migrations.AddIndex(
            model_name="appointmentitem",
            index=models.Index(
                fields=["service", "start_time"],
                name="appt_item_service_start_idx",
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_remove_room_from_masterprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="is_taxable",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text="Charge 5% GST when true.",
            ),
        ),
    ]


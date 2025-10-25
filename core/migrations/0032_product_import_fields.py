from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_appointment_apply_card_processing_fee"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="brand",
            field=models.CharField(blank=True, default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="product",
            name="cost_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Internal cost per unit.",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="measure_type",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Unit type used by the supplier (e.g. ml, g, pack).",
                max_length=64,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="product",
            name="measure_value",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Package size or quantity as provided by the supplier.",
                max_length=64,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="product",
            name="supplier",
            field=models.CharField(blank=True, default="", max_length=120),
            preserve_default=False,
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_productcategory_product_productsale_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="productsale",
            name="appointment",
            field=models.ForeignKey(
                blank=True,
                help_text="Appointment associated with this sale (optional).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="product_sales",
                to="core.appointment",
            ),
        ),
        migrations.AddIndex(
            model_name="productsale",
            index=models.Index(fields=["appointment"], name="product_sale_appt_idx"),
        ),
    ]


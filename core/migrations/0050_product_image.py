from django.db import migrations, models
import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0049_alter_supportdocument_document_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=core.models.product_image_upload_to,
                help_text="Visible to staff in product lists and appointment selection.",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="image_alt_text",
            field=models.CharField(
                max_length=120,
                blank=True,
                help_text="Optional description for the product image; defaults to the product name.",
            ),
        ),
    ]

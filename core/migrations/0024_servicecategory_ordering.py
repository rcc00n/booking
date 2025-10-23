from django.db import migrations, models
from django.db.models import Q


FEATURED_CATEGORY_RANKS = (
    (1, "First"),
    (2, "Second"),
    (3, "Third"),
)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_rename_appt_item_service_start_idx_core_appoin_service_023b69_idx_and_more"),
        ("core", "0018_alter_payment_receipt_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicecategory",
            name="catalog_order",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Lower numbers appear earlier for categories without a featured rank.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="servicecategory",
            name="featured_rank",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=FEATURED_CATEGORY_RANKS,
                help_text="Optional position for highlighting this category first in the catalog.",
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="servicecategory",
            constraint=models.UniqueConstraint(
                condition=Q(featured_rank__isnull=False),
                fields=("featured_rank",),
                name="core_servicecategory_unique_featured_rank",
            ),
        ),
    ]

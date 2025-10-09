from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_userprofile_address"),  # поставь актуальную зависимость
    ]
    operations = [
        migrations.RunSQL(
            "ALTER TABLE core_service DROP COLUMN IF EXISTS extra_time_label;",
            reverse_sql="ALTER TABLE core_service ADD COLUMN extra_time_label varchar(100) NOT NULL DEFAULT '';",
        ),
        migrations.RunSQL(
            "ALTER TABLE core_service DROP COLUMN IF EXISTS raw_extra_time;",
            reverse_sql="ALTER TABLE core_service ADD COLUMN raw_extra_time varchar(100) NOT NULL DEFAULT '';",
        ),
        migrations.RunSQL(
            "ALTER TABLE core_service DROP COLUMN IF EXISTS slug;",
            reverse_sql="ALTER TABLE core_service ADD COLUMN slug varchar(100) NOT NULL DEFAULT '';",
        ),
        migrations.RunSQL(
            "ALTER TABLE core_service DROP COLUMN IF EXISTS external_uid;",
            reverse_sql="ALTER TABLE core_service ADD COLUMN external_uid varchar(100) NOT NULL DEFAULT '';",
        ),
        migrations.RunSQL(
            "ALTER TABLE core_service DROP COLUMN IF EXISTS is_active;",
            reverse_sql="ALTER TABLE core_service ADD COLUMN is_active varchar(100) NOT NULL DEFAULT '';",
        ),
        # Если есть другие легаси-колонки, по аналогии:
        # migrations.RunSQL("ALTER TABLE core_service DROP COLUMN IF EXISTS extra_time_price;", reverse_sql="..."),
    ]
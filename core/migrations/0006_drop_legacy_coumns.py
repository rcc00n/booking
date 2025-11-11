from django.db import migrations


def _vendor_is_postgres(schema_editor) -> bool:
    return schema_editor.connection.vendor == "postgresql"


def drop_extra_time_label(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute("ALTER TABLE core_service DROP COLUMN IF EXISTS extra_time_label;")


def add_extra_time_label(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute(
        "ALTER TABLE core_service ADD COLUMN extra_time_label varchar(100) NOT NULL DEFAULT '';"
    )


def drop_raw_extra_time(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute("ALTER TABLE core_service DROP COLUMN IF EXISTS raw_extra_time;")


def add_raw_extra_time(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute(
        "ALTER TABLE core_service ADD COLUMN raw_extra_time varchar(100) NOT NULL DEFAULT '';"
    )


def drop_slug(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute("ALTER TABLE core_service DROP COLUMN IF EXISTS slug;")


def add_slug(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute(
        "ALTER TABLE core_service ADD COLUMN slug varchar(100) NOT NULL DEFAULT '';"
    )


def drop_external_uid(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute("ALTER TABLE core_service DROP COLUMN IF EXISTS external_uid;")


def add_external_uid(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute(
        "ALTER TABLE core_service ADD COLUMN external_uid varchar(100) NOT NULL DEFAULT '';"
    )


def drop_is_active(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute("ALTER TABLE core_service DROP COLUMN IF EXISTS is_active;")


def add_is_active(apps, schema_editor) -> None:
    if not _vendor_is_postgres(schema_editor):
        return
    schema_editor.execute(
        "ALTER TABLE core_service ADD COLUMN is_active varchar(100) NOT NULL DEFAULT '';"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_userprofile_address"),
    ]
    operations = [
        migrations.RunPython(drop_extra_time_label, add_extra_time_label),
        migrations.RunPython(drop_raw_extra_time, add_raw_extra_time),
        migrations.RunPython(drop_slug, add_slug),
        migrations.RunPython(drop_external_uid, add_external_uid),
        migrations.RunPython(drop_is_active, add_is_active),
        # For additional legacy columns replicate the helper pattern above.
    ]

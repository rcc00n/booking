from django.db import migrations


def ensure_admin_notes_column(apps, schema_editor):
    table = "core_appointment"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, "notes"],
        )
        has_notes = cursor.fetchone()
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, "admin_notes"],
        )
        has_admin = cursor.fetchone()
        if has_admin and not has_notes:
            cursor.execute(f'ALTER TABLE "{table}" RENAME COLUMN "admin_notes" TO "notes";')


def reverse_noop(apps, schema_editor):
    # keep noop on reverse; renaming back risks reintroducing the bug
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0035_merge_20251025_1535"),
    ]

    operations = [
        migrations.RunPython(ensure_admin_notes_column, reverse_noop),
    ]

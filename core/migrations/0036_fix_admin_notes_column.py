from django.db import migrations


def _column_exists(schema_editor, table: str, column: str) -> bool:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute(f"PRAGMA table_info({table});")
            return any(row[1] == column for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, column],
        )
        return cursor.fetchone() is not None


def ensure_admin_notes_column(apps, schema_editor):
    table = "core_appointment"
    has_notes = _column_exists(schema_editor, table, "notes")
    has_admin = _column_exists(schema_editor, table, "admin_notes")
    if has_admin and not has_notes:
        with schema_editor.connection.cursor() as cursor:
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

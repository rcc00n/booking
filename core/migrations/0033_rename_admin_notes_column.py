from django.db import migrations


def _column_exists(schema_editor, table: str, column: str) -> bool:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "sqlite":
            cursor.execute(f"PRAGMA table_info({table});")
            return any(row[1] == column for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, column],
        )
        return cursor.fetchone() is not None


def rename_admin_notes_to_notes(apps, schema_editor):
    table = "core_appointment"
    has_admin = _column_exists(schema_editor, table, "admin_notes")
    has_notes = _column_exists(schema_editor, table, "notes")
    if has_admin and not has_notes:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE "{table}" RENAME COLUMN "admin_notes" TO "notes";')


def rename_notes_to_admin_notes(apps, schema_editor):
    table = "core_appointment"
    has_notes = _column_exists(schema_editor, table, "notes")
    has_admin = _column_exists(schema_editor, table, "admin_notes")
    if has_notes and not has_admin:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE "{table}" RENAME COLUMN "notes" TO "admin_notes";')


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_appointment_notes"),
    ]

    operations = [
        migrations.RunPython(rename_admin_notes_to_notes, rename_notes_to_admin_notes),
    ]

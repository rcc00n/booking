from django.db import migrations


def rename_admin_notes_to_notes(apps, schema_editor):
    table = "core_appointment"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, "admin_notes"],
        )
        has_admin = cursor.fetchone()
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, "notes"],
        )
        has_notes = cursor.fetchone()
        if has_admin and not has_notes:
            cursor.execute(f'ALTER TABLE "{table}" RENAME COLUMN "admin_notes" TO "notes";')


def rename_notes_to_admin_notes(apps, schema_editor):
    table = "core_appointment"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, "notes"],
        )
        has_notes = cursor.fetchone()
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, "admin_notes"],
        )
        has_admin = cursor.fetchone()
        if has_notes and not has_admin:
            cursor.execute(f'ALTER TABLE "{table}" RENAME COLUMN "notes" TO "admin_notes";')


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_appointment_notes"),
    ]

    operations = [
        migrations.RunPython(rename_admin_notes_to_notes, rename_notes_to_admin_notes),
    ]

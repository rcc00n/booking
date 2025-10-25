from django.db import migrations


CONSTRAINT_NAME = "appointmentitem_no_room_overlap"


SQL_CREATE = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = '{constraint}'
        ) THEN
            ALTER TABLE core_appointmentitem
            ADD CONSTRAINT {constraint}
            EXCLUDE USING GIST (
                room_id WITH =,
                tstzrange(start_time, end_time, '[]') WITH &&
            )
            WHERE (room_id IS NOT NULL);
        END IF;
    END$$;
""".format(
    constraint=CONSTRAINT_NAME
)


def create_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")
    schema_editor.execute(SQL_CREATE)


def drop_constraint(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        f"ALTER TABLE core_appointmentitem DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME};"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_room_allocation'),
    ]

    operations = [
        migrations.RunPython(create_constraint, drop_constraint),
    ]

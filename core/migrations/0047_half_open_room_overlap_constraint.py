from django.db import migrations


CONSTRAINT_NAME = "appointmentitem_no_room_overlap"

SQL_TEMPLATE = """
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE core_appointmentitem
DROP CONSTRAINT IF EXISTS {constraint};

ALTER TABLE core_appointmentitem
ADD CONSTRAINT {constraint}
EXCLUDE USING gist (
    room_id WITH =,
    tstzrange(start_time, end_time, '{bounds}') WITH &&
)
WHERE (room_id IS NOT NULL);
"""

FORWARD_SQL = SQL_TEMPLATE.format(constraint=CONSTRAINT_NAME, bounds="[)")
REVERSE_SQL = SQL_TEMPLATE.format(constraint=CONSTRAINT_NAME, bounds="[]")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0046_terms_support_document"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]

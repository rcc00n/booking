from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


def seed_time_off_reasons(apps, schema_editor):
    TimeOffReason = apps.get_model("core", "TimeOffReason")
    MasterAvailability = apps.get_model("core", "MasterAvailability")

    cache = {}

    def ensure_reason(code, label=None):
        normalized = slugify(code or "") or "vacation"
        if normalized in cache:
            return cache[normalized]
        display_name = (label or code or "Vacation").strip() or "Vacation"
        obj, _ = TimeOffReason.objects.get_or_create(
            code=normalized,
            defaults={"name": display_name},
        )
        cache[normalized] = obj
        return obj

    base_reasons = [
        ("vacation", "Vacation"),
        ("lunch", "Lunch"),
        ("break", "Break"),
    ]
    for code, label in base_reasons:
        ensure_reason(code, label)

    for availability in MasterAvailability.objects.all():
        reason_obj = ensure_reason(availability.reason, availability.reason)
        availability.reason_fk = reason_obj
        availability.save(update_fields=["reason_fk"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0047_half_open_room_overlap_constraint"),
    ]

    operations = [
        migrations.CreateModel(
            name="TimeOffReason",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
            options={
                "verbose_name": "Time Off Reason",
                "verbose_name_plural": "Time Off Reasons",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="masteravailability",
            name="reason_fk",
            field=models.ForeignKey(
                help_text="Reason for time off",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.timeoffreason",
            ),
        ),
        migrations.RunPython(seed_time_off_reasons, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="masteravailability",
            name="reason",
        ),
        migrations.RenameField(
            model_name="masteravailability",
            old_name="reason_fk",
            new_name="reason",
        ),
        migrations.AlterField(
            model_name="masteravailability",
            name="reason",
            field=models.ForeignKey(
                help_text="Reason for time off",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="master_availabilities",
                to="core.timeoffreason",
            ),
        ),
    ]

from django.conf import settings
from django.db import migrations, models, transaction
from django.utils import timezone


DEFAULT_ITEM_STATUSES = [
    ("BOOKED", "Booked"),
    ("CONFIRMED", "Confirmed"),
    ("CANCELLED", "Cancelled"),
    ("COMPLETED", "Completed"),
]


STATUS_NAME_TO_CODE = {
    "booked": "BOOKED",
    "pending": "BOOKED",
    "confirmed": "CONFIRMED",
    "cancelled": "CANCELLED",
    "canceled": "CANCELLED",
    "completed": "COMPLETED",
    "finished": "COMPLETED",
    "done": "COMPLETED",
}


def _resolve_item_status(status_by_code, code):
    code = (code or "BOOKED").upper()
    return status_by_code.get(code) or status_by_code.get("BOOKED")


def seed_item_statuses(apps, schema_editor):
    Status = apps.get_model("core", "AppointmentItemStatus")
    for code, name in DEFAULT_ITEM_STATUSES:
        Status.objects.update_or_create(code=code, defaults={"name": name})


def unseed_item_statuses(apps, schema_editor):
    Status = apps.get_model("core", "AppointmentItemStatus")
    codes = [code for code, _ in DEFAULT_ITEM_STATUSES]
    Status.objects.filter(code__in=codes).delete()


def mirror_appointment_statuses(apps, schema_editor):
    Appointment = apps.get_model("core", "Appointment")
    AppointmentItem = apps.get_model("core", "AppointmentItem")
    AppointmentStatusHistory = apps.get_model("core", "AppointmentStatusHistory")
    AppointmentItemStatus = apps.get_model("core", "AppointmentItemStatus")
    AppointmentItemStatusHistory = apps.get_model("core", "AppointmentItemStatusHistory")

    status_by_code = {
        status.code.upper(): status
        for status in AppointmentItemStatus.objects.all()
    }
    fallback_status = _resolve_item_status(status_by_code, "BOOKED")

    now = timezone.now()

    with transaction.atomic():
        for appointment in Appointment.objects.all().iterator():
            item_ids = list(
                AppointmentItem.objects.filter(appointment_id=appointment.pk).values_list("pk", flat=True)
            )
            if not item_ids:
                continue

            latest = (
                AppointmentStatusHistory.objects
                .filter(appointment_id=appointment.pk)
                .select_related("status", "set_by__user")
                .order_by("-set_at", "-id")
                .first()
            )

            if latest and getattr(latest, "status", None):
                legacy_name = (getattr(latest.status, "name", "") or "").strip().lower()
                target_code = STATUS_NAME_TO_CODE.get(legacy_name, "BOOKED")
                user_id = getattr(getattr(latest, "set_by", None), "user_id", None)
                set_at = getattr(latest, "set_at", None) or appointment.created_at or now
            else:
                target_code = "BOOKED"
                user_id = None
                set_at = appointment.created_at or now

            status_obj = _resolve_item_status(status_by_code, target_code) or fallback_status
            status_id = getattr(status_obj, "id", None)

            if status_id is not None:
                AppointmentItem.objects.filter(pk__in=item_ids).update(status_id=status_id)

            for item_id in item_ids:
                history = AppointmentItemStatusHistory.objects.create(
                    item_id=item_id,
                    status_id=status_id,
                    set_by_id=user_id,
                )
                if set_at:
                    AppointmentItemStatusHistory.objects.filter(pk=history.pk).update(set_at=set_at)


def rollback_item_statuses(apps, schema_editor):
    AppointmentItem = apps.get_model("core", "AppointmentItem")
    AppointmentItemStatusHistory = apps.get_model("core", "AppointmentItemStatusHistory")
    AppointmentItem.objects.update(status_id=None)
    AppointmentItemStatusHistory.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_alter_clientsource_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    atomic = False

    operations = [
        migrations.CreateModel(
            name="AppointmentItemStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=40)),
                ("code", models.CharField(max_length=32, unique=True)),
            ],
            options={
                "ordering": ["name", "id"],
                "verbose_name": "Appointment item status",
                "verbose_name_plural": "Appointment item statuses",
            },
        ),
        migrations.CreateModel(
            name="AppointmentItemStatusHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("set_at", models.DateTimeField(auto_now_add=True)),
                ("note", models.TextField(blank=True, null=True)),
                ("item", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="status_history", to="core.appointmentitem")),
                ("set_by", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="appointment_item_status_actions", to=settings.AUTH_USER_MODEL)),
                ("status", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="history", to="core.appointmentitemstatus")),
            ],
            options={
                "ordering": ["set_at", "id"],
                "verbose_name": "Appointment item status history",
                "verbose_name_plural": "Appointment item status history",
            },
        ),
        migrations.AddField(
            model_name="appointmentitem",
            name="status",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.PROTECT, related_name="items", to="core.appointmentitemstatus"),
        ),
        migrations.RunPython(seed_item_statuses, reverse_code=unseed_item_statuses),
        migrations.RunPython(mirror_appointment_statuses, reverse_code=rollback_item_statuses),
    ]

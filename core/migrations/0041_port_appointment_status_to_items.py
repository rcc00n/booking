from __future__ import annotations

from django.db import migrations
from django.utils import timezone


DEFAULT_ITEM_STATUSES = [
    ("BOOKED", "Booked"),
    ("CONFIRMED", "Confirmed"),
    ("CANCELLED", "Cancelled"),
    ("COMPLETED", "Completed"),
]

LEGACY_NAME_TO_CODE = {
    "booked": "BOOKED",
    "pending": "BOOKED",
    "scheduled": "BOOKED",
    "confirmed": "CONFIRMED",
    "cancelled": "CANCELLED",
    "canceled": "CANCELLED",
    "completed": "COMPLETED",
    "finished": "COMPLETED",
    "done": "COMPLETED",
}

MIGRATION_NOTE = "seed-from-appointment-status"


def _resolve_status_code(status_name: str | None, available_codes: set[str]) -> str:
    if not status_name:
        return "BOOKED"
    normalized = (status_name or "").strip().lower()
    if normalized in LEGACY_NAME_TO_CODE:
        return LEGACY_NAME_TO_CODE[normalized]
    uppercase = (status_name or "").strip().upper()
    if uppercase in available_codes:
        return uppercase
    return "BOOKED"


def forwards(apps, schema_editor):
    Appointment = apps.get_model("core", "Appointment")
    AppointmentItem = apps.get_model("core", "AppointmentItem")
    AppointmentStatusHistory = apps.get_model("core", "AppointmentStatusHistory")
    ItemStatus = apps.get_model("core", "AppointmentItemStatus")
    ItemStatusHistory = apps.get_model("core", "AppointmentItemStatusHistory")

    # Ensure the canonical item statuses exist and stay active.
    status_by_code = {}
    for code, name in DEFAULT_ITEM_STATUSES:
        status_obj, _ = ItemStatus.objects.update_or_create(
            code=code,
            defaults={"name": name, "is_active": True},
        )
        status_by_code[code] = status_obj

    available_codes = set(status_by_code)

    default_timestamp = timezone.now()

    for appointment in Appointment.objects.iterator():
        latest_status = (
            AppointmentStatusHistory.objects.filter(appointment_id=appointment.pk)
            .select_related("status", "set_by__user")
            .order_by("-set_at", "-id")
            .first()
        )

        if latest_status and getattr(latest_status, "status", None):
            legacy_name = getattr(latest_status.status, "name", "")
            target_code = _resolve_status_code(legacy_name, available_codes)
            timestamp = latest_status.set_at or getattr(appointment, "created_at", None) or default_timestamp
            set_by_profile = getattr(latest_status, "set_by", None)
            set_by_user_id = getattr(set_by_profile, "user_id", None)
        else:
            target_code = "BOOKED"
            timestamp = getattr(appointment, "created_at", None) or default_timestamp
            set_by_user_id = None

        status_obj = status_by_code.get(target_code) or status_by_code["BOOKED"]

        item_ids = list(
            AppointmentItem.objects.filter(appointment_id=appointment.pk).values_list("pk", flat=True)
        )
        if not item_ids:
            continue

        # Update the denormalised current status pointer.
        AppointmentItem.objects.filter(pk__in=item_ids).exclude(status_id=status_obj.id).update(
            status_id=status_obj.id
        )

        # Ensure each item has a terminal history entry (idempotently).
        for item_id in item_ids:
            flagged = (
                ItemStatusHistory.objects.filter(item_id=item_id, note=MIGRATION_NOTE)
                .order_by("-set_at", "-id")
                .first()
            )
            if flagged:
                updates = {}
                if flagged.status_id != status_obj.id:
                    updates["status_id"] = status_obj.id
                if flagged.set_at != timestamp:
                    updates["set_at"] = timestamp
                if flagged.set_by_id != set_by_user_id:
                    updates["set_by_id"] = set_by_user_id
                if updates:
                    ItemStatusHistory.objects.filter(pk=flagged.pk).update(**updates)
                continue

            latest_item_history = (
                ItemStatusHistory.objects.filter(item_id=item_id)
                .order_by("-set_at", "-id")
                .first()
            )

            if (
                latest_item_history
                and latest_item_history.status_id == status_obj.id
                and latest_item_history.set_at == timestamp
            ):
                # No need to create a duplicate history record.
                continue

            ItemStatusHistory.objects.create(
                item_id=item_id,
                status_id=status_obj.id,
                set_at=timestamp,
                set_by_id=set_by_user_id,
                note=MIGRATION_NOTE,
            )


def backwards(apps, schema_editor):
    ItemStatusHistory = apps.get_model("core", "AppointmentItemStatusHistory")
    AppointmentItem = apps.get_model("core", "AppointmentItem")

    flagged_entries = list(
        ItemStatusHistory.objects.filter(note=MIGRATION_NOTE).values_list("item_id", flat=True)
    )
    if not flagged_entries:
        return

    ItemStatusHistory.objects.filter(note=MIGRATION_NOTE).delete()

    unique_item_ids = set(flagged_entries)
    for item_id in unique_item_ids:
        latest = (
            ItemStatusHistory.objects.filter(item_id=item_id)
            .order_by("-set_at", "-id")
            .first()
        )
        if latest:
            AppointmentItem.objects.filter(pk=item_id).update(status_id=latest.status_id)
        else:
            AppointmentItem.objects.filter(pk=item_id).update(status_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0040_alter_appointmentitemstatushistory_options_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]


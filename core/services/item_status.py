from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from core.models import (
    AppointmentItem,
    AppointmentItemStatus,
    AppointmentItemStatusHistory,
)

STATUS_LABELS = {
    "BOOKED": "Booked",
    "CONFIRMED": "Confirmed",
    "CANCELLED": "Cancelled",
    "COMPLETED": "Completed",
}

INITIAL_NOTE = "initial-status"
ADMIN_INITIAL_NOTE = "admin-initial"
EMAIL_CONFIRM_NOTE = "email-confirmed"


@dataclass(frozen=True)
class ItemStatusResult:
    status: AppointmentItemStatus
    history_created: bool


def _normalize_code(code: Optional[str]) -> str:
    return (code or "BOOKED").upper()


def ensure_item_status(code: str) -> AppointmentItemStatus:
    normalized = _normalize_code(code)
    defaults = {
        "name": STATUS_LABELS.get(normalized, normalized.title()),
        "is_active": True,
    }
    status, created = AppointmentItemStatus.objects.get_or_create(
        code=normalized,
        defaults=defaults,
    )
    updates = {}
    if defaults["name"] and status.name != defaults["name"]:
        updates["name"] = defaults["name"]
    if not status.is_active:
        updates["is_active"] = True
    if updates:
        for field, value in updates.items():
            setattr(status, field, value)
        status.save(update_fields=list(updates))
    return status


def record_item_status(
    item: AppointmentItem,
    code: str,
    *,
    timestamp=None,
    set_by_user_id: Optional[int] = None,
    note: Optional[str] = None,
) -> ItemStatusResult:
    status = ensure_item_status(code)
    timestamp = timestamp or timezone.now()

    with transaction.atomic():
        if item.status_id != status.id:
            AppointmentItem.objects.filter(pk=item.pk).update(status_id=status.id)
            item.status = status

        history_qs = AppointmentItemStatusHistory.objects.filter(item_id=item.pk)
        if note:
            existing = (
                history_qs.filter(note=note)
                .order_by("-set_at", "-id")
                .first()
            )
            if existing:
                updates = {}
                if existing.status_id != status.id:
                    updates["status_id"] = status.id
                if existing.set_at != timestamp:
                    updates["set_at"] = timestamp
                if existing.set_by_id != set_by_user_id:
                    updates["set_by_id"] = set_by_user_id
                if updates:
                    history_qs.filter(pk=existing.pk).update(**updates)
                return ItemStatusResult(status=status, history_created=False)

        AppointmentItemStatusHistory.objects.create(
            item_id=item.pk,
            status_id=status.id,
            set_at=timestamp,
            set_by_id=set_by_user_id,
            note=note,
        )
        return ItemStatusResult(status=status, history_created=True)


def ensure_initial_status(
    item: AppointmentItem,
    code: str,
    *,
    timestamp=None,
    set_by_user_id: Optional[int] = None,
    note: Optional[str] = None,
) -> ItemStatusResult:
    effective_note = note or INITIAL_NOTE
    return record_item_status(
        item,
        code,
        timestamp=timestamp,
        set_by_user_id=set_by_user_id,
        note=effective_note,
    )


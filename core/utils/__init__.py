from __future__ import annotations

from datetime import datetime, timedelta  # CHANGED: include timedelta for fallback duration calculations
from typing import TYPE_CHECKING

from django.apps import apps
from django.db.models import OuterRef, Q, Subquery

if TYPE_CHECKING:
    from core.models import MasterRoom, Service

__all__ = ["time_overlaps_q", "pick_free_room"]


def _appointment_item_model():
    return apps.get_model("core", "AppointmentItem")


def time_overlaps_q(start: datetime, end: datetime) -> Q:
    """
    Build an overlap predicate for AppointmentItem intervals.
    """
    return Q(start_time__lt=end) & Q(end_time__gt=start)


def pick_free_room(service: "Service", start: datetime, end: datetime) -> "MasterRoom | None":
    """
    Return the first allowed room without conflicting appointments in [start, end).
    Cancelled appointments are ignored to stay consistent with model validation.
    """
    if start is None or end is None:
        return None

    rooms = list(service.allowed_rooms.order_by("pk"))
    if not rooms:
        return None

    AppointmentItem = _appointment_item_model()
    try:
        AppointmentStatusHistory = apps.get_model("core", "AppointmentStatusHistory")
    except LookupError:
        AppointmentStatusHistory = None
    latest_appt_status_sq = None
    if AppointmentStatusHistory is not None:
        latest_appt_status_sq = (
            AppointmentStatusHistory.objects.filter(appointment_id=OuterRef("appointment_id"))
            .order_by("-set_at", "-id")
            .values("status__name")[:1]
        )

    active_status_q = Q(current_status_code__isnull=True) | ~Q(current_status_code__iexact="CANCELLED")  # CHANGED: keep items without status history active

    for room in rooms:
        qs = (
            AppointmentItem.objects.with_current_status()
            .filter(room=room)
            .filter(time_overlaps_q(start, end))
        )
        if latest_appt_status_sq is not None:
            qs = qs.annotate(_latest_appt_status=Subquery(latest_appt_status_sq)).exclude(
                _latest_appt_status__iexact="Cancelled"
            )
        qs = qs.filter(active_status_q)

        has_conflict = False
        for other in qs.select_related("service", "appointment"):
            if hasattr(other, "validation_enabled") and not getattr(other, "validation_enabled", True):
                continue
            other_start = getattr(other, "start_time", None)
            if not other_start:
                continue
            other_end = getattr(other, "end_time", None)
            if other_end is None:
                duration = getattr(other, "duration_min", None)
                if duration is None:
                    duration = getattr(getattr(other, "service", None), "duration_min", 0) or 0
                    extra = getattr(getattr(other, "service", None), "extra_time_min", 0) or 0
                    duration = int(duration) + int(extra)
                other_end = other_start + timedelta(minutes=int(duration or 0))
            if start < other_end and end > other_start:
                has_conflict = True
                break

        if not has_conflict:
            return room
    return None

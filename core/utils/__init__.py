from __future__ import annotations

from datetime import datetime
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

    for room in rooms:
        qs = AppointmentItem.objects.with_current_status().filter(room=room).filter(time_overlaps_q(start, end))
        if latest_appt_status_sq is not None:
            qs = qs.annotate(_latest_appt_status=Subquery(latest_appt_status_sq)).exclude(
                _latest_appt_status__iexact="Cancelled"
            )
        qs = qs.exclude(current_status_code__iexact="CANCELLED")
        if not qs.exists():
            return room
    return None

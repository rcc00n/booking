from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.apps import apps
from django.db.models import Q

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
    """
    if start is None or end is None:
        return None

    rooms = list(service.allowed_rooms.order_by("pk"))
    if not rooms:
        return None

    AppointmentItem = _appointment_item_model()
    for room in rooms:
        overlap_exists = AppointmentItem.objects.filter(room=room).filter(time_overlaps_q(start, end)).exists()
        if not overlap_exists:
            return room
    return None

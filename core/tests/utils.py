from __future__ import annotations

from core.models import MasterRoom, Service

__all__ = ["assign_service_room"]


def assign_service_room(service: Service, room_name: str | None = None) -> MasterRoom:
    """
    Ensure the given service is linked to at least one allowed room for tests.
    """
    base_label = (room_name or f"Room {service.pk}").strip() or "Room"
    label = _unique_room_label(base_label)
    room = MasterRoom.objects.create(room=label)
    service.allowed_rooms.add(room)
    return room


def _unique_room_label(base_label: str) -> str:
    max_len = MasterRoom._meta.get_field("room").max_length or 20

    def truncate(value: str, suffix: str = "") -> str:
        available = max_len - len(suffix)
        if available <= 0:
            # Fallback in pathological cases; keep suffix only trimmed to max_len
            return suffix[-max_len:]
        return value[:available] + suffix

    candidate = truncate(base_label)
    if not MasterRoom.objects.filter(room=candidate).exists():
        return candidate

    counter = 1
    while True:
        suffix = f"-{counter}"
        candidate = truncate(base_label, suffix)
        if not MasterRoom.objects.filter(room=candidate).exists():
            return candidate
        counter += 1

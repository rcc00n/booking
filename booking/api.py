"""Minimal REST-style API endpoints used by the Telegram bot/WebApp."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as datetime_time
from typing import Sequence
from uuid import uuid4

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AppointmentItem, MasterProfile, Service, UserProfile
from core.services.booking import create_appointment_from_cart_items, get_available_slots
from core.services.intake_assignments import ensure_assignments, ensure_universal_assignments_for_profile
from core.services.item_status import record_item_status


def _ensure_aware(dt: datetime) -> datetime:
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


class AvailabilityQuerySerializer(serializers.Serializer):
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.filter(is_active=True))
    date = serializers.DateField()
    master = serializers.PrimaryKeyRelatedField(queryset=MasterProfile.objects.all(), allow_null=True, required=False)
    step = serializers.IntegerField(min_value=5, max_value=120, required=False, default=15)


class AppointmentItemSerializer(serializers.Serializer):
    service = serializers.PrimaryKeyRelatedField(queryset=Service.objects.filter(is_active=True))
    master = serializers.PrimaryKeyRelatedField(queryset=MasterProfile.objects.all())
    start = serializers.DateTimeField()


class AppointmentCreateSerializer(serializers.Serializer):
    client = serializers.PrimaryKeyRelatedField(queryset=UserProfile.objects.all())
    items = AppointmentItemSerializer(many=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class AppointmentItemStatusSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    note = serializers.CharField(required=False, allow_blank=True)


@dataclass
class _CartItem:
    service: Service
    master: MasterProfile
    start_time: datetime
    pk: str = field(default_factory=lambda: str(uuid4()))


class AvailabilityView(APIView):
    """Expose get_available_slots via HTTP for inline keyboards/web apps."""

    def get(self, request):
        serializer = AvailabilityQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        service: Service = serializer.validated_data["service"]
        target_date = serializer.validated_data["date"]
        master: MasterProfile | None = serializer.validated_data.get("master")
        step = serializer.validated_data.get("step", 15)

        anchor = timezone.make_aware(
            datetime.combine(target_date, datetime_time.min),
            timezone.get_current_timezone(),
        )
        slots_map = get_available_slots(service, anchor, master=master, step_minutes=step)

        slot_list: list[str] = []
        if master:
            for dt in slots_map.get(master.id, []):
                slot_list.append(dt.isoformat())
        else:
            for entries in slots_map.values():
                slot_list.extend(dt.isoformat() for dt in entries)

        return Response({
            "service": str(service.pk),
            "master": str(master.pk) if master else None,
            "slots": slot_list,
            "count": len(slot_list),
        })


class AppointmentCreateView(APIView):
    """Create an appointment using the same logic as the main checkout."""

    serializer_class = AppointmentCreateSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile: UserProfile = serializer.validated_data["client"]
        items_payload: Sequence[dict] = serializer.validated_data["items"]
        notes: str = serializer.validated_data.get("notes", "") or ""

        cart_items: list[_CartItem] = []
        for payload in items_payload:
            start: datetime = payload["start"]
            cart_items.append(
                _CartItem(
                    service=payload["service"],
                    master=payload["master"],
                    start_time=_ensure_aware(start),
                )
            )

        try:
            appointment = create_appointment_from_cart_items(profile=profile, items=cart_items)
        except Exception as exc:  # noqa: BLE001 - bubble up readable message
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if notes:
            appointment.notes = (appointment.notes or "").strip() + f"\n{notes}" if appointment.notes else notes
            appointment.save(update_fields=["notes"])

        service_forms: list = []
        for entry in items_payload:
            service: Service = entry["service"]
            service_forms.extend(service.active_forms())

        if service_forms:
            ensure_assignments(profile=profile, forms=service_forms)
        ensure_universal_assignments_for_profile(profile)

        appointment.refresh_from_db()
        appointment_items = list(
            appointment.items.select_related("service", "master", "status").order_by("start_time")
        )
        payload = {
            "appointment": str(appointment.pk),
            "start": appointment.start_time.isoformat() if appointment.start_time else None,
            "items": [
                {
                    "id": str(item.pk),
                    "service": getattr(item.service, "name", ""),
                    "master": getattr(item.master, "display_name", ""),
                    "start": item.start_time.isoformat() if item.start_time else None,
                    "status": getattr(getattr(item, "status", None), "code", ""),
                }
                for item in appointment_items
            ],
        }
        return Response(payload, status=status.HTTP_201_CREATED)


class AppointmentItemStatusView(APIView):
    """Wrap record_item_status for Telegram inline actions."""

    serializer_class = AppointmentItemStatusSerializer

    def post(self, request, item_id: str):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        item = AppointmentItem.objects.select_related("status").filter(pk=item_id).first()
        if not item:
            return Response({"error": "Appointment item not found."}, status=status.HTTP_404_NOT_FOUND)

        code = serializer.validated_data["code"].upper()
        note = serializer.validated_data.get("note") or "telegram-api"
        user_id = request.user.id if request.user.is_authenticated else None

        result = record_item_status(item, code, set_by_user_id=user_id, note=note)

        return Response(
            {
                "item": str(item.pk),
                "status": result.status.code,
                "history_created": result.history_created,
            }
        )

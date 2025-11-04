from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentItem,
    AppointmentItemStatus,
    AppointmentItemStatusHistory,
    MasterProfile,
    MasterRoom,
    PaymentStatus,
    Service,
    ServiceMaster,
    UserProfile,
)
from core.services.item_status import (
    INITIAL_NOTE,
    STATUS_LABELS,
    ItemStatusResult,
    _normalize_code,
    ensure_initial_status,
    ensure_item_status,
    record_item_status,
)


class ServiceItemStatusUnitTests(TestCase):
    def create_appointment_item(self) -> AppointmentItem:
        """Create a fully wired appointment item ready for status transitions."""
        user_model = get_user_model()

        client_user = user_model.objects.create_user(username="client-item", password="test123")
        client_profile = UserProfile.objects.create(user=client_user)

        master_user = user_model.objects.create_user(username="master-item", password="test123")
        master_profile_user = UserProfile.objects.create(user=master_user)
        master_profile = MasterProfile.objects.create(user=master_profile_user)

        payment_status = PaymentStatus.objects.create(name="Not Paid")

        service = Service.objects.create(
            name="Deep Tissue Massage",
            base_price=Decimal("120.00"),
            duration_min=60,
        )
        room = MasterRoom.objects.create(room="Therapy 1")
        service.allowed_rooms.add(room)
        ServiceMaster.objects.create(service=service, master=master_profile)

        appointment = Appointment.objects.create(
            client=client_profile,
            payment_status=payment_status,
            start_time=timezone.now(),
        )

        item = AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=master_profile,
            start_time=timezone.now(),
            unit_price=Decimal("120.00"),
        )
        return item

    def test_normalize_code_handles_variants(self) -> None:
        cases = [
            ("booked", "BOOKED"),
            ("CoMpleted", "COMPLETED"),
            (None, "BOOKED"),
            ("", "BOOKED"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(_normalize_code(value), expected)

    def test_ensure_item_status_creates_with_defaults(self) -> None:
        status = ensure_item_status("confirmed")

        self.assertIsInstance(status, AppointmentItemStatus)
        self.assertEqual(status.code, "CONFIRMED")
        self.assertEqual(status.name, STATUS_LABELS["CONFIRMED"])
        self.assertTrue(status.is_active)

    def test_ensure_item_status_updates_existing(self) -> None:
        status, _ = AppointmentItemStatus.objects.update_or_create(
            code="BOOKED",
            defaults={"name": "Old Label", "is_active": False},
        )

        updated = ensure_item_status("BOOKED")

        status.refresh_from_db()
        self.assertEqual(updated.pk, status.pk)
        self.assertEqual(status.name, STATUS_LABELS["BOOKED"])
        self.assertTrue(status.is_active)

    def test_record_item_status_creates_history_entry(self) -> None:
        appointment_item = self.create_appointment_item()
        AppointmentItemStatusHistory.objects.filter(item=appointment_item).delete()
        AppointmentItem.objects.filter(pk=appointment_item.pk).update(status=None)
        appointment_item.refresh_from_db()

        result = record_item_status(appointment_item, "confirmed")

        appointment_item.refresh_from_db()
        history = AppointmentItemStatusHistory.objects.filter(item=appointment_item)
        self.assertEqual(result, ItemStatusResult(status=appointment_item.status, history_created=True))
        self.assertEqual(history.count(), 1)
        self.assertIsNone(history.first().note)

    def test_record_item_status_updates_existing_history_for_note(self) -> None:
        appointment_item = self.create_appointment_item()
        AppointmentItemStatusHistory.objects.filter(item=appointment_item).delete()
        AppointmentItem.objects.filter(pk=appointment_item.pk).update(status=None)
        appointment_item.refresh_from_db()

        first_timestamp = timezone.now()
        second_timestamp = first_timestamp + timedelta(minutes=5)

        initial = record_item_status(
            appointment_item,
            "cancelled",
            timestamp=first_timestamp,
            set_by_user_id=None,
            note="manual-update",
        )
        self.assertTrue(initial.history_created)

        user_model = get_user_model()
        staff_user = user_model.objects.create_user(username="staff-history", password="test123")
        UserProfile.objects.create(user=staff_user)

        updated = record_item_status(
            appointment_item,
            "cancelled",
            timestamp=second_timestamp,
            set_by_user_id=staff_user.pk,
            note="manual-update",
        )

        history = AppointmentItemStatusHistory.objects.filter(item=appointment_item)
        self.assertFalse(updated.history_created)
        self.assertEqual(history.count(), 1)
        entry = history.first()
        self.assertEqual(entry.status.code, "CANCELLED")
        self.assertEqual(entry.set_by_id, staff_user.pk)
        self.assertEqual(entry.set_at, second_timestamp)

    def test_ensure_initial_status_uses_default_note(self) -> None:
        appointment_item = self.create_appointment_item()
        AppointmentItemStatusHistory.objects.filter(item=appointment_item).delete()
        AppointmentItem.objects.filter(pk=appointment_item.pk).update(status=None)
        appointment_item.refresh_from_db()

        result = ensure_initial_status(appointment_item, "booked")

        history = AppointmentItemStatusHistory.objects.filter(item=appointment_item)
        self.assertTrue(result.history_created)
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().note, INITIAL_NOTE)

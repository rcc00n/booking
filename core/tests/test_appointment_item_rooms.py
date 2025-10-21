from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentItem,
    MasterProfile,
    MasterRoom,
    Service,
    UserProfile,
)


class AppointmentItemRoomConflictTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.client_user = user_model.objects.create_user(
            username="client",
            email="client@example.com",
            password="testpass123",
        )
        self.client_profile = UserProfile.objects.create(user=self.client_user, phone="+15005550000")

        self.master1 = self._make_master(user_model, "master1", "Alice")
        self.master2 = self._make_master(user_model, "master2", "Brenda")

        self.room_a = MasterRoom.objects.create(room="Room A")
        self.room_b = MasterRoom.objects.create(room="Room B")

        self.service_room_a_primary = Service.objects.create(
            name="Facial A1",
            description="Primary room A service",
            base_price="100.00",
            duration_min=60,
            extra_time_min=0,
            room=self.room_a,
        )
        self.service_room_a_secondary = Service.objects.create(
            name="Facial A2",
            description="Secondary room A service",
            base_price="110.00",
            duration_min=45,
            extra_time_min=0,
            room=self.room_a,
        )
        self.service_room_b = Service.objects.create(
            name="Massage B",
            description="Room B service",
            base_price="90.00",
            duration_min=60,
            extra_time_min=0,
            room=self.room_b,
        )
        self.service_no_room = Service.objects.create(
            name="Consultation",
            description="No room assigned",
            base_price="50.00",
            duration_min=30,
            extra_time_min=0,
            room=None,
        )

        self.appointment_one = Appointment.objects.create(
            client=self.client_profile,
            start_time=timezone.now(),
        )
        self.appointment_two = Appointment.objects.create(
            client=self.client_profile,
            start_time=timezone.now() + timedelta(hours=1),
        )

        base_start = timezone.now().replace(minute=0, second=0, microsecond=0)
        self.existing_item = AppointmentItem.objects.create(
            appointment=self.appointment_one,
            service=self.service_room_a_primary,
            master=self.master1,
            start_time=base_start,
        )
        self.base_start = base_start

    @staticmethod
    def _make_master(user_model, username, first_name):
        user = user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
            first_name=first_name,
            last_name="Master",
        )
        profile = UserProfile.objects.create(user=user, phone=f"+1500555{username[-1]}001")
        return MasterProfile.objects.create(user=profile, profession="Stylist")

    def test_overlap_same_room_raises_error(self):
        overlapping_item = AppointmentItem(
            appointment=self.appointment_two,
            service=self.service_room_a_secondary,
            master=self.master2,
            start_time=self.base_start + timedelta(minutes=15),
        )

        with self.assertRaises(ValidationError) as ctx:
            overlapping_item.clean()

        message = "This room is currently used by another service for the selected time."
        self.assertIn(message, ctx.exception.message_dict["start_time"])

    def test_overlap_different_room_passes(self):
        overlapping_item = AppointmentItem(
            appointment=self.appointment_two,
            service=self.service_room_b,
            master=self.master2,
            start_time=self.base_start + timedelta(minutes=15),
        )

        # Should not raise
        overlapping_item.clean()

    def test_overlap_when_new_item_has_no_room_passes(self):
        overlapping_item = AppointmentItem(
            appointment=self.appointment_two,
            service=self.service_no_room,
            master=self.master2,
            start_time=self.base_start + timedelta(minutes=15),
        )

        overlapping_item.clean()

    def test_overlap_when_existing_item_has_no_room_is_ignored(self):
        # Remove room from existing item service
        self.service_room_a_primary.room = None
        self.service_room_a_primary.save(update_fields=["room"])
        self.existing_item.refresh_from_db()

        overlapping_item = AppointmentItem(
            appointment=self.appointment_two,
            service=self.service_room_a_secondary,
            master=self.master2,
            start_time=self.base_start + timedelta(minutes=15),
        )

        overlapping_item.clean()

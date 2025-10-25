from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentItem,
    MasterProfile,
    MasterRoom,
    Service,
    UserProfile,
)


class RoomAllocationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        self.user_model = get_user_model()
        self.client_profile = self._make_client("room-client")

    def _make_client(self, username: str) -> UserProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
        )
        return getattr(user, "userprofile", None) or UserProfile.objects.create(user=user)

    def _make_master(self, username: str, first_name: str) -> MasterProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
            first_name=first_name,
            last_name="Master",
        )
        profile = getattr(user, "userprofile", None) or UserProfile.objects.create(user=user)
        return MasterProfile.objects.create(user=profile, profession="Stylist")

    def _make_service(self, name: str, rooms: list[MasterRoom]) -> Service:
        service = Service.objects.create(
            name=name,
            description="Test service",
            base_price="50.00",
            duration_min=60,
            extra_time_min=0,
        )
        service.allowed_rooms.set(rooms)
        return service

    def _make_appointment(self, start) -> Appointment:
        return Appointment.objects.create(client=self.client_profile, start_time=start)

    def _create_item(self, appointment, service, master, start):
        return AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=master,
            start_time=start,
        )

    def test_auto_assigns_free_room(self):
        room_a = MasterRoom.objects.create(room="Room A")
        room_b = MasterRoom.objects.create(room="Room B")
        service = self._make_service("Facial", [room_a, room_b])

        master_one = self._make_master("master1", "Alice")
        master_two = self._make_master("master2", "Brenda")
        start = timezone.now().replace(minute=0, second=0, microsecond=0)
        appt_one = self._make_appointment(start)
        appt_two = self._make_appointment(start)

        first_item = self._create_item(appt_one, service, master_one, start)
        second_item = self._create_item(appt_two, service, master_two, start + timedelta(minutes=15))

        self.assertEqual(first_item.room, room_a)
        self.assertEqual(second_item.room, room_b)

    def test_blocks_when_all_busy(self):
        room_a = MasterRoom.objects.create(room="Room A")
        room_b = MasterRoom.objects.create(room="Room B")
        service = self._make_service("Massage", [room_a, room_b])

        master_one = self._make_master("master1", "Alice")
        master_two = self._make_master("master2", "Brenda")
        master_three = self._make_master("master3", "Cara")
        base_start = timezone.now().replace(minute=0, second=0, microsecond=0)
        appt_one = self._make_appointment(base_start)
        appt_two = self._make_appointment(base_start)
        appt_three = self._make_appointment(base_start)

        self._create_item(appt_one, service, master_one, base_start)
        self._create_item(appt_two, service, master_two, base_start)

        pending = AppointmentItem(
            appointment=appt_three,
            service=service,
            master=master_three,
            start_time=base_start,
        )
        with self.assertRaises(ValidationError):
            pending.full_clean()

    def test_different_services_share_same_rooms(self):
        room_a = MasterRoom.objects.create(room="Room A")
        room_b = MasterRoom.objects.create(room="Room B")
        service_one = self._make_service("Laser A", [room_a, room_b])
        service_two = self._make_service("Laser B", [room_a, room_b])

        master_one = self._make_master("master1", "Alice")
        master_two = self._make_master("master2", "Brenda")
        master_three = self._make_master("master3", "Cara")
        base_start = timezone.now().replace(minute=0, second=0, microsecond=0)

        appt_one = self._make_appointment(base_start)
        appt_two = self._make_appointment(base_start)
        appt_three = self._make_appointment(base_start)

        first_item = self._create_item(appt_one, service_one, master_one, base_start)
        second_item = self._create_item(appt_two, service_two, master_two, base_start)

        self.assertEqual({first_item.room, second_item.room}, {room_a, room_b})

        conflict = AppointmentItem(
            appointment=appt_three,
            service=service_two,
            master=master_three,
            start_time=base_start,
            end_time=base_start + timedelta(minutes=60),
            room=room_a,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AppointmentItem.objects.bulk_create([conflict])

    def test_update_reallocates_or_blocks(self):
        room_a = MasterRoom.objects.create(room="Room A")
        room_b = MasterRoom.objects.create(room="Room B")
        service = self._make_service("Peel", [room_a, room_b])

        m1 = self._make_master("master1", "Alice")
        m2 = self._make_master("master2", "Brenda")
        m3 = self._make_master("master3", "Cara")
        m4 = self._make_master("master4", "Daria")

        slot_one = timezone.now().replace(minute=0, second=0, microsecond=0)
        slot_two = slot_one + timedelta(hours=2)

        appt_a = self._make_appointment(slot_one)
        appt_b = self._make_appointment(slot_one)
        appt_c = self._make_appointment(slot_two)
        appt_d = self._make_appointment(slot_one)

        self._create_item(appt_a, service, m1, slot_one)
        moving = self._create_item(appt_b, service, m2, slot_one)
        blocker_future = self._create_item(appt_c, service, m3, slot_two)

        moving.start_time = slot_two
        moving.save()
        moving.refresh_from_db()
        self.assertNotEqual(moving.room, blocker_future.room)

        self._create_item(appt_d, service, m4, slot_one)

        moving.start_time = slot_one
        with self.assertRaises(ValidationError):
            moving.full_clean()

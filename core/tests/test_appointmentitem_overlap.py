from __future__ import annotations

import unittest
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
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


class AppointmentItemOverlapConstraintTests(TransactionTestCase):
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Appointment overlap constraint requires PostgreSQL.")
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.user_model = get_user_model()
        self.client_profile = self._make_user_profile("appt-client", first_name="Client")
        self.master = self._make_master("appt-master", "Master")
        self.room = MasterRoom.objects.create(room="Room A")
        self.service = Service.objects.create(
            name="Test Service",
            description="",
            base_price="100.00",
            duration_min=60,
            extra_time_min=15,
        )
        self.service.allowed_rooms.add(self.room)
        self.appointment = Appointment.objects.create(
            client=self.client_profile,
            start_time=self._dt(16, 0),
        )

    def _make_user_profile(self, username: str, *, first_name: str, last_name: str = "User") -> UserProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
            first_name=first_name,
            last_name=last_name,
        )
        profile = getattr(user, "userprofile", None)
        if profile is None:
            profile = UserProfile.objects.create(user=user)
        return profile

    def _make_master(self, username: str, first_name: str) -> MasterProfile:
        profile = self._make_user_profile(username, first_name=first_name, last_name="Master")
        return MasterProfile.objects.create(user=profile, profession="Stylist")

    def _dt(self, hour: int, minute: int) -> datetime:
        base = datetime(2025, 11, 13, hour, minute)
        return timezone.make_aware(base, timezone.get_current_timezone())

    def _create_item(self, start_time, *, validation_enabled: bool = True) -> AppointmentItem:
        return AppointmentItem.objects.create(
            appointment=self.appointment,
            service=self.service,
            master=self.master,
            start_time=start_time,
            room=self.room,
            validation_enabled=validation_enabled,
        )

    def test_back_to_back_appointments_share_room_without_conflict(self):
        first_item = self._create_item(self._dt(16, 0))
        second_item = self._create_item(self._dt(17, 15))

        self.assertEqual(first_item.room, self.room)
        self.assertEqual(second_item.room, self.room)
        self.assertEqual(first_item.end_time, second_item.start_time)
        self.assertEqual(AppointmentItem.objects.count(), 2)

    def test_true_overlaps_still_raise_integrity_error(self):
        self._create_item(self._dt(16, 0))

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_item(self._dt(17, 0), validation_enabled=False)

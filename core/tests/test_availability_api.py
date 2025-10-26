from __future__ import annotations

from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentItem,
    AppointmentStatus,
    AppointmentStatusHistory,
    MasterProfile,
    MasterWorkDay,
    Service,
    ServiceMaster,
    UserProfile,
)
from core.tests.utils import assign_service_room


class AvailabilityRoomsApiTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user_model = get_user_model()
        self.staff_user = self.user_model.objects.create_user(
            username="staff", email="staff@example.com", password="pass123"
        )
        self.staff_profile = getattr(self.staff_user, "userprofile", None)
        if self.staff_profile is None:
            self.staff_profile = UserProfile.objects.create(user=self.staff_user)
        self.client.force_login(self.staff_user)

        self.client_profile = self._make_client("client-api")
        self.master_one = self._make_master("master-one")
        self.master_two = self._make_master("master-two")

        for master in (self.master_one, self.master_two):
            self._ensure_full_workweek(master)

        self.today = timezone.localdate()
        self.timezone = timezone.get_current_timezone()

        self.status_confirmed, _ = AppointmentStatus.objects.get_or_create(name="Confirmed")
        self.status_cancelled, _ = AppointmentStatus.objects.get_or_create(name="Cancelled")

    def _make_client(self, username: str) -> UserProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass123",
        )
        profile = getattr(user, "userprofile", None)
        if profile is None:
            profile = UserProfile.objects.create(user=user)
        return profile

    def _make_master(self, username: str) -> MasterProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass123",
            first_name=username.split("-")[0].title(),
            last_name="Master",
        )
        profile = getattr(user, "userprofile", None)
        if profile is None:
            profile = UserProfile.objects.create(user=user)
        return MasterProfile.objects.create(user=profile, profession="Stylist")

    def _ensure_full_workweek(self, master: MasterProfile):
        for weekday in range(7):
            MasterWorkDay.objects.create(
                master=master,
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(20, 0),
            )

    def _create_service(self, *, rooms: int, masters: list[MasterProfile]) -> Service:
        service = Service.objects.create(
            name=f"Service-{rooms}",
            base_price="50.00",
            duration_min=60,
            extra_time_min=0,
        )
        for idx in range(rooms):
            assign_service_room(service, room_name=f"Room {rooms}-{idx + 1}")
        for master in masters:
            ServiceMaster.objects.create(service=service, master=master)
        return service

    def _slot_at(self, hour: int) -> datetime:
        base = datetime.combine(self.today, time(hour, 0))
        return timezone.make_aware(base, self.timezone)

    def _book(self, *, service: Service, master: MasterProfile, start):
        appt = Appointment.objects.create(client=self.client_profile, start_time=start)
        item = AppointmentItem(
            appointment=appt,
            service=service,
            master=master,
            start_time=start,
        )
        item.full_clean()
        item.save()
        return appt

    def _set_status(self, appointment: Appointment, status: AppointmentStatus):
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            status=status,
            set_by=self.staff_profile,
        )

    def test_returns_no_slots_when_service_lacks_rooms(self):
        service = self._create_service(rooms=0, masters=[self.master_one])

        response = self.client.get(
            reverse("api-availability"),
            {"service": str(service.pk), "date": self.today.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        masters = {entry["id"]: entry.get("slots", []) for entry in payload.get("masters", [])}
        self.assertIn(self.master_one.id, masters)
        self.assertEqual(masters[self.master_one.id], [])

    def test_slots_disappear_once_all_rooms_busy(self):
        service = self._create_service(rooms=1, masters=[self.master_one, self.master_two])
        target = self._slot_at(10)
        params = {
            "service": str(service.pk),
            "date": target.date().isoformat(),
            "master": str(self.master_two.pk),
        }

        resp_before = self.client.get(reverse("api-availability"), params)
        self.assertEqual(resp_before.status_code, 200)
        slots_before = resp_before.json().get("slots", [])
        self.assertIn(target.isoformat(), slots_before)

        appointment = self._book(service=service, master=self.master_one, start=target)
        self._set_status(appointment, self.status_confirmed)

        resp_after = self.client.get(reverse("api-availability"), params)
        self.assertEqual(resp_after.status_code, 200)
        slots_after = resp_after.json().get("slots", [])
        self.assertNotIn(target.isoformat(), slots_after)

    def test_cancelled_appointment_does_not_block_room(self):
        service = self._create_service(rooms=1, masters=[self.master_one, self.master_two])
        target = self._slot_at(11)
        appointment = self._book(service=service, master=self.master_one, start=target)
        self._set_status(appointment, self.status_cancelled)

        response = self.client.get(
            reverse("api-availability"),
            {
                "service": str(service.pk),
                "date": target.date().isoformat(),
                "master": str(self.master_two.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        slots = response.json().get("slots", [])
        self.assertIn(target.isoformat(), slots)

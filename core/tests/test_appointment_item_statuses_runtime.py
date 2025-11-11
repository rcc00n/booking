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


class AppointmentItemStatusRuntimeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.status_catalog = {}
        defaults = {
            "BOOKED": "Booked",
            "CONFIRMED": "Confirmed",
            "CANCELLED": "Cancelled",
            "COMPLETED": "Completed",
        }
        for code, name in defaults.items():
            status, _ = AppointmentItemStatus.objects.update_or_create(
                code=code,
                defaults={"name": name, "is_active": True},
            )
            cls.status_catalog[code] = status

        user_model = get_user_model()

        client_user = user_model.objects.create_user(username="client-appt", password="test123")
        cls.client_profile = UserProfile.objects.create(user=client_user)

        master_user = user_model.objects.create_user(username="master-appt", password="test123")
        master_profile_user = UserProfile.objects.create(user=master_user)
        cls.master_profile = MasterProfile.objects.create(user=master_profile_user)

        cls.payment_status = PaymentStatus.objects.create(name="Not Paid")

        cls.service = Service.objects.create(
            name="Deep Tissue",
            base_price=Decimal("120.00"),
            duration_min=60,
            extra_time_min=0,
        )
        room = MasterRoom.objects.create(room="Room A")
        cls.service.allowed_rooms.add(room)
        ServiceMaster.objects.create(service=cls.service, master=cls.master_profile)

    def create_appointment(self, status_sequence: list[str]) -> Appointment:
        now = timezone.now()
        appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=now,
        )

        for index, status_code in enumerate(status_sequence):
            item = AppointmentItem.objects.create(
                appointment=appointment,
                service=self.service,
                master=self.master_profile,
                start_time=now + timedelta(minutes=60 * index),
                unit_price=self.service.base_price,
            )
            status = self.status_catalog[status_code]
            AppointmentItemStatusHistory.objects.create(
                item=item,
                status=status,
                set_by=None,
            )
            AppointmentItem.objects.filter(pk=item.pk).update(status=status)

        return appointment

    def test_aggregated_status_all_cancelled(self) -> None:
        appointment = self.create_appointment(["CANCELLED", "CANCELLED"])
        self.assertEqual(appointment.aggregated_status_code, "CANCELLED")
        self.assertEqual(appointment.aggregated_status, "Cancelled")

    def test_aggregated_status_all_completed(self) -> None:
        appointment = self.create_appointment(["COMPLETED", "COMPLETED", "COMPLETED"])
        self.assertEqual(appointment.aggregated_status_code, "COMPLETED")
        self.assertEqual(appointment.aggregated_status, "Completed")

    def test_aggregated_status_confirmed_mixed(self) -> None:
        appointment = self.create_appointment(["CONFIRMED", "COMPLETED"])
        self.assertEqual(appointment.aggregated_status_code, "CONFIRMED")
        self.assertEqual(appointment.aggregated_status, "Confirmed")

    def test_aggregated_status_cancelled_and_confirmed(self) -> None:
        appointment = self.create_appointment(["CANCELLED", "CONFIRMED"])
        self.assertEqual(appointment.aggregated_status_code, "BOOKED")
        self.assertEqual(appointment.aggregated_status, "Booked")

    def test_aggregated_status_defaults_to_booked(self) -> None:
        appointment = self.create_appointment(["BOOKED", "BOOKED"])
        self.assertEqual(appointment.aggregated_status_code, "BOOKED")
        self.assertEqual(appointment.aggregated_status, "Booked")

    def test_with_aggregated_status_annotation_avoids_extra_queries(self) -> None:
        self.create_appointment(["CANCELLED", "CANCELLED"])
        self.create_appointment(["COMPLETED"])
        self.create_appointment(["CONFIRMED"])

        qs = Appointment.objects.with_aggregated_status().order_by("created_at")

        with self.assertNumQueries(1):
            appointments = list(qs)

        with self.assertNumQueries(0):
            codes = [appt.aggregated_status_code for appt in appointments]
            labels = [appt.aggregated_status for appt in appointments]

        self.assertEqual(codes, ["CANCELLED", "COMPLETED", "CONFIRMED"])
        self.assertEqual(labels, ["Cancelled", "Completed", "Confirmed"])

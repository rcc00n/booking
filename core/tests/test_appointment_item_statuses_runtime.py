from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
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


@pytest.fixture
def status_catalog(db):
    statuses = {}
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
        statuses[code] = status
    return statuses


@pytest.fixture
def appointment_factory(db, status_catalog):
    user_model = get_user_model()

    client_user = user_model.objects.create_user(username="client-appt", password="test123")
    client_profile = UserProfile.objects.create(user=client_user)

    master_user = user_model.objects.create_user(username="master-appt", password="test123")
    master_profile_user = UserProfile.objects.create(user=master_user)
    master_profile = MasterProfile.objects.create(user=master_profile_user)

    payment_status = PaymentStatus.objects.create(name="Not Paid")

    service = Service.objects.create(
        name="Deep Tissue",
        base_price=Decimal("120.00"),
        duration_min=60,
        extra_time_min=0,
    )
    room = MasterRoom.objects.create(room="Room A")
    service.allowed_rooms.add(room)
    ServiceMaster.objects.create(service=service, master=master_profile)

    def make_appointment(status_sequence: list[str]) -> Appointment:
        now = timezone.now()
        appointment = Appointment.objects.create(
            client=client_profile,
            payment_status=payment_status,
            start_time=now,
        )

        for index, status_code in enumerate(status_sequence):
            item = AppointmentItem.objects.create(
                appointment=appointment,
                service=service,
                master=master_profile,
                start_time=now + timedelta(minutes=60 * index),
                unit_price=service.base_price,
            )
            status = status_catalog[status_code]
            AppointmentItemStatusHistory.objects.create(
                item=item,
                status=status,
                set_by=None,
            )
            AppointmentItem.objects.filter(pk=item.pk).update(status=status)

        return appointment

    return make_appointment


def test_aggregated_status_all_cancelled(appointment_factory):
    appointment = appointment_factory(["CANCELLED", "CANCELLED"])
    assert appointment.aggregated_status_code == "CANCELLED"
    assert appointment.aggregated_status == "Cancelled"


def test_aggregated_status_all_completed(appointment_factory):
    appointment = appointment_factory(["COMPLETED", "COMPLETED", "COMPLETED"])
    assert appointment.aggregated_status_code == "COMPLETED"
    assert appointment.aggregated_status == "Completed"


def test_aggregated_status_confirmed_mixed(appointment_factory):
    appointment = appointment_factory(["CONFIRMED", "COMPLETED"])
    assert appointment.aggregated_status_code == "CONFIRMED"
    assert appointment.aggregated_status == "Confirmed"

def test_aggregated_status_cancelled_and_confirmed(appointment_factory):
    appointment = appointment_factory(["CANCELLED", "CONFIRMED"])
    assert appointment.aggregated_status_code == "BOOKED"
    assert appointment.aggregated_status == "Booked"


def test_aggregated_status_defaults_to_booked(appointment_factory):
    appointment = appointment_factory(["BOOKED", "BOOKED"])
    assert appointment.aggregated_status_code == "BOOKED"
    assert appointment.aggregated_status == "Booked"


def test_with_aggregated_status_annotation_avoids_extra_queries(
    appointment_factory, django_assert_num_queries
):
    appointment_factory(["CANCELLED", "CANCELLED"])
    appointment_factory(["COMPLETED"])
    appointment_factory(["CONFIRMED"])

    qs = Appointment.objects.with_aggregated_status().order_by("created_at")

    with django_assert_num_queries(1):
        appointments = list(qs)

    with django_assert_num_queries(0):
        codes = [appt.aggregated_status_code for appt in appointments]
        labels = [appt.aggregated_status for appt in appointments]

    assert codes == ["CANCELLED", "COMPLETED", "CONFIRMED"]
    assert labels == ["Cancelled", "Completed", "Confirmed"]

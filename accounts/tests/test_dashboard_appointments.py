from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from core.models import Appointment, AppointmentItem, MasterProfile, Service, UserProfile
from core.tests.utils import assign_service_room


def _aware(dt: datetime) -> datetime:
    tz = timezone.get_current_timezone()
    if timezone.is_aware(dt):
        return dt.astimezone(tz)
    return timezone.make_aware(dt, tz)


@pytest.fixture
def make_user_with_profile(db):
    def _make(prefix: str = "user") -> tuple:
        user_model = get_user_model()
        suffix = uuid4().hex[:8]
        email = f"{prefix}-{suffix}@example.com"
        user = user_model.objects.create_user(
            username=email,
            email=email,
            password="pass1234",
        )
        profile = UserProfile.objects.create(user=user)
        return user, profile

    return _make


@pytest.fixture
def master_profile(db):
    user_model = get_user_model()
    master_user = user_model.objects.create_user(
        username="master@example.com",
        email="master@example.com",
        password="pass1234",
    )
    master_user_profile = UserProfile.objects.create(user=master_user)
    return MasterProfile.objects.create(user=master_user_profile)


def _create_appointment(
    *,
    profile: UserProfile,
    start: datetime,
    service_name: str,
    master: MasterProfile,
) -> Appointment:
    service = Service.objects.create(
        name=service_name,
        base_price=Decimal("120.00"),
        duration_min=60,
    )
    assign_service_room(service)
    appointment = Appointment.objects.create(
        client=profile,
        start_time=start,
        final_price=Decimal("120.00"),
    )
    AppointmentItem.objects.create(
        appointment=appointment,
        service=service,
        master=master,
        start_time=start,
        end_time=start + timedelta(hours=1),
    )
    return appointment


@pytest.mark.django_db
def test_dashboard_shows_only_authenticated_client_appointments(
    client, make_user_with_profile, master_profile
):
    user, profile = make_user_with_profile("primary")
    other_user, other_profile = make_user_with_profile("secondary")

    client.force_login(user)

    own_start = _aware(timezone.now() + timedelta(days=3))
    other_start = _aware(timezone.now() + timedelta(days=7))

    _create_appointment(profile=profile, start=own_start, service_name="Facial", master=master_profile)
    _create_appointment(profile=other_profile, start=other_start, service_name="Massage", master=master_profile)

    response = client.get(reverse("dashboard"))
    assert response.status_code == 200

    months = response.context["appointments_by_month"]
    assert months

    month = months[0]
    assert len(month["appointments"]) == 1

    card = month["appointments"][0]
    assert card.service_name == "Facial"
    assert card.is_future is True


@pytest.mark.django_db
def test_dashboard_groups_appointments_by_month_descending(
    client, make_user_with_profile, master_profile
):
    user, profile = make_user_with_profile("grouping")
    client.force_login(user)

    starts = [
        _aware(datetime(2025, 12, 1, 9, 0)),
        _aware(datetime(2025, 12, 20, 15, 0)),
        _aware(datetime(2025, 11, 5, 13, 30)),
    ]
    names = ["Peel", "Massage", "Consultation"]
    for index, start in enumerate(starts):
        _create_appointment(profile=profile, start=start, service_name=names[index], master=master_profile)

    response = client.get(reverse("dashboard"))
    assert response.status_code == 200

    months = response.context["appointments_by_month"]
    assert [month["iso"] for month in months] == ["2025-12-01", "2025-11-01"]

    december_cards = months[0]["appointments"]
    assert len(december_cards) == 2
    assert {card.service_name for card in december_cards} == {"Peel", "Massage"}


@pytest.mark.django_db
def test_dashboard_markup_includes_data_attributes(client, make_user_with_profile, master_profile):
    user, profile = make_user_with_profile("markup")
    client.force_login(user)

    start = _aware(timezone.now() + timedelta(days=5))
    _create_appointment(profile=profile, start=start, service_name="Laser", master=master_profile)

    response = client.get(reverse("dashboard"))
    assert response.status_code == 200

    html = response.content.decode("utf-8")
    assert 'data-appt-start-iso="' in html
    assert 'class="appt-cancel' in html
    assert 'class="appt-reschedule' in html

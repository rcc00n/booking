from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Appointment, AppointmentItem, MasterProfile, Service, UserProfile
from core.tests.utils import assign_service_room


def _aware(dt: datetime) -> datetime:
    tz = timezone.get_current_timezone()
    if timezone.is_aware(dt):
        return dt.astimezone(tz)
    return timezone.make_aware(dt, tz)


class DashboardAppointmentsTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        master_user = user_model.objects.create_user(
            username="master@example.com",
            email="master@example.com",
            password="pass1234",
        )
        master_profile = UserProfile.objects.create(user=master_user)
        self.master = MasterProfile.objects.create(user=master_profile)
        self.user_model = user_model

    def _make_user_with_profile(self, prefix: str = "user") -> tuple:
        suffix = uuid4().hex[:8]
        email = f"{prefix}-{suffix}@example.com"
        user = self.user_model.objects.create_user(
            username=email,
            email=email,
            password="pass1234",
        )
        profile = UserProfile.objects.create(user=user)
        return user, profile

    def _create_appointment(
        self,
        *,
        profile: UserProfile,
        start: datetime,
        service_name: str,
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
            master=self.master,
            start_time=start,
            end_time=start + timedelta(hours=1),
        )
        return appointment

    def test_dashboard_shows_only_authenticated_client_appointments(self) -> None:
        user, profile = self._make_user_with_profile("primary")
        _, other_profile = self._make_user_with_profile("secondary")

        self.client.force_login(user)

        own_start = _aware(timezone.now() + timedelta(days=3))
        other_start = _aware(timezone.now() + timedelta(days=7))

        self._create_appointment(profile=profile, start=own_start, service_name="Facial")
        self._create_appointment(profile=other_profile, start=other_start, service_name="Massage")

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        months = response.context["appointments_by_month"]
        self.assertTrue(months)

        month = months[0]
        self.assertEqual(len(month["appointments"]), 1)

        card = month["appointments"][0]
        self.assertEqual(card.service_name, "Facial")
        self.assertTrue(card.is_future)

    def test_dashboard_groups_appointments_by_month_descending(self) -> None:
        user, profile = self._make_user_with_profile("grouping")
        self.client.force_login(user)

        starts = [
            _aware(datetime(2025, 12, 1, 9, 0)),
            _aware(datetime(2025, 12, 20, 15, 0)),
            _aware(datetime(2025, 11, 5, 13, 30)),
        ]
        names = ["Peel", "Massage", "Consultation"]
        for index, start in enumerate(starts):
            self._create_appointment(profile=profile, start=start, service_name=names[index])

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        months = response.context["appointments_by_month"]
        self.assertEqual([month["iso"] for month in months], ["2025-12-01", "2025-11-01"])

        december_cards = months[0]["appointments"]
        self.assertEqual(len(december_cards), 2)
        self.assertSetEqual({card.service_name for card in december_cards}, {"Peel", "Massage"})

    def test_dashboard_markup_includes_data_attributes(self) -> None:
        user, profile = self._make_user_with_profile("markup")
        self.client.force_login(user)

        start = _aware(timezone.now() + timedelta(days=5))
        self._create_appointment(profile=profile, start=start, service_name="Laser")

        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        self.assertIn('data-appt-start-iso="', html)
        self.assertIn('class="appt-cancel', html)
        self.assertIn('class="appt-reschedule', html)

    def test_dashboard_query_count(self) -> None:
        user, profile = self._make_user_with_profile("queries")
        self.client.force_login(user)

        starts = [
            _aware(timezone.now() + timedelta(days=day, hours=offset))
            for day in range(1, 4)
            for offset in (0, 2)
        ]
        for index, start in enumerate(starts):
            self._create_appointment(
                profile=profile,
                start=start,
                service_name=f"Service {index}",
            )

        expected_queries = 11 if connection.vendor == "postgresql" else 22
        with self.assertNumQueries(expected_queries):
            response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

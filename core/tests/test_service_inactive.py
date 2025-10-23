from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.forms import AppointmentItemInlineForm, MasterCreateFullForm
from core.models import (
    Appointment,
    AppointmentItem,
    BookingCart,
    BookingCartItem,
    MasterProfile,
    Service,
    ServiceCategory,
    ServiceMaster,
    UserProfile,
)


class ServiceActiveStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.client_user = user_model.objects.create_user(username="client", password="pass123")
        cls.client_profile = getattr(cls.client_user, "userprofile", None)
        if cls.client_profile is None:
            cls.client_profile = UserProfile.objects.create(user=cls.client_user)

        master_user = user_model.objects.create_user(username="master", password="pass123")
        master_profile_user = getattr(master_user, "userprofile", None)
        if master_profile_user is None:
            master_profile_user = UserProfile.objects.create(user=master_user)
        cls.master_profile = MasterProfile.objects.create(user=master_profile_user)

        cls.category = ServiceCategory.objects.create(name="Therapy")
        cls.active_service = Service.objects.create(
            name="Massage",
            category=cls.category,
            base_price=Decimal("100.00"),
            duration_min=60,
        )
        cls.inactive_service = Service.objects.create(
            name="Cryotherapy",
            category=cls.category,
            base_price=Decimal("150.00"),
            duration_min=45,
            is_active=False,
        )

        ServiceMaster.objects.create(service=cls.active_service, master=cls.master_profile)
        ServiceMaster.objects.create(service=cls.inactive_service, master=cls.master_profile)

    def test_service_search_excludes_inactive(self):
        response = self.client.get(reverse("service-search"), {"q": ""})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {row["id"] for row in payload.get("results", [])}
        self.assertIn(str(self.active_service.pk), ids)
        self.assertNotIn(str(self.inactive_service.pk), ids)

    def test_availability_api_rejects_inactive_service(self):
        self.client.force_login(self.client_user)
        response = self.client.get(
            reverse("api-availability"),
            {
                "service": str(self.inactive_service.pk),
                "date": timezone.now().date().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inactive", response.content.decode().lower())


    def test_service_autocomplete_excludes_inactive(self):
        response = self.client.get(reverse('service-autocomplete'), {'q': 'massage'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {row.get('id') for row in payload.get('results', [])}
        self.assertIn(str(self.active_service.pk), ids)
        self.assertNotIn(str(self.inactive_service.pk), ids)

    def test_booking_api_rejects_inactive_service(self):
        self.client.force_login(self.client_user)
        start_time = (timezone.now() + timedelta(hours=1)).isoformat()
        response = self.client.post(
            reverse("api-book"),
            data=json.dumps(
                {
                    "service": str(self.inactive_service.pk),
                    "master": self.master_profile.pk,
                    "start_time": start_time,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inactive", response.json().get("error", "").lower())

    def test_cart_api_rejects_inactive_service(self):
        self.client.force_login(self.client_user)
        start_time = (timezone.now() + timedelta(hours=2)).isoformat()
        response = self.client.post(
            reverse("api-cart-add"),
            data=json.dumps(
                {
                    "service": str(self.inactive_service.pk),
                    "master": self.master_profile.pk,
                    "start_time": start_time,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inactive", response.json().get("error", "").lower())

    def test_booking_cart_item_clean_blocks_inactive_service(self):
        cart = BookingCart.for_user(self.client_profile)
        item = BookingCartItem(
            cart=cart,
            service=self.inactive_service,
            master=self.master_profile,
            start_time=timezone.now(),
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("inactive", str(ctx.exception).lower())

    def test_appointment_item_clean_blocks_inactive_service(self):
        appointment = Appointment.objects.create(client=self.client_profile, start_time=None)
        item = AppointmentItem(
            appointment=appointment,
            service=self.inactive_service,
            master=self.master_profile,
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("inactive", str(ctx.exception).lower())

    def test_master_form_marks_existing_inactive_services_disabled(self):
        form = MasterCreateFullForm(instance=self.master_profile)
        field = form.fields["services"]
        queryset_ids = set(field.queryset.values_list("pk", flat=True))
        self.assertIn(self.active_service.pk, queryset_ids)
        self.assertNotIn(self.inactive_service.pk, queryset_ids)
        initial_ids = set(form.initial.get("services", []))
        self.assertNotIn(self.inactive_service.pk, initial_ids)

        fresh_form = MasterCreateFullForm()
        fresh_ids = set(fresh_form.fields["services"].queryset.values_list("pk", flat=True))
        self.assertIn(self.active_service.pk, fresh_ids)
        self.assertNotIn(self.inactive_service.pk, fresh_ids)

    def test_appointment_form_excludes_inactive_service(self):
        appointment = Appointment.objects.create(client=self.client_profile, start_time=timezone.now())
        item = AppointmentItem.objects.create(
            appointment=appointment,
            service=self.active_service,
            master=self.master_profile,
            start_time=timezone.now(),
        )
        form = AppointmentItemInlineForm(instance=item)
        queryset_ids = set(form.fields["service"].queryset.values_list("pk", flat=True))
        self.assertIn(self.active_service.pk, queryset_ids)
        self.assertNotIn(self.inactive_service.pk, queryset_ids)

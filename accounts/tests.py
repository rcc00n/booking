import json
from datetime import timedelta, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Appointment,
    MasterProfile,
    MasterWorkDay,
    PaymentStatus,
    Service,
    ServiceCategory,
    ServiceMaster,
    UserProfile,
)


class CartApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.password = "testpass123"
        self.user = User.objects.create_user(username="client", password=self.password, email="client@example.com")
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)

        self.master_user = User.objects.create_user(username="master", password="masterpass", email="master@example.com")
        self.master_profile_user, _ = UserProfile.objects.get_or_create(user=self.master_user)
        self.master_profile = MasterProfile.objects.create(user=self.master_profile_user)
        for weekday in range(7):
            MasterWorkDay.objects.create(
                master=self.master_profile,
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(20, 0),
            )

        self.category = ServiceCategory.objects.create(name="Cuts")
        self.service1 = Service.objects.create(
            name="Service One",
            base_price=50,
            duration_min=30,
            category=self.category,
        )
        self.service2 = Service.objects.create(
            name="Service Two",
            base_price=30,
            duration_min=20,
            category=self.category,
        )
        ServiceMaster.objects.create(service=self.service1, master=self.master_profile)
        ServiceMaster.objects.create(service=self.service2, master=self.master_profile)

        PaymentStatus.objects.create(name="Pending")

        self.client.login(username="client", password=self.password)

    def test_add_multiple_services_and_checkout(self):
        base_dt = timezone.localtime(timezone.now() + timedelta(days=1))
        base_start = base_dt.replace(hour=10, minute=0, second=0, microsecond=0)

        payload1 = {
            "service": str(self.service1.pk),
            "master": self.master_profile.id,
            "start_time": base_start.isoformat(),
        }
        resp1 = self.client.post(
            "/accounts/api/cart/add/",
            data=json.dumps(payload1),
            content_type="application/json",
        )
        self.assertEqual(resp1.status_code, 201)

        payload2 = {
            "service": str(self.service2.pk),
            "master": self.master_profile.id,
            "start_time": (base_start + timedelta(minutes=45)).isoformat(),
        }
        resp2 = self.client.post(
            "/accounts/api/cart/add/",
            data=json.dumps(payload2),
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 201)

        summary = self.client.get("/accounts/api/cart/")
        self.assertEqual(summary.status_code, 200)
        data = summary.json()
        self.assertEqual(data["count"], 2)

        checkout = self.client.post(
            "/accounts/api/cart/checkout/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.json())

        appt = Appointment.objects.first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.client, self.profile)
        self.assertEqual(appt.items.count(), 2)

        summary_after = self.client.get("/accounts/api/cart/")
        self.assertEqual(summary_after.status_code, 200)
        self.assertEqual(summary_after.json()["count"], 0)

import json
from datetime import timedelta, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.forms import CustomUserCreationForm, CustomUserChangeForm
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


class RegistrationTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.url = reverse('register')

    def test_password_mismatch_does_not_create_user(self):
        data = {
            "username": "",
            "email": "newclient@example.com",
            "phone": "+1 (403) 555-1234",
            "password1": "StrongPass123!",
            "password2": "Mismatch123!",
        }
        response = self.client.post(self.url, data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.User.objects.count(), 0)
        self.assertIn('password2', response.json())

    def test_successful_registration_creates_profile_and_allows_login(self):
        data = {
            "username": "",  # разрешаем автогенерацию
            "email": "Client@Example.com",
            "phone": "403-555-1234",
            "first_name": "Test",
            "last_name": "User",
            "birth_date": "1995-01-01",
            "address": "123 Test Street",
            "how_heard": "google",
            "email_marketing_consent": "on",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        response = self.client.post(self.url, data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload.get('status'), 'ok')
        generated_username = payload.get('username')
        self.assertTrue(generated_username)
        self.assertEqual(payload.get('redirect'), f"{reverse('login')}?registered=1")

        self.assertEqual(self.User.objects.count(), 1)
        user = self.User.objects.get()
        self.assertEqual(user.username, generated_username)
        self.assertEqual(user.email, data['email'].lower())

        profile = getattr(user, 'userprofile', None)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.phone, '+14035551234')
        self.assertEqual(profile.address, data['address'])
        self.assertEqual(profile.how_heard, data['how_heard'])
        self.assertTrue(profile.email_marketing_consent)
        self.assertIsNotNone(profile.email_marketing_consented_at)
        self.assertEqual(profile.source, 'online')
        self.assertTrue(profile.userrole_set.filter(role__name='Client').exists())

        self.assertTrue(self.client.login(username=generated_username, password=data['password1']))
        self.client.logout()
        self.assertTrue(self.client.login(username=data['email'], password=data['password1']))

        self.assertEqual(self.User.objects.count(), 1)
        self.assertEqual(UserProfile.objects.count(), 1)


@override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_PUBLIC_KEY='pk_test_dummy')
class CartApiTests(TestCase):
    def setUp(self):
        create_intent_patcher = patch('core.views.payment_services.create_or_update_payment_intent')
        self.addCleanup(create_intent_patcher.stop)
        self.mock_create_intent = create_intent_patcher.start()

        payment_stub = SimpleNamespace(
            id='pay_test',
            status='requires_payment_method',
            amount=Decimal('0'),
            amount_received=Decimal('0'),
            currency='cad',
            livemode=False,
            stripe_payment_intent_id='pi_test',
        )
        intent_stub = SimpleNamespace(id='pi_test', client_secret='secret_test')
        self.mock_create_intent.return_value = SimpleNamespace(payment=payment_stub, intent=intent_stub)

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


class AdminUserFormTests(TestCase):
    def test_admin_creation_form_saves_profile_fields(self):
        form_data = {
            "username": "adminclient",
            "email": "client_admin@example.com",
            "first_name": "Admin",
            "last_name": "Client",
            "phone": "403-555-7890",
            "address": "42 Flower Road",  # optional
            "postal_code": "T2X1A1",
            "how_heard": "instagram",
            "email_marketing_consent": "on",
            "notes": "VIP client",
            "personal_discount_percent": "5",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
            "usable_password": "true",
            "is_active": "on",
            "is_staff": "",
            "is_superuser": "",
            "groups": [],
            "chronic_conditions": [],
            "contraindications": [],
            "birth_date_year": "1991",
            "birth_date_month": "2",
            "birth_date_day": "20",
        }

        creation_form = CustomUserCreationForm(data=form_data)
        self.assertTrue(creation_form.is_valid(), creation_form.errors)
        self.assertEqual(creation_form.cleaned_data['phone'], "+14035557890")

        user = creation_form.save()
        profile = user.userprofile
        profile.refresh_from_db()

        self.assertEqual(user.email, "client_admin@example.com")
        self.assertEqual(profile.phone, "+14035557890")
        self.assertEqual(profile.address, "42 Flower Road")
        self.assertEqual(profile.how_heard, "instagram")
        self.assertTrue(profile.email_marketing_consent)
        self.assertIsNotNone(profile.email_marketing_consented_at)
        self.assertEqual(profile.personal_discount_percent, 5)
        self.assertEqual(profile.source, "offline")

    def test_admin_change_form_updates_profile(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="change_client",
            email="change_client@example.com",
            password="OldPass123!",
            first_name="Change",
            last_name="Client",
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.phone = "+14035550000"
        profile.address = "Initial address"
        profile.save()

        form_data = {
            "username": user.username,
            "email": "change_client@example.com",
            "first_name": "Change",
            "last_name": "Client",
            "phone": "(403) 777-1111",
            "address": "500 Updated Ave",
            "postal_code": "T2Y7B1",
            "how_heard": "google",
            "email_marketing_consent": "on",
            "notes": "Updated note",
            "personal_discount_percent": "7",
            "is_active": "on",
            "is_staff": "",
            "is_superuser": "",
            "groups": [],
            "user_permissions": [],
            "password": user.password,
            "chronic_conditions": [],
            "contraindications": [],
            "birth_date_year": "1990",
            "birth_date_month": "1",
            "birth_date_day": "15",
        }

        change_form = CustomUserChangeForm(data=form_data, instance=user)
        self.assertTrue(change_form.is_valid(), change_form.errors)
        self.assertEqual(change_form.cleaned_data['phone'], "+14037771111")

        updated_user = change_form.save()
        updated_profile = updated_user.userprofile
        updated_profile.refresh_from_db()

        self.assertEqual(updated_profile.phone, "+14037771111")
        self.assertEqual(updated_profile.address, "500 Updated Ave")
        self.assertEqual(updated_profile.how_heard, "google")
        self.assertTrue(updated_profile.email_marketing_consent)
        self.assertEqual(updated_profile.personal_discount_percent, 7)

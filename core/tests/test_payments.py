from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta, time
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase, override_settings
from django.utils import timezone

from core import signals as core_signals
from core.models import (
    Appointment,
    BookingCart,
    BookingCartItem,
    MasterProfile,
    MasterWorkDay,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Service,
    ServiceDiscount,
    ServiceMaster,
)
from core.services import payments as payment_services
from core.services.booking import create_appointment_from_cart_items
from core.services.pricing import compute_cart_pricing
from core.payments import stripe_api


class FakeIntent(SimpleNamespace):
    """Helper stub mimicking Stripe's PaymentIntent object."""

    def to_dict_recursive(self):
        def convert(value):
            if isinstance(value, SimpleNamespace):
                return {k: convert(v) for k, v in value.__dict__.items()}
            if isinstance(value, list):
                return [convert(v) for v in value]
            return value

        return {k: convert(v) for k, v in self.__dict__.items()}


class CartTestMixin:
    def setUp(self):
        super().setUp()
        self._disconnect_signals()
        current_tz = timezone.get_current_timezone()
        today = timezone.now().astimezone(current_tz).date()
        self.now = timezone.make_aware(datetime.combine(today, time(12, 0)), current_tz)
        self.today = today
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="client",
            email="client@example.com",
            password="testpass",
        )
        self.profile = self.user.userprofile
        master_user = user_model.objects.create_user(
            username="master",
            email="master@example.com",
            password="masterpass",
        )
        self.master_profile = MasterProfile.objects.create(user=master_user.userprofile)
        for weekday in range(7):
            MasterWorkDay.objects.create(
                master=self.master_profile,
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(20, 0),
            )
        self.cart = BookingCart.for_user(self.profile)

    def tearDown(self):
        self._reconnect_signals()
        super().tearDown()

    def _disconnect_signals(self):
        post_save.disconnect(core_signals.appointment_post_save, sender=Appointment)

    def _reconnect_signals(self):
        post_save.connect(core_signals.appointment_post_save, sender=Appointment)

    def create_service(self, name: str = "Service", price: str = "50.00") -> Service:
        service = Service.objects.create(
            name=name,
            base_price=Decimal(price),
            duration_min=60,
            extra_time_min=0,
        )
        ServiceMaster.objects.create(service=service, master=self.master_profile)
        return service

    def add_cart_item(self, service: Service, *, start_time=None) -> BookingCartItem:
        return BookingCartItem.objects.create(
            cart=self.cart,
            service=service,
            master=self.master_profile,
            start_time=start_time or self.now,
        )

class PaymentServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="client", email="client@example.com", password="testpass"
        )
        self.profile = self.user.userprofile

        self.status_pending, _ = PaymentStatus.objects.get_or_create(name="Pending")
        self.status_paid, _ = PaymentStatus.objects.get_or_create(name="Paid")
        PaymentStatus.objects.get_or_create(name="Failed")
        PaymentMethod.objects.get_or_create(name="Manual")
        PaymentMethod.objects.get_or_create(name="Stripe")

        self.appointment = Appointment.objects.create(
            client=self.profile,
            start_time=timezone.now(),
            payment_status=self.status_pending,
        )
        self.appointment.final_price = Decimal("0.00")
        self.appointment.save(update_fields=["final_price"])

    def test_zero_amount_marks_paid(self):
        bundle = payment_services.create_or_update_payment_intent(
            self.appointment,
            amount=Decimal("0.00"),
        )

        self.assertIsNone(bundle.intent)
        payment = bundle.payment
        payment.refresh_from_db()
        self.appointment.refresh_from_db()

        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(payment.amount, Decimal("0.00"))
        self.assertEqual(payment.method.name, "Manual")
        self.assertEqual(self.appointment.payment_status.name, "Paid")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123", STRIPE_API_VERSION="2024-11-20")
    def test_create_payment_intent_sets_pending(self):
        self.appointment.final_price = Decimal("50.00")
        self.appointment.save(update_fields=["final_price"])

        fake_intent = FakeIntent(
            id="pi_test",
            client_secret="secret",
            status="requires_payment_method",
            livemode=False,
            metadata={"test": "ok"},
            amount=5000,
            amount_received=0,
            charges=SimpleNamespace(data=[]),
        )

        with mock.patch(
            "core.services.payments.stripe.PaymentIntent.create",
            return_value=fake_intent,
        ):
            bundle = payment_services.create_or_update_payment_intent(self.appointment)

        self.assertIsNotNone(bundle.intent)
        payment = bundle.payment
        payment.refresh_from_db()
        self.appointment.refresh_from_db()

        self.assertEqual(payment.stripe_payment_intent_id, "pi_test")
        self.assertEqual(payment.status, "requires_payment_method")
        self.assertEqual(payment.amount, Decimal("50.00"))
        self.assertEqual(self.appointment.payment_status.name, "Pending")

    def test_handle_webhook_event_updates_to_paid(self):
        self.appointment.final_price = Decimal("30.00")
        self.appointment.save(update_fields=["final_price"])
        payment_method, _ = PaymentMethod.objects.get_or_create(name="Stripe")
        payment = Payment.objects.create(
            appointment=self.appointment,
            amount=Decimal("30.00"),
            currency="cad",
            method=payment_method,
            status="processing",
            stripe_payment_intent_id="pi_success",
        )

        charge = {"id": "ch_123", "created": timezone.now().timestamp(), "receipt_url": "https://stripe/receipt", "amount_refunded": 0}
        intent = FakeIntent(
            id="pi_success",
            client_secret="secret",
            status="succeeded",
            livemode=False,
            metadata={},
            amount=3000,
            amount_received=3000,
            charges=SimpleNamespace(data=[charge]),
        )
        event = SimpleNamespace(type="payment_intent.succeeded", data=SimpleNamespace(object=intent))

        payment_services.handle_webhook_event(event)

        payment.refresh_from_db()
        self.appointment.refresh_from_db()

        self.assertEqual(payment.status, "succeeded")
        self.assertTrue(payment.receipt_url)
        self.assertEqual(self.appointment.payment_status.name, "Paid")


class CartPricingTests(CartTestMixin, TestCase):
    def test_compute_cart_pricing_applies_service_and_personal_discounts(self):
        service = self.create_service(name="Facial Moisture", price="70.00")
        ServiceDiscount.objects.create(
            service=service,
            discount_percent=10,
            start_date=self.today - timedelta(days=1),
            end_date=self.today + timedelta(days=1),
        )
        self.profile.personal_discount_percent = 5
        self.profile.save(update_fields=["personal_discount_percent"])
        self.add_cart_item(service)

        pricing = compute_cart_pricing(self.profile)

        self.assertEqual(pricing["total"], 6215)
        self.assertEqual(pricing["total_decimal"], "62.15")
        self.assertEqual(pricing["count"], 1)
        self.assertEqual(pricing["processing_fee"], 230)
        self.assertEqual(pricing["processing_fee_decimal"], "2.30")
        self.assertEqual(pricing["pre_fee_total_decimal"], "59.85")
        item = pricing["items"][0]
        self.assertEqual(item["unit_price_decimal"], "59.85")
        discount_types = {entry["type"] for entry in item["discounts"]}
        self.assertIn("service", discount_types)
        self.assertIn("personal", discount_types)


class CartCheckoutViewTests(CartTestMixin, TestCase):
    def test_create_cart_intent_handles_zero_total(self):
        service = self.create_service(name="Free consultation", price="0.00")
        self.add_cart_item(service)
        self.client.force_login(self.user)

        response = self.client.post(
            "/accounts/api/payments/cart/create-intent/",
            data={},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["requires_payment"])
        self.assertEqual(data["amount"], "0.00")
        self.assertEqual(Appointment.objects.filter(client=self.profile).count(), 1)
        appointment = Appointment.objects.get(client=self.profile)
        self.assertEqual(appointment.items.count(), 1)
        item = appointment.items.first()
        self.assertIsNotNone(item)
        self.assertEqual(item.final_price, Decimal("0.00"))
        payment = Payment.objects.get(appointment=appointment)
        self.assertEqual(payment.amount, Decimal("0.00"))
        self.assertEqual(payment.status, "succeeded")
        self.assertFalse(self.cart.items.exists())
        self.assertEqual(data["cart"]["processing_fee"], 0)

    @mock.patch("core.payments.stripe_api._get_or_create_stripe_customer", return_value="cus_test")
    @mock.patch("core.payments.stripe_api.stripe.PaymentIntent.create")
    def test_create_cart_intent_returns_payment_intent(
        self,
        mock_create_intent,
        _mock_customer,
    ):
        service = self.create_service(name="Facial Moisture", price="63.00")
        self.add_cart_item(service)
        self.client.force_login(self.user)
        mock_create_intent.return_value = SimpleNamespace(
            id="pi_test",
            client_secret="secret_test",
        )

        response = self.client.post(
            "/accounts/api/payments/cart/create-intent/",
            data={},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["requires_payment"])
        self.assertEqual(data["amount"], "65.39")
        self.assertEqual(data["amount_minor"], 6539)
        mock_create_intent.assert_called_once()
        kwargs = mock_create_intent.call_args.kwargs
        self.assertEqual(kwargs["amount"], 6539)
        self.assertEqual(kwargs["currency"], "cad")
        self.assertEqual(kwargs["metadata"]["cart_id"], data["cart"]["cart_id"])
        self.assertEqual(kwargs["metadata"]["cart_processing_fee_minor"], "239")
        self.assertEqual(kwargs["metadata"]["cart_service_fee_minor"], "0")


class CartAppointmentCreationTests(CartTestMixin, TestCase):
    def test_create_appointment_sets_card_fee_flag(self):
        service = self.create_service(name="Signature Facial", price="80.00")
        item = self.add_cart_item(service)

        appointment = create_appointment_from_cart_items(profile=self.profile, items=[item])
        appointment.refresh_from_db()

        self.assertTrue(appointment.apply_card_processing_fee)
        self.assertGreater(appointment.card_processing_fee, Decimal("0.00"))
        self.assertGreater(appointment.final_price, Decimal("80.00"))


class StripeWebhookTests(CartTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.service_paid = self.create_service(name="Facial Moisture", price="63.00")
        self.service_free = self.create_service(name="Consultation", price="0.00")

    def _prime_cart(self):
        self.cart.items.all().delete()
        self.add_cart_item(self.service_paid, start_time=self.now)
        self.add_cart_item(self.service_free, start_time=self.now + timedelta(hours=1))
        return compute_cart_pricing(self.profile)

    def _build_intent(self, pricing) -> FakeIntent:
        charge = {
            "id": "ch_test",
            "receipt_url": "https://example.com/receipt",
            "amount_refunded": 0,
            "payment_method": "pm_card",
        }
        return FakeIntent(
            id="pi_test",
            metadata={
                "user_id": str(self.profile.pk),
                "cart_id": pricing["cart_id"],
            },
            amount=pricing["total"],
            amount_received=pricing["total"],
            currency=pricing["currency"],
            customer="cus_test",
            status="succeeded",
            charges=SimpleNamespace(data=[charge]),
            livemode=False,
        )

    @mock.patch("core.payments.stripe_api._retrieve_payment_method")
    @mock.patch("core.payments.stripe_api._fetch_intent")
    def test_webhook_success_creates_appointment_and_payment(
        self,
        mock_fetch_intent,
        mock_retrieve_method,
    ):
        pricing = self._prime_cart()
        intent = self._build_intent(pricing)
        mock_fetch_intent.return_value = intent
        mock_retrieve_method.return_value = ("pm_card", {"card": {"funding": "credit"}})

        payment = stripe_api._handle_payment_intent_succeeded({"id": intent.id})

        appointment = payment.appointment
        self.assertIsNotNone(appointment)
        self.assertEqual(appointment.items.count(), 2)
        zero_item = appointment.items.filter(final_price=Decimal("0.00")).first()
        self.assertIsNotNone(zero_item)
        self.assertEqual(payment.amount, Decimal("65.39"))
        self.assertEqual(payment.status, "succeeded")
        self.assertEqual(payment.method.name, "Credit card")
        self.assertEqual(payment.metadata.get("cart_pricing", {}).get("total"), pricing["total"])
        self.assertEqual(payment.metadata.get("cart_pricing", {}).get("processing_fee"), pricing["processing_fee"])
        self.assertEqual(payment.metadata.get("card_processing_fee_minor"), "239")
        self.assertEqual(payment.metadata.get("cart_service_fee_minor"), "0")
        self.assertFalse(self.cart.items.exists())

    @mock.patch("core.payments.stripe_api._retrieve_payment_method")
    @mock.patch("core.payments.stripe_api._fetch_intent")
    def test_webhook_success_is_idempotent(
        self,
        mock_fetch_intent,
        mock_retrieve_method,
    ):
        pricing = self._prime_cart()
        intent = self._build_intent(pricing)
        mock_fetch_intent.return_value = intent
        mock_retrieve_method.return_value = ("pm_card", {"card": {"funding": "credit"}})

        first_payment = stripe_api._handle_payment_intent_succeeded({"id": intent.id})
        second_payment = stripe_api._handle_payment_intent_succeeded({"id": intent.id})

        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Payment.objects.filter(stripe_payment_intent_id=intent.id).count(), 1)
        self.assertEqual(first_payment.pk, second_payment.pk)
        self.assertEqual(first_payment.appointment_id, second_payment.appointment_id)
        self.assertEqual(first_payment.metadata.get("cart_pricing", {}), second_payment.metadata.get("cart_pricing", {}))

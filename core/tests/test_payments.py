from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Appointment, Payment, PaymentMethod, PaymentStatus
from core.services import payments as payment_services


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

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from datetime import timedelta

from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentItem,
    MasterProfile,
    Payment,
    PaymentMethod,
    PaymentRefund,
    Service,
)
from core.services.refunds import RefundService, RefundError
from core.tests.utils import assign_service_room


class RefundServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.client_user = user_model.objects.create_user(
            username="client",
            email="client@example.com",
            password="pass1234",
        )
        cls.master_user = user_model.objects.create_user(
            username="master",
            email="master@example.com",
            password="pass1234",
        )
        cls.master_profile = MasterProfile.objects.create(user=cls.master_user.userprofile)
        cls.service = Service.objects.create(
            name="Massage",
            base_price=Decimal("120.00"),
            duration_min=60,
        )
        assign_service_room(cls.service, "Therapy Room")
        cls.stripe_method = PaymentMethod.objects.create(name="Stripe")
        cls.cash_method = PaymentMethod.objects.create(name="Cash")

    def _create_appointment(self) -> Appointment:
        return Appointment.objects.create(
            client=self.client_user.userprofile,
            start_time=timezone.now(),
        )

    def _create_payment(
        self,
        appointment: Appointment,
        *,
        amount: str,
        received: str,
        refunded: str,
        method: PaymentMethod,
        stripe_id: str | None = None,
        charge_id: str | None = None,
        captured_offset_hours: int = 0,
    ) -> Payment:
        captured_at = timezone.now() + timedelta(hours=captured_offset_hours)
        return Payment.objects.create(
            appointment=appointment,
            amount=Decimal(amount),
            amount_received=Decimal(received),
            amount_refunded=Decimal(refunded),
            method=method,
            status="succeeded",
            stripe_payment_intent_id=stripe_id,
            stripe_charge_id=charge_id,
            captured_at=captured_at,
        )

    def test_allocate_single_card_partial(self):
        appointment = self._create_appointment()
        payment = self._create_payment(
            appointment,
            amount="100.00",
            received="100.00",
            refunded="10.00",
            method=self.stripe_method,
            stripe_id="pi_card",
        )

        allocations = RefundService.allocate_refund_for_appointment(appointment, 2000)
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0].payment, payment)
        self.assertEqual(allocations[0].amount_minor, 2000)

    def test_allocate_cascades_across_multiple_cards(self):
        appointment = self._create_appointment()
        first = self._create_payment(
            appointment,
            amount="50.00",
            received="50.00",
            refunded="0.00",
            method=self.stripe_method,
            stripe_id="pi_one",
            captured_offset_hours=-2,
        )
        second = self._create_payment(
            appointment,
            amount="80.00",
            received="80.00",
            refunded="0.00",
            method=self.stripe_method,
            stripe_id="pi_two",
            captured_offset_hours=-1,
        )

        allocations = RefundService.allocate_refund_for_appointment(appointment, 7000)
        self.assertEqual(len(allocations), 2)
        self.assertEqual(allocations[0].payment, first)
        self.assertEqual(allocations[0].amount_minor, 5000)
        self.assertEqual(allocations[1].payment, second)
        self.assertEqual(allocations[1].amount_minor, 2000)

    def test_allocate_prefers_card_before_cash(self):
        appointment = self._create_appointment()
        card_payment = self._create_payment(
            appointment,
            amount="60.00",
            received="60.00",
            refunded="0.00",
            method=self.stripe_method,
            stripe_id="pi_card",
        )
        cash_payment = self._create_payment(
            appointment,
            amount="40.00",
            received="40.00",
            refunded="0.00",
            method=self.cash_method,
        )

        allocations = RefundService.allocate_refund_for_appointment(appointment, 8000)
        self.assertEqual(len(allocations), 2)
        self.assertEqual(allocations[0].payment, card_payment)
        self.assertEqual(allocations[0].amount_minor, 6000)
        self.assertEqual(allocations[1].payment, cash_payment)
        self.assertEqual(allocations[1].amount_minor, 2000)

    def test_allocate_only_cash_payments(self):
        appointment = self._create_appointment()
        cash_payment = self._create_payment(
            appointment,
            amount="120.00",
            received="120.00",
            refunded="20.00",
            method=self.cash_method,
        )

        allocations = RefundService.allocate_refund_for_appointment(appointment, 5000)
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0].payment, cash_payment)
        self.assertEqual(allocations[0].amount_minor, 5000)

    def test_allocate_raises_when_refund_exceeds_available(self):
        appointment = self._create_appointment()
        self._create_payment(
            appointment,
            amount="50.00",
            received="50.00",
            refunded="10.00",
            method=self.stripe_method,
            stripe_id="pi_card",
        )
        with self.assertRaises(RefundError):
            RefundService.allocate_refund_for_appointment(appointment, 5000)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], STRIPE_SECRET_KEY="sk_test_admin")
class PaymentRefundViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff_user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass",
        )
        cls.client_user = user_model.objects.create_user(
            username="client_view",
            email="client_view@example.com",
            password="pass1234",
        )
        cls.master_user = user_model.objects.create_user(
            username="master_view",
            email="master_view@example.com",
            password="pass1234",
        )
        cls.master_profile = MasterProfile.objects.create(user=cls.master_user.userprofile)
        cls.service = Service.objects.create(
            name="Facial",
            base_price=Decimal("150.00"),
            duration_min=75,
        )
        assign_service_room(cls.service, "Studio")
        cls.stripe_method, _ = PaymentMethod.objects.get_or_create(name="Stripe")

    def setUp(self):
        logged_in = self.client.login(username="admin", password="adminpass")
        self.assertTrue(logged_in)
        self.assertTrue(self.staff_user.is_staff)
        self.appointment = Appointment.objects.create(
            client=self.client_user.userprofile,
            start_time=timezone.now(),
        )
        self.item = AppointmentItem.objects.create(
            appointment=self.appointment,
            service=self.service,
            master=self.master_profile,
            start_time=timezone.now(),
            unit_price=Decimal("150.00"),
            final_price=Decimal("150.00"),
            tax_amount=Decimal("7.50"),
        )
        self.payment = Payment.objects.create(
            appointment=self.appointment,
            amount=Decimal("157.50"),
            amount_received=Decimal("157.50"),
            amount_refunded=Decimal("0.00"),
            method=self.stripe_method,
            status="succeeded",
            stripe_payment_intent_id="pi_test_refund",
            stripe_charge_id="ch_test_refund",
            captured_at=timezone.now(),
        )

    @patch("core.services.refunds.stripe.Refund.create")
    def test_refund_view_creates_stripe_refund(self, refund_create):
        refund_create.return_value = SimpleNamespace(id="re_test")
        url = reverse("admin-payment-refund", args=[self.payment.pk])
        pre_response = self.client.get(url)
        self.assertEqual(pre_response.status_code, 200)

        self.assertAlmostEqual(
            pre_response.context["summary"]["available"],
            Decimal("157.50"),
        )
        response = self.client.post(
            url,
            {
                "amount_to_refund": "50.00",
                "item_ids": [str(self.item.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith(url))
        self.assertEqual(PaymentRefund.objects.count(), 1)
        audit = PaymentRefund.objects.first()
        self.assertEqual(audit.amount, Decimal("50.00"))
        self.assertEqual(audit.method, PaymentRefund.METHOD_STRIPE)
        self.assertEqual(audit.stripe_refund_id, "re_test")
        self.assertEqual(audit.created_by, self.staff_user)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_refunded, Decimal("0.00"))
        refund_create.assert_called_once()
        _, kwargs = refund_create.call_args
        self.assertEqual(kwargs["amount"], 5000)
        self.assertEqual(kwargs.get("charge"), "ch_test_refund")

    def test_refund_view_validates_amount_limits(self):
        url = reverse("admin-payment-refund", args=[self.payment.pk])
        response = self.client.post(
            url,
            {
                "amount_to_refund": "999.00",
                "item_ids": [str(self.item.pk)],
            },
        )
        self.assertEqual(response.status_code, 200)
        form = response.context.get("form")
        self.assertIsNotNone(form)
        self.assertIn("amount_to_refund", form.errors)
        self.assertEqual(PaymentRefund.objects.count(), 0)

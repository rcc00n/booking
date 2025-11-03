from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Appointment, Payment, PaymentMethod, PaymentRefund
from core.receipts import generate_refund_receipt_pdf
from core.services.mailer import send_refund_receipt_email


class RefundReceiptTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        user_model = get_user_model()
        self.client_user = user_model.objects.create_user(
            username="refund-client@example.com",
            email="refund-client@example.com",
            password="secret123",
        )
        self.client_profile = self.client_user.userprofile
        self.method = PaymentMethod.objects.create(name="Card")
        self.appointment = Appointment.objects.create(
            client=self.client_profile,
            start_time=timezone.now(),
        )
        self.payment = Payment.objects.create(
            appointment=self.appointment,
            amount=Decimal("120.00"),
            currency="cad",
            method=self.method,
            status="succeeded",
            metadata={
                "cart_pricing": {
                    "currency": "cad",
                    "grand_total_minor": 12000,
                    "tax_minor": 2000,
                    "subtotal_minor": 10000,
                    "discount_minor": 0,
                    "service_fee_minor": 0,
                    "processing_fee_minor": 0,
                    "items": [
                        {
                            "name": "Therapy Session",
                            "total_minor": 12000,
                            "base_minor": 12000,
                            "discount_minor": 0,
                            "tax_minor": 2000,
                        },
                    ],
                },
            },
        )

    def _create_refund(self, amount: Decimal = Decimal("20.00")) -> PaymentRefund:
        with mock.patch("core.signals.email_refund_receipt_task.delay"), mock.patch(
            "core.signals.transaction.on_commit", side_effect=lambda cb, **kwargs: cb()
        ):
            return PaymentRefund.objects.create(
                appointment=self.appointment,
                payment=self.payment,
                amount=amount,
                amount_minor=int(amount * 100),
                method=PaymentRefund.METHOD_STRIPE,
            )

    def test_generate_refund_receipt_pdf_uses_refund_template(self):
        refund = self._create_refund()

        with mock.patch("core.receipts.render_to_string", return_value="<html></html>") as render_mock, mock.patch(
            "core.receipts.render_html_to_pdf", return_value=b"%PDF-1.4"
        ) as pdf_mock:
            pdf_bytes = generate_refund_receipt_pdf(refund)

        self.assertEqual(pdf_bytes, b"%PDF-1.4")
        render_mock.assert_called_once()
        template_name, context = render_mock.call_args.args[:2]
        self.assertEqual(template_name, "refund_receipt.html")
        self.assertEqual(context["receipt_number"], f"R-{refund.pk}")
        self.assertIn("refund", context)
        self.assertEqual(context["refund"]["amount"], refund.amount)
        self.assertEqual(context["refund"]["currency"], "CAD")
        pdf_mock.assert_called_once_with("<html></html>")

    def test_send_refund_receipt_email_attaches_pdf(self):
        refund = self._create_refund()

        with mock.patch("core.services.mailer.EmailMessage") as email_cls:
            email_instance = email_cls.return_value
            email_instance.send.return_value = 1
            ok = send_refund_receipt_email(refund, b"%PDF-1.4")

        self.assertTrue(ok)
        email_cls.assert_called_once()
        kwargs = email_cls.call_args.kwargs
        self.assertIn("to", kwargs)
        self.assertEqual(kwargs["to"], ["refund-client@example.com"])
        email_instance.attach.assert_called_once()
        attachment_args = email_instance.attach.call_args.args
        self.assertTrue(attachment_args[0].startswith("refund_receipt_"))
        self.assertEqual(attachment_args[2], "application/pdf")
        email_instance.send.assert_called_once_with(fail_silently=False)

    def test_send_refund_receipt_email_requires_client_email(self):
        user_model = get_user_model()
        anon_user = user_model.objects.create_user(
            username="no-email-user",
            email="",
            password="secret123",
        )
        anon_profile = anon_user.userprofile
        appointment = Appointment.objects.create(
            client=anon_profile,
            start_time=timezone.now(),
        )
        payment = Payment.objects.create(
            appointment=appointment,
            amount=Decimal("60.00"),
            currency="cad",
            method=self.method,
            status="succeeded",
            metadata={},
        )
        with mock.patch("core.signals.email_refund_receipt_task.delay"), mock.patch(
            "core.signals.transaction.on_commit", side_effect=lambda cb, **kwargs: cb()
        ):
            refund = PaymentRefund.objects.create(
                appointment=appointment,
                payment=payment,
                amount=Decimal("10.00"),
                amount_minor=1000,
                method=PaymentRefund.METHOD_CASH,
            )

        with mock.patch("core.services.mailer.EmailMessage") as email_cls:
            ok = send_refund_receipt_email(refund, b"%PDF-1.4")

        self.assertFalse(ok)
        email_cls.assert_not_called()

    def test_signal_enqueues_refund_email_task(self):
        callbacks = []

        def capture(callback, **kwargs):
            callbacks.append(callback)

        with mock.patch("core.signals.transaction.on_commit", side_effect=capture):
            refund = PaymentRefund.objects.create(
                appointment=self.appointment,
                payment=self.payment,
                amount=Decimal("15.00"),
                amount_minor=1500,
                method=PaymentRefund.METHOD_STRIPE,
            )

        self.assertEqual(len(callbacks), 1)

        with mock.patch("core.signals.email_refund_receipt_task.delay") as delay_mock:
            callbacks[0]()

        delay_mock.assert_called_once_with(str(refund.pk))

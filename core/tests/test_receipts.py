from __future__ import annotations

import shutil
import tempfile
import uuid
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from core.models import Appointment, Payment, PaymentMethod
from core.services import receipts
from core.tasks import email_payment_receipt_task


class PaymentReceiptServiceTests(TestCase):
    def setUp(self):
        super().setUp()
        self.media_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.media_dir, ignore_errors=True))
        override = self.settings(MEDIA_ROOT=self.media_dir)
        override.enable()
        self.addCleanup(override.disable)

    def _create_payment(self) -> Payment:
        method = PaymentMethod.objects.create(name="Card")
        return Payment.objects.create(
            amount=Decimal("25.50"),
            currency="cad",
            method=method,
            status="succeeded",
        )

    def test_persist_payment_receipt_idempotent(self):
        payment = self._create_payment()

        with mock.patch(
            "core.services.receipts.generate_payment_receipt_pdf",
            side_effect=[b"first", b"second"],
        ) as pdf_mock:
            path_one = receipts.persist_payment_receipt(str(payment.pk))
            payment.refresh_from_db()
            self.assertTrue(payment.receipt_pdf.name)
            self.assertTrue(path_one.endswith(".pdf"))
            payment.receipt_pdf.open("rb")
            self.assertEqual(payment.receipt_pdf.read(), b"first")
            payment.receipt_pdf.close()
            pdf_mock.assert_called_once()

            pdf_mock.reset_mock()
            path_two = receipts.persist_payment_receipt(str(payment.pk))
            self.assertEqual(path_one, path_two)
            pdf_mock.assert_not_called()

            result_force = receipts.persist_payment_receipt(str(payment.pk), force=True)
            payment.refresh_from_db()
            self.assertEqual(path_one, result_force)
            payment.receipt_pdf.open("rb")
            self.assertEqual(payment.receipt_pdf.read(), b"second")
            payment.receipt_pdf.close()
            pdf_mock.assert_called_once()


class PaymentReceiptTasksTests(TestCase):
    def setUp(self):
        super().setUp()
        self.media_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.media_dir, ignore_errors=True))
        override = self.settings(MEDIA_ROOT=self.media_dir)
        override.enable()
        self.addCleanup(override.disable)
        self.method = PaymentMethod.objects.create(name="Card")

    def _create_payment_with_appointment(self, *, email: str | None) -> Payment:
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=f"user-{uuid.uuid4()}",
            email=email or "",
            password="password123",
        )
        profile = user.userprofile
        appointment = Appointment.objects.create(
            client=profile,
            start_time=timezone.now(),
        )
        return Payment.objects.create(
            appointment=appointment,
            amount=Decimal("50.00"),
            currency="cad",
            method=self.method,
            status="succeeded",
        )

    def test_email_payment_receipt_task_skips_without_client_email(self):
        payment = self._create_payment_with_appointment(email=None)

        with mock.patch("core.tasks.generate_payment_receipt_pdf", return_value=b"mock"):
            with mock.patch("core.services.mailer.EmailMessage.send") as send_mail:
                email_payment_receipt_task(str(payment.pk))
                send_mail.assert_not_called()

        payment.refresh_from_db()
        self.assertIsNone(payment.receipt_sent_at)

    def test_email_payment_receipt_task_sends_and_marks_timestamp(self):
        payment = self._create_payment_with_appointment(email="client@example.com")
        payment.receipt_pdf.save("existing.pdf", ContentFile(b"mock-pdf"), save=True)
        payment.refresh_from_db()

        with mock.patch("core.tasks.generate_payment_receipt_pdf", return_value=b"regen-pdf") as pdf_mock:
            with mock.patch("core.tasks.send_payment_receipt_email") as send_mail:
                before = timezone.now()
                email_payment_receipt_task(str(payment.pk))
                payment.refresh_from_db()
                self.assertIsNotNone(payment.receipt_sent_at)
                self.assertGreaterEqual(payment.receipt_sent_at, before)
                send_mail.assert_called_once()
                args, _ = send_mail.call_args
                self.assertEqual(args[0].pk, payment.pk)
                self.assertEqual(args[1], b"mock-pdf")
                pdf_mock.assert_not_called()

                prev_sent = payment.receipt_sent_at
                send_mail.reset_mock()
                email_payment_receipt_task(str(payment.pk))
                send_mail.assert_not_called()
                pdf_mock.assert_not_called()

                send_mail.reset_mock()
                email_payment_receipt_task(str(payment.pk), force=True)
                payment.refresh_from_db()
                self.assertGreater(payment.receipt_sent_at, prev_sent)
                send_mail.assert_called_once()
                pdf_mock.assert_called_once()

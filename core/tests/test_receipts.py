from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import TestCase
from django.utils import timezone

from core.models import Appointment, AppointmentItem, MasterProfile, Payment, PaymentMethod, Service, ServiceCategory
from core.services import receipts
from core.tasks import email_payment_receipt_task
from core.payments import stripe_api
from core.tests.utils import assign_service_room


def _use_local_receipt_storage(testcase, media_dir: str) -> None:
    field = Payment._meta.get_field("receipt_pdf")
    original_storage = field.storage
    filesystem_storage = FileSystemStorage(location=media_dir)
    field.storage = filesystem_storage
    field._storage = filesystem_storage

    def _restore() -> None:
        field.storage = original_storage
        field._storage = original_storage

    testcase.addCleanup(_restore)


class PaymentReceiptServiceTests(TestCase):
    def setUp(self):
        super().setUp()
        self.media_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.media_dir, ignore_errors=True))
        override = self.settings(MEDIA_ROOT=self.media_dir)
        override.enable()
        self.addCleanup(override.disable)
        _use_local_receipt_storage(self, self.media_dir)
        receipt_patcher = mock.patch("core.services.receipts.render_html_to_pdf", return_value=b"%PDF-test")
        self.addCleanup(receipt_patcher.stop)
        receipt_patcher.start()
        receipt_task_patcher = mock.patch("core.signals.generate_payment_receipt_task.delay", return_value=None)
        self.addCleanup(receipt_task_patcher.stop)
        receipt_task_patcher.start()

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

    def test_build_payment_context_with_compact_metadata(self):
        payment = self._create_payment()
        pricing_snapshot = {
            "currency": "cad",
            "grand_total_minor": 12500,
            "tax_minor": 500,
            "processing_fee_minor": 250,
            "service_fee_minor": 0,
            "subtotal_minor": 11750,
            "discount_minor": 0,
            "item_count": 4,
            "items": [
                {"name": "Facial", "total_minor": 5000, "base_minor": 5000, "discount_minor": 0, "tax_minor": 200},
                {"name": "Massage", "total_minor": 4500, "base_minor": 4500, "discount_minor": 0, "tax_minor": 180},
                {"name": "Add-on", "total_minor": 2000, "base_minor": 2200, "discount_minor": 200, "tax_minor": 120},
                {"name": "Bonus", "total_minor": 1500, "base_minor": 1500, "discount_minor": 0},
            ],
        }
        payment.metadata = stripe_api._compact_cart_metadata(
            user_id=payment.pk,
            cart_id="cart-context",
            pricing=pricing_snapshot,
            cart_finalized=True,
        )
        payment.save(update_fields=["metadata"])

        context = receipts.build_payment_context(payment)
        self.assertEqual(len(context["items"]), 3)
        totals = context["totals"]
        self.assertEqual(totals.total, Decimal("125.00"))
        self.assertEqual(totals.processing_fee, Decimal("2.50"))

    def test_build_payment_context_without_metadata_uses_appointment(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="receipt-user@example.com",
            email="receipt-user@example.com",
            password="pass123",
        )
        profile = user.userprofile
        master_user = user_model.objects.create_user(
            username="master-receipt@example.com",
            email="master-receipt@example.com",
            password="pass123",
        )
        master_profile = MasterProfile.objects.create(user=master_user.userprofile)
        category = ServiceCategory.objects.create(name="Therapy")
        service = Service.objects.create(
            name="Therapy Session",
            base_price=Decimal("80.00"),
            duration_min=60,
            category=category,
        )
        assign_service_room(service, room_name="Receipt Room")
        appointment = Appointment.objects.create(
            client=profile,
            start_time=timezone.now(),
        )
        AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            unit_price=Decimal("80.00"),
            final_price=Decimal("80.00"),
            tax_amount=Decimal("4.00"),
            master=master_profile,
            start_time=timezone.now(),
        )

        payment = Payment.objects.create(
            appointment=appointment,
            amount=Decimal("84.00"),
            currency="cad",
            method=PaymentMethod.objects.create(name="Card"),
            status="succeeded",
            metadata={},
        )

        context = receipts.build_payment_context(payment)
        self.assertEqual(len(context["items"]), 1)
        totals = context["totals"]
        self.assertEqual(totals.total, Decimal("84.00"))
        self.assertEqual(totals.tax_total, Decimal("4.00"))


class PaymentReceiptTasksTests(TestCase):
    def setUp(self):
        super().setUp()
        self.media_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.media_dir, ignore_errors=True))
        override = self.settings(MEDIA_ROOT=self.media_dir)
        override.enable()
        self.addCleanup(override.disable)
        self.method = PaymentMethod.objects.create(name="Card")
        _use_local_receipt_storage(self, self.media_dir)
        receipt_patcher = mock.patch("core.services.receipts.render_html_to_pdf", return_value=b"%PDF-test")
        self.addCleanup(receipt_patcher.stop)
        receipt_patcher.start()
        receipt_task_patcher = mock.patch("core.signals.generate_payment_receipt_task.delay", return_value=None)
        self.addCleanup(receipt_task_patcher.stop)
        receipt_task_patcher.start()

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

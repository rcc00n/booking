from __future__ import annotations

from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from core import signals as core_signals
from core.models import (
    Appointment,
    AppointmentItem,
    MasterProfile,
    MasterRoom,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Service,
    ServiceMaster,
    UserProfile,
)


class PaymentRefundViewTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self._settings_override = self.settings(
            CELERY_BROKER_URL="memory://",
            CELERY_RESULT_BACKEND="cache+memory://",
            CELERY_TASK_ALWAYS_EAGER=True,
            CELERY_TASK_EAGER_PROPAGATES=True,
        )
        self._settings_override.enable()
        self.addCleanup(self._settings_override.disable)

        self._celery_patchers = [
            patch("core.tasks.generate_payment_receipt_task.delay", return_value=None),
            patch("core.tasks.email_payment_receipt_task.delay", return_value=None),
            patch("core.tasks.send_item_confirmation_email.delay", return_value=None),
            patch("core.tasks.send_item_cancellation_email.delay", return_value=None),
        ]
        for patcher in self._celery_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        post_save.disconnect(core_signals.trigger_receipt_pipeline, sender=Payment)
        self.addCleanup(
            lambda: post_save.connect(core_signals.trigger_receipt_pipeline, sender=Payment)
        )

        self.client.force_login(self._create_staff_user(with_permission=False))  # default login; individual tests adjust
        self.client.logout()

        self.client_profile = self._make_profile("refund-client@example.com")
        self.payment_status, _ = PaymentStatus.objects.get_or_create(name="Not Paid")
        self.appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=timezone.now(),
        )

        self.payment_method = PaymentMethod.objects.create(name="Card")
        self.payment = Payment.objects.create(
            appointment=self.appointment,
            amount=Decimal("120.00"),
            currency="cad",
            method=self.payment_method,
            status="succeeded",
        )

        service = Service.objects.create(
            name="Refundable Service",
            base_price=Decimal("120.00"),
            duration_min=60,
        )
        room = MasterRoom.objects.create(room="Refund Room")
        service.allowed_rooms.add(room)
        master_user = self.user_model.objects.create(username="refund-master")
        master_profile = MasterProfile.objects.create(user=UserProfile.objects.create(user=master_user))
        ServiceMaster.objects.create(service=service, master=master_profile)
        AppointmentItem.objects.create(
            appointment=self.appointment,
            service=service,
            master=master_profile,
            start_time=timezone.now(),
            unit_price=Decimal("120.00"),
        )

        self.superuser = self._create_staff_user(with_permission=True)
        self.staff_without_perm = self._create_staff_user(with_permission=False, username_suffix="noperm")

    def _make_profile(self, username: str) -> UserProfile:
        user = self.user_model.objects.create(username=username, email=username)
        return UserProfile.objects.create(user=user)

    def _create_staff_user(self, *, with_permission: bool, username_suffix: str | None = None):
        username = f"staff-{username_suffix or uuid4().hex[:6]}"
        user = self.user_model.objects.create(username=username, email=f"{username}@example.com")
        user.is_staff = True
        user.is_superuser = with_permission
        user.save(update_fields=["is_staff", "is_superuser"])
        return user

    def test_url_resolves_to_view(self) -> None:
        match = resolve(f"/admin/core/payment/{self.payment.pk}/refund/")
        self.assertEqual(match.view_name, "admin-payment-refund")

    def test_view_requires_change_payment_permission(self) -> None:
        self.client.force_login(self.staff_without_perm)
        response = self.client.get(reverse("admin-payment-refund", args=[self.payment.pk]))
        self.assertEqual(response.status_code, 403)

    def test_view_redirects_anonymous_users(self) -> None:
        response = self.client.get(reverse("admin-payment-refund", args=[self.payment.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.headers["Location"])

    def test_view_renders_for_authorized_staff(self) -> None:
        pricing_payload = {
            "currency_symbol": "CA$",
            "items": [
                {"id": str(uuid4()), "name": "Service", "total_with_tax": Decimal("120.00"), "master": "A"}
            ],
            "product_sales": [],
            "totals": {"grand_total": Decimal("120.00")},
        }

        self.client.force_login(self.superuser)

        with patch("core.views.compute_appointment_pricing", return_value=pricing_payload), patch(
            "core.views.payment_services.get_total_received_for_appointment",
            return_value=Decimal("120.00"),
        ):
            response = self.client.get(reverse("admin-payment-refund", args=[self.payment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/payment_refund.html")
        self.assertEqual(response.context["payment"].pk, self.payment.pk)
        self.assertIn("summary", response.context)

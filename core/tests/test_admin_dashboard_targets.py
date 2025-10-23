from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentItem,
    MasterMonthlySalesTarget,
    MasterProfile,
    Payment,
    PaymentMethod,
    Service,
    UserProfile,
)


class AdminDashboardTargetsTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.month_start = timezone.localdate().replace(day=1)
        self.payment_method = PaymentMethod.objects.create(name="Card")
        self.service = Service.objects.create(
            name="Consultation",
            base_price=Decimal("100.00"),
            duration_min=60,
        )

    def _create_master(self, username: str, target_amount: Decimal | None) -> tuple:
        user = self.user_model.objects.create_user(
            username=username,
            password="pass",
            is_staff=True,
            is_active=True,
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        master = MasterProfile.objects.create(user=profile)
        if target_amount is not None:
            MasterMonthlySalesTarget.objects.create(
                master=master,
                month=self.month_start,
                target_amount=target_amount,
            )
        return user, master

    def _book_and_pay(self, master: MasterProfile, amount: Decimal) -> None:
        client_user = self.user_model.objects.create_user(
            username=f"client_{master.pk}",
            password="pass",
        )
        client_profile, _ = UserProfile.objects.get_or_create(user=client_user)
        start = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        appointment = Appointment.objects.create(
            client=client_profile,
            start_time=start,
        )
        AppointmentItem.objects.create(
            appointment=appointment,
            service=self.service,
            master=master,
            start_time=start,
            final_price=amount,
        )
        payment = Payment.objects.create(
            appointment=appointment,
            amount=amount,
            method=self.payment_method,
            status="succeeded",
        )
        Payment.objects.filter(pk=payment.pk).update(created_at=start)

    def test_admin_sees_monthly_targets_progress(self):
        admin_user = self.user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="pass",
        )
        self.client.force_login(admin_user)

        _, master_with_target = self._create_master("master_with_target", Decimal("1500.00"))
        _, master_without_target = self._create_master("master_without_target", None)
        self._book_and_pay(master_with_target, Decimal("1000.00"))

        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

        rows = response.context["master_target_rows"]
        self.assertGreaterEqual(len(rows), 2)

        with_target = next(row for row in rows if row["master"] == master_with_target)
        self.assertEqual(with_target["target_amount"], Decimal("1500.00"))
        self.assertEqual(with_target["achieved_amount"], Decimal("1000.00"))
        self.assertEqual(with_target["remaining_amount"], Decimal("500.00"))

        without_target = next(row for row in rows if row["master"] == master_without_target)
        self.assertIsNone(without_target["target_amount"])
        self.assertEqual(without_target["achieved_amount"], Decimal("0"))
        self.assertIsNone(without_target["remaining_amount"])

        label = response.context["master_target_month_label"]
        self.assertIn(self.month_start.strftime("%B"), label)

    def test_master_sees_personal_target_summary(self):
        master_user, master = self._create_master("lead_master", Decimal("800.00"))
        self._book_and_pay(master, Decimal("500.00"))

        self.client.force_login(master_user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

        entry = response.context["master_target_for_current_user"]
        self.assertIsNotNone(entry)
        self.assertEqual(entry["target_amount"], Decimal("800.00"))
        self.assertEqual(entry["achieved_amount"], Decimal("500.00"))
        self.assertEqual(entry["remaining_amount"], Decimal("300.00"))

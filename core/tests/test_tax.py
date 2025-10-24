
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentItem,
    MasterProfile,
    PaymentStatus,
    Product,
    ProductSale,
    Service,
    UserProfile,
)
from core.services.pricing import compute_appointment_pricing


@override_settings(GST_PERCENT=Decimal("5.0"), GST_ENABLED=True)
class AppointmentTaxTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client_user = User.objects.create_user(username="client", password="test")
        self.client_profile = UserProfile.objects.create(user=self.client_user)

        self.master_user = User.objects.create_user(username="master", password="test")
        self.master_profile = UserProfile.objects.create(user=self.master_user)
        self.master = MasterProfile.objects.create(user=self.master_profile)

        self.payment_status = PaymentStatus.objects.create(name="Not Paid")

    def _create_service(self, *, is_taxable: bool) -> Service:
        return Service.objects.create(
            name="Service",
            base_price=Decimal("100.00"),
            duration_min=60,
            is_taxable=is_taxable,
        )

    def _create_appointment(self) -> Appointment:
        return Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=timezone.now(),
        )

    def test_taxable_service_records_item_tax(self):
        service = self._create_service(is_taxable=True)
        appointment = self._create_appointment()

        item = AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=self.master,
            start_time=timezone.now(),
        )

        appointment.recompute_totals(save=True)
        item.refresh_from_db()
        appointment.refresh_from_db()

        self.assertEqual(item.tax_amount, Decimal("5.00"))
        self.assertEqual(appointment.tax_amount, Decimal("5.00"))
        self.assertEqual(appointment.card_processing_fee, Decimal("3.65"))
        self.assertEqual(appointment.final_price, Decimal("108.65"))

    def test_appointment_totals_include_product_sales_tax(self):
        service = self._create_service(is_taxable=True)
        appointment = self._create_appointment()

        AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=self.master,
            start_time=timezone.now(),
        )

        product = Product.objects.create(
            name="Retail",
            price=Decimal("20.00"),
            quantity_in_stock=10,
        )

        sale = ProductSale.objects.create(
            product=product,
            sold_by=self.master_profile,
            client=self.client_profile,
            appointment=appointment,
            quantity=1,
            unit_price=Decimal("20.00"),
        )

        appointment.recompute_totals(save=True)
        sale.refresh_from_db()
        appointment.refresh_from_db()

        self.assertEqual(sale.tax_amount, Decimal("1.00"))
        self.assertEqual(appointment.tax_amount, Decimal("6.00"))
        self.assertEqual(appointment.card_processing_fee, Decimal("4.28"))
        self.assertEqual(appointment.final_price, Decimal("130.28"))


class AppointmentPricingSnapshotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client_user = User.objects.create_user(username="client", password="test")
        self.client_profile = UserProfile.objects.create(user=self.client_user, personal_discount_percent=10)

        self.master_user = User.objects.create_user(username="master", password="test")
        self.master_profile = UserProfile.objects.create(user=self.master_user)
        self.master = MasterProfile.objects.create(user=self.master_profile)

        self.payment_status = PaymentStatus.objects.create(name="Not Paid")

    def test_compute_appointment_pricing_includes_discounts_and_fee(self):
        service = Service.objects.create(
            name="Service",
            base_price=Decimal("100.00"),
            duration_min=60,
            is_taxable=True,
        )

        appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=timezone.now(),
        )

        AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=self.master,
            start_time=timezone.now(),
        )

        appointment.recompute_totals(save=True)
        appointment.refresh_from_db()

        snapshot = compute_appointment_pricing(appointment)
        totals = snapshot["totals"]
        summary = snapshot["summary"]

        self.assertEqual(totals["services_subtotal"], Decimal("90.00"))
        self.assertEqual(totals["discount_total"], Decimal("10.00"))
        self.assertGreater(totals["processing_fee"], Decimal("0.00"))
        self.assertEqual(summary.get("personal_discount_percent"), 10)
        self.assertIn("personal", summary.get("discount_tags", {}))

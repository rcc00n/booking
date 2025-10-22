
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
        self.assertEqual(appointment.final_price, Decimal("105.00"))

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
        self.assertEqual(appointment.final_price, Decimal("126.00"))

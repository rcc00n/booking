
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from core.models import (
    Appointment,
    AppointmentItem,
    MasterProfile,
    PaymentStatus,
    Product,
    ProductSale,
    Service,
    UserProfile,
    Payment,
    PaymentMethod,
)
from core.tests.utils import assign_service_room
from core.services.pricing import compute_appointment_pricing
from core.admin import PaymentAdmin


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
        service = Service.objects.create(
            name="Service",
            base_price=Decimal("100.00"),
            duration_min=60,
            is_taxable=is_taxable,
        )
        assign_service_room(service, room_name=f"Tax Service {'T' if is_taxable else 'NT'}")
        return service

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
        self.assertFalse(appointment.apply_card_processing_fee)
        self.assertEqual(appointment.card_processing_fee, Decimal("0.00"))
        self.assertEqual(appointment.final_price, Decimal("105.00"))

    def test_enabling_card_fee_updates_totals(self):
        service = self._create_service(is_taxable=True)
        appointment = self._create_appointment()

        AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=self.master,
            start_time=timezone.now(),
        )

        appointment.apply_card_processing_fee = True
        appointment.card_processing_fee = Decimal("0.00")
        appointment.recompute_totals(save=True)
        appointment.refresh_from_db()

        self.assertTrue(appointment.apply_card_processing_fee)
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
        self.assertEqual(appointment.card_processing_fee, Decimal("0.00"))
        self.assertEqual(appointment.final_price, Decimal("126.00"))


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
        assign_service_room(service, room_name="Pricing Snapshot Room")

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

        appointment.apply_card_processing_fee = True
        appointment.card_processing_fee = Decimal("0.00")
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


class AdminPayFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass",
        )
        self.client.force_login(self.superuser)
        self.factory = RequestFactory()

        self.client_user = User.objects.create_user(username="pay_client", password="test")
        self.client_profile = UserProfile.objects.create(user=self.client_user)

        self.master_user = User.objects.create_user(username="pay_master", password="test")
        self.master_profile = MasterProfile.objects.create(user=self.master_user.userprofile)

        self.payment_status = PaymentStatus.objects.create(name="Not Paid")
        PaymentMethod.objects.get_or_create(name="Cash")
        PaymentMethod.objects.get_or_create(name="E-transfer")

        self.service = Service.objects.create(
            name="Card Fee Eligible",
            base_price=Decimal("100.00"),
            duration_min=60,
            is_taxable=True,
        )
        assign_service_room(self.service, room_name="Admin PayFlow Room")

    def _build_appointment(self) -> Appointment:
        appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=timezone.now(),
        )
        AppointmentItem.objects.create(
            appointment=appointment,
            service=self.service,
            master=self.master_profile,
            start_time=timezone.now(),
        )
        appointment.recompute_totals(save=True)
        return appointment

    def test_enable_card_fee_endpoint_applies_surcharge(self):
        appointment = self._build_appointment()
        url = reverse("admin:core_appointment_enable_card_fee", args=[appointment.pk])

        response = self.client.post(url, data={}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        appointment.refresh_from_db()
        self.assertTrue(appointment.apply_card_processing_fee)
        self.assertEqual(appointment.card_processing_fee, Decimal("3.65"))
        self.assertEqual(appointment.final_price, Decimal("108.65"))

    def test_payment_admin_prefills_from_query_params(self):
        appointment = self._build_appointment()
        payment_admin = PaymentAdmin(Payment, admin.site)
        request = self.factory.get(
            "/admin/core/payment/add/",
            {
                "appointment": str(appointment.pk),
                "amount": "150.25",
                "method_hint": "cash",
            },
        )
        request.user = self.superuser

        initial = payment_admin.get_changeform_initial_data(request)

        self.assertEqual(initial["appointment"], appointment)
        self.assertEqual(initial["amount"], Decimal("150.25"))
        self.assertEqual(initial["method"].name, "Cash")

from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.forms import AppointmentProductSaleForm
from core.models import Product, UserProfile


class AppointmentProductSaleFormTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username="staff",
            password="pass",
            is_staff=True,
            is_active=True,
        )
        self.staff_profile = UserProfile.objects.create(user=self.staff_user)
        self.product = Product.objects.create(
            name="Hydrating Serum",
            price=Decimal("42.50"),
            quantity_in_stock=10,
            is_active=True,
        )
        self.request = SimpleNamespace(user=self.staff_user)

    def _base_payload(self) -> dict[str, str]:
        return {
            "product": str(self.product.pk),
            "sold_by": str(self.staff_profile.pk),
            "client": "",
            "quantity": "1",
            "notes": "",
            "unit_price": "",
        }

    def test_unit_price_defaults_to_product_price_when_blank(self):
        form = AppointmentProductSaleForm(
            data=self._base_payload(),
            request=self.request,
            appointment=None,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["unit_price"], Decimal("42.50"))

    def test_manual_unit_price_is_accepted(self):
        payload = self._base_payload()
        payload["unit_price"] = "12.35"
        form = AppointmentProductSaleForm(
            data=payload,
            request=self.request,
            appointment=None,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["unit_price"], Decimal("12.35"))

    def test_negative_unit_price_rejected(self):
        payload = self._base_payload()
        payload["unit_price"] = "-1"
        form = AppointmentProductSaleForm(
            data=payload,
            request=self.request,
            appointment=None,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Unit price cannot be negative.", form.errors["unit_price"])

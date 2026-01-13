from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from unittest import mock

from accounts.forms import (
    AccountPasswordResetForm,
    AccountSetPasswordForm,
    ClientLoginForm,
    ClientProfileForm,
    ClientRegistrationForm,
    HealthConditionsForm,
    ProductSaleForm,
)
from core.models import Product, Role, UserProfile, UserRole


class ClientRegistrationFormTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        Role.objects.get_or_create(name="Client")

    def _valid_payload(self) -> dict[str, object]:
        today = date.today()
        adult_birth = today - timedelta(days=365 * 25)
        return {
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
            "phone": "+1 403 555 0101",
            "birth_date": adult_birth.strftime("%Y-%m-%d"),
            "how_heard": "google",
            "email_marketing_consent": True,
            "data_processing_consent": True,
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        }

    def test_successful_registration_persists_profile_and_role(self) -> None:
        form = ClientRegistrationForm(data=self._valid_payload())
        self.assertTrue(form.is_valid(), form.errors)

        user = form.save()

        self.assertEqual(user.username, "+14035550101")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.phone, "+14035550101")
        self.assertEqual(profile.how_heard, "google")
        self.assertTrue(profile.email_marketing_consent)
        self.assertIsNotNone(profile.email_marketing_consented_at)
        self.assertTrue(UserRole.objects.filter(user=profile, role__name="Client").exists())

    def test_duplicate_email_is_rejected(self) -> None:
        existing = self.user_model.objects.create_user(
            username="+14035550000",
            email="alice@example.com",
            password="StrongPass123!",
        )
        UserProfile.objects.create(user=existing, phone="+14035550000")

        form = ClientRegistrationForm(data=self._valid_payload())
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_duplicate_phone_in_user_table_is_rejected(self) -> None:
        existing = self.user_model.objects.create_user(
            username="+14035550101",
            email="other@example.com",
            password="StrongPass123!",
        )
        UserProfile.objects.create(user=existing, phone="+14035550101")

        payload = self._valid_payload()
        payload["phone"] = "+1 (403) 555-0101"
        form = ClientRegistrationForm(data=payload)

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_duplicate_phone_in_profile_table_is_rejected(self) -> None:
        existing = self.user_model.objects.create_user(
            username="+14035550202",
            email="other2@example.com",
            password="StrongPass123!",
        )
        UserProfile.objects.create(user=existing, phone="+14035550101")

        payload = self._valid_payload()
        payload["phone"] = "+1 (403) 555-0101"
        form = ClientRegistrationForm(data=payload)

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_birth_date_must_be_adult(self) -> None:
        payload = self._valid_payload()
        payload["birth_date"] = (date.today() - timedelta(days=365 * 15)).strftime("%Y-%m-%d")
        form = ClientRegistrationForm(data=payload)

        self.assertFalse(form.is_valid())
        self.assertIn("birth_date", form.errors)

    def test_future_birth_date_is_rejected(self) -> None:
        payload = self._valid_payload()
        payload["birth_date"] = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        form = ClientRegistrationForm(data=payload)

        self.assertFalse(form.is_valid())
        self.assertIn("birth_date", form.errors)

    def test_data_processing_consent_is_required(self) -> None:
        payload = self._valid_payload()
        payload["data_processing_consent"] = False
        form = ClientRegistrationForm(data=payload)

        self.assertFalse(form.is_valid())
        self.assertIn("data_processing_consent", form.errors)

    def test_existing_profile_is_updated_on_save(self) -> None:
        user = self.user_model.objects.create_user(
            username="+14035550000",
            email="old@example.com",
            password="OldPass123!",
        )
        profile = UserProfile.objects.create(
            user=user,
            phone="+14035550000",
            birth_date=date(1990, 1, 1),
            how_heard="friend",
            email_marketing_consent=False,
        )

        payload = self._valid_payload()
        payload["email"] = "fresh@example.com"
        payload["phone"] = "+1 825 555 0102"
        form = ClientRegistrationForm(data=payload, instance=user)
        self.assertTrue(form.is_valid(), form.errors)

        saved_user = form.save()

        profile.refresh_from_db()
        self.assertEqual(saved_user.pk, user.pk)
        self.assertEqual(profile.phone, "+18255550102")
        self.assertEqual(profile.how_heard, "google")
        self.assertTrue(profile.email_marketing_consent)
        self.assertEqual(saved_user.email, "fresh@example.com")


class ClientLoginFormTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.factory = RequestFactory()
        self.user = self.user_model.objects.create_user(
            username="+14035550101",
            email="login@example.com",
            password="StrongPass123!",
        )
        UserProfile.objects.create(user=self.user, phone="+14035550101")

    def test_candidate_identifiers_generate_expected_variants(self) -> None:
        form = ClientLoginForm()
        candidates = form._candidate_identifiers("Test.User+1@example.com")

        self.assertIn("test.user+1@example.com", candidates)
        self.assertIn("Test.User+1@example.com", candidates)
        self.assertIn("TestUser+1@examplecom", candidates)
        self.assertIn("1", candidates)
        self.assertEqual(candidates[0], "Test.User+1@example.com")

    def test_clean_accepts_phone_variants(self) -> None:
        data = {"username": "403 555-0101", "password": "StrongPass123!"}
        request = self.factory.post("/login/", data)
        form = ClientLoginForm(request=request, data=data)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.get_user(), self.user)

    def test_clean_rejects_unknown_credentials(self) -> None:
        data = {"username": "unknown@example.com", "password": "WrongPass!"}
        request = self.factory.post("/login/", data)
        form = ClientLoginForm(request=request, data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_candidate_identifiers_for_phone_number_variants(self) -> None:
        form = ClientLoginForm()
        candidates = form._candidate_identifiers("(403) 555-0101")

        self.assertIn("+14035550101", candidates)
        self.assertIn("4035550101", candidates)
        self.assertEqual(candidates[0], "(403) 555-0101")


class AccountFormStylingTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="styling@example.com",
            email="styling@example.com",
            password="StrongPass123!",
        )

    def test_password_reset_form_widgets(self) -> None:
        form = AccountPasswordResetForm()
        self.assertEqual(form.fields["email"].widget.attrs["placeholder"], "you@example.com")
        self.assertEqual(form.fields["email"].widget.attrs["autocomplete"], "email")
        self.assertEqual(form.fields["email"].widget.attrs["class"], "auth-input")

    def test_set_password_form_widgets(self) -> None:
        form = AccountSetPasswordForm(user=self.user)
        attrs = form.fields["new_password1"].widget.attrs
        self.assertEqual(attrs.get("autocomplete"), "new-password")
        self.assertEqual(attrs.get("class"), "auth-input")
        self.assertEqual(
            form.fields["new_password2"].widget.attrs.get("class"),
            "auth-input",
        )


class AccountSetPasswordFormValidationTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="reuse@example.com",
            email="reuse@example.com",
            password="OldPassword123!",
        )

    def test_reusing_current_password_is_rejected(self) -> None:
        form = AccountSetPasswordForm(
            user=self.user,
            data={
                "new_password1": "OldPassword123!",
                "new_password2": "OldPassword123!",
            },
        )

        self.assertFalse(form.is_valid())
        error = form.errors["new_password2"].as_data()[0]
        self.assertEqual(error.code, "password_no_change")
        self.assertIn("different from your current password", str(error))

    def test_setting_new_password_succeeds(self) -> None:
        form = AccountSetPasswordForm(
            user=self.user,
            data={
                "new_password1": "FreshPassword456!",
                "new_password2": "FreshPassword456!",
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("FreshPassword456!"))


class ClientProfileFormTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="profile@example.com",
            email="profile@example.com",
            password="StrongPass123!",
            first_name="Existing",
            last_name="User",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            phone="+14035558888",
            birth_date=date(1990, 1, 1),
            how_heard="google",
            email_marketing_consent=False,
        )

    def _form_payload(self) -> dict[str, object]:
        return {
            "first_name": "Updated",
            "last_name": "Person",
            "email": "new@example.com",
            "phone": "(403) 555-9999",
            "birth_date": "1992-05-15",
            "address": "123 Main St\nUnit 4",
            "postal_code": "T2X1A1",
            "how_heard": "friend",
            "email_marketing_consent": True,
        }

    def test_profile_update_normalizes_and_persists(self) -> None:
        form = ClientProfileForm(data=self._form_payload(), user=self.user)
        self.assertTrue(form.is_valid(), form.errors)

        returned_user = form.save()

        self.assertEqual(returned_user.first_name, "Updated")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.phone, "+14035559999")
        self.assertEqual(self.profile.postal_code, "T2X1A1")
        self.assertTrue(self.profile.email_marketing_consent)
        self.assertIsNotNone(self.profile.email_marketing_consented_at)
        self.assertEqual(self.profile.billing_contact["name"], "Updated Person")
        self.assertEqual(self.profile.billing_contact["address_line2"], "Unit 4")
        self.assertEqual(self.profile.billing_contact["postal_code"], "T2X1A1")
        self.assertEqual(self.profile.billing_contact["email"], "new@example.com")
        self.assertEqual(self.profile.billing_contact["phone"], "+14035559999")
        self.assertIsNotNone(self.profile.billing_contact_updated_at)

    def test_email_uniqueness_validation(self) -> None:
        other_user = get_user_model().objects.create_user(
            username="other@example.com",
            email="duplicated@example.com",
            password="StrongPass123!",
        )
        UserProfile.objects.create(user=other_user, phone="+14035557771")
        payload = self._form_payload()
        payload["email"] = "duplicated@example.com"

        form = ClientProfileForm(data=payload, user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_invalid_phone_format_is_rejected(self) -> None:
        payload = self._form_payload()
        payload["phone"] = "invalid"

        form = ClientProfileForm(data=payload, user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_birth_date_in_future_is_rejected(self) -> None:
        payload = self._form_payload()
        payload["birth_date"] = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")

        form = ClientProfileForm(data=payload, user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("birth_date", form.errors)

    def test_birth_date_underage_is_rejected(self) -> None:
        payload = self._form_payload()
        payload["birth_date"] = (date.today() - timedelta(days=365 * 17)).strftime("%Y-%m-%d")

        form = ClientProfileForm(data=payload, user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("birth_date", form.errors)

    def test_invalid_postal_code_raises_error(self) -> None:
        payload = self._form_payload()
        payload["postal_code"] = "12345"

        form = ClientProfileForm(data=payload, user=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn("postal_code", form.errors)

    def test_blank_postal_code_returns_empty_string(self) -> None:
        payload = self._form_payload()
        payload["postal_code"] = ""

        form = ClientProfileForm(data=payload, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)

        form.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.postal_code, "")

    def test_save_without_address_clears_billing_lines(self) -> None:
        payload = self._form_payload()
        payload["address"] = ""

        form = ClientProfileForm(data=payload, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)

        form.save()
        self.profile.refresh_from_db()
        self.assertNotIn("address_line1", self.profile.billing_contact)
        self.assertNotIn("address_line2", self.profile.billing_contact)


class HealthConditionsFormTests(SimpleTestCase):
    def test_to_json_serializes_lists(self) -> None:
        form = HealthConditionsForm(
            data={
                "allergies": "Lidocaine,  Cats ",
                "medications": "",
                "contraindications": "None",
                "chronic": "Asthma",
                "surgeries": "",
                "notes": "Additional notes",
            }
        )
        self.assertTrue(form.is_valid())

        payload = form.to_json()
        self.assertEqual(payload["allergies"], ["Lidocaine", "Cats"])
        self.assertEqual(payload["contraindications"], ["None"])
        self.assertEqual(payload["notes"], "Additional notes")

    def test_load_initial_from_json_populates_fields(self) -> None:
        form = HealthConditionsForm()
        form.load_initial_from_json(
            {
                "allergies": ["Cats"],
                "medications": ["Ibuprofen"],
                "contraindications": [],
                "notes": "Observations",
            }
        )
        self.assertEqual(form.initial["allergies"], "Cats")
        self.assertEqual(form.initial["medications"], "Ibuprofen")
        self.assertEqual(form.initial["notes"], "Observations")


class ProductSaleFormTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.employee_user = self.user_model.objects.create_user(
            username="employee@example.com",
            email="employee@example.com",
            password="StrongPass123!",
        )
        self.employee_profile = UserProfile.objects.create(user=self.employee_user, phone="+14035557777")

        self.product = Product.objects.create(
            name="Serum",
            price=Decimal("49.00"),
            quantity_in_stock=10,
        )

    def test_clean_unit_price_defaults_to_product_price(self) -> None:
        form = ProductSaleForm(
            data={
                "product": self.product.pk,
                "client": "",
                "quantity": 2,
                "unit_price": "",
                "sold_at": "2025-01-01T12:00",
                "notes": "",
            },
            employee_profile=self.employee_profile,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["unit_price"], Decimal("49.00"))

    def test_quantity_validation_against_stock(self) -> None:
        form = ProductSaleForm(
            data={
                "product": self.product.pk,
                "client": "",
                "quantity": 99,
                "unit_price": "",
                "sold_at": "2025-01-01T12:00",
                "notes": "",
            },
            employee_profile=self.employee_profile,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)

    def test_clean_sold_at_defaults_to_now_for_empty_input(self) -> None:
        fixed = timezone.make_aware(datetime(2025, 1, 10, 8, 30))
        with mock.patch("accounts.forms.timezone.now", return_value=fixed):
            form = ProductSaleForm(
                data={
                    "product": self.product.pk,
                    "client": "",
                    "quantity": 1,
                    "unit_price": "",
                    "sold_at": "",
                    "notes": "",
                },
                employee_profile=self.employee_profile,
            )
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["sold_at"], fixed)

    def test_clean_sold_at_converts_naive_datetime_to_aware(self) -> None:
        naive = datetime(2025, 1, 5, 9, 45)
        form = ProductSaleForm(
            data={
                "product": self.product.pk,
                "client": "",
                "quantity": 1,
                "unit_price": "",
                "sold_at": naive.strftime("%Y-%m-%dT%H:%M"),
                "notes": "",
            },
            employee_profile=self.employee_profile,
        )
        self.assertTrue(form.is_valid(), form.errors)
        sold_at = form.cleaned_data["sold_at"]
        self.assertTrue(timezone.is_aware(sold_at))
        self.assertEqual(sold_at.replace(tzinfo=None), naive)

    def test_unbound_form_prefills_sold_at_initial(self) -> None:
        fixed = timezone.make_aware(datetime(2024, 12, 25, 14, 0))
        with mock.patch("accounts.forms.timezone.now", return_value=fixed):
            with mock.patch("accounts.forms.timezone.localtime", return_value=fixed):
                form = ProductSaleForm(employee_profile=self.employee_profile)
        self.assertEqual(form.fields["sold_at"].initial, "2024-12-25T14:00")

    def test_save_creates_sale_and_updates_stock(self) -> None:
        form = ProductSaleForm(
            data={
                "product": self.product.pk,
                "client": "",
                "quantity": 3,
                "unit_price": "",
                "sold_at": "2025-01-01T09:00",
                "notes": "Sold after consultation",
            },
            employee_profile=self.employee_profile,
        )
        self.assertTrue(form.is_valid(), form.errors)

        sale = form.save()

        self.assertEqual(sale.sold_by, self.employee_profile)
        self.assertEqual(sale.quantity, 3)
        self.assertEqual(sale.unit_price, Decimal("49.00"))
        self.assertEqual(sale.notes, "Sold after consultation")
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_in_stock, 7)

    def test_save_without_employee_profile_raises(self) -> None:
        form = ProductSaleForm(
            data={
                "product": self.product.pk,
                "client": "",
                "quantity": 1,
                "unit_price": "",
                "sold_at": "2025-01-01T12:00",
                "notes": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        with self.assertRaises(ValidationError):
            form.save()

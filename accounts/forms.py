from __future__ import annotations

from django import forms
from decimal import Decimal
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.utils import timezone

import phonenumbers

from core.models import (
    CustomUserDisplay,
    UserProfile,
    Role,
    HowHeard,  # TextChoices со значениями источников
    Product,
    ProductSale,
)
from core.forms import _normalize_phone
from core.validators import clean_ab_postal_code


# ---------- Registration ----------
class ClientRegistrationForm(UserCreationForm):
    """
    Регистрация клиента: e-mail, телефон + пароль.
    Username берётся из нормализованного номера телефона (как в админке).
    После save():
        • создаёт UserProfile (включая how_heard / email_marketing_consent),
        • назначает роль «Client».
    """

    first_name = forms.CharField(
        required=True,
        max_length=150,
        label="First name",
        error_messages={"required": "First name is required."},
    )

    last_name = forms.CharField(
        required=True,
        max_length=150,
        label="Last name",
        error_messages={"required": "Last name is required."},
    )

    email = forms.EmailField(required=True, label="E-mail")

    # Визуально предзаполняем +1 и показываем формат;
    # валидацию/нормализацию делаем в clean_phone()
    phone = forms.CharField(
        max_length=20,
        label="Phone",
        initial="+1 ",
        widget=forms.TextInput(attrs={"placeholder": "(555) 123-4567"})
    )

    birth_date = forms.DateField(
        required=True,
        label="Date of birth",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
        error_messages={"required": "Date of birth is required."},
    )

    how_heard = forms.ChoiceField(
        required=False, label="How did you hear about us?",
        choices=[("", "— Select —")] + list(HowHeard.choices)
    )

    email_marketing_consent = forms.BooleanField(
        required=False,
        label="I agree to receive e-mail updates and offers and consent to the processing of my personal data",
    )

    data_processing_consent = forms.BooleanField(
        required=True,
        label="I consent to the processing of my personal data according to the Privacy Notice.",
        error_messages={"required": "You must consent to the processing of personal data to continue."},
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUserDisplay
        fields = (
            "first_name", "last_name", "email", "phone", "birth_date",
            "how_heard", "email_marketing_consent",
            "password1", "password2"
        )

    # --- Validation helpers ---

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").lower().strip()
        if CustomUserDisplay.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This e-mail is already in use.")
        return email

    def clean_phone(self):
        try:
            phone = _normalize_phone(self.cleaned_data.get("phone", ""))
        except ValidationError as exc:
            raise forms.ValidationError(exc.message)

        qs = CustomUserDisplay.objects.filter(username=phone)
        instance_pk = getattr(self.instance, "pk", None)
        if instance_pk:
            qs = qs.exclude(pk=instance_pk)
        if qs.exists():
            raise forms.ValidationError("This phone number is already in use.")

        profile_qs = UserProfile.objects.filter(phone=phone)
        if instance_pk:
            profile_qs = profile_qs.exclude(user_id=instance_pk)
        if profile_qs.exists():
            raise forms.ValidationError("This phone number is already in use.")
        return phone

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get("birth_date")
        if not birth_date:
            return birth_date

        today = timezone.now().date()
        if birth_date > today:
            raise forms.ValidationError("Birth date cannot be in the future.")

        age = today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )
        if age < 18:
            raise forms.ValidationError("You must be at least 18 years old to create an account.")

        return birth_date

    # --- Save ---

    def save(self, commit=True):
        user = super().save(commit=False)

        phone = self.cleaned_data["phone"]
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.username = phone

        if commit:
            user.save()

            birth_date = self.cleaned_data.get("birth_date")
            how_heard = self.cleaned_data.get("how_heard") or ""

            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "phone": phone,
                    "birth_date": birth_date,
                    "how_heard": how_heard,
                },
            )
            if not created:
                profile.phone = phone
                profile.birth_date = birth_date
                profile.how_heard = how_heard

            consent = bool(self.cleaned_data.get("email_marketing_consent"))
            profile.set_marketing_consent(consent)
        profile.save(update_fields=[
            "phone", "birth_date", "how_heard",
            "email_marketing_consent", "email_marketing_consented_at",
        ])

        client_role, _ = Role.objects.get_or_create(name="Client")
        profile.userrole_set.get_or_create(role=client_role)

        return user

    def clean_data_processing_consent(self):
        consent = self.cleaned_data.get("data_processing_consent")
        if not consent:
            raise forms.ValidationError(
                "You must consent to the processing of personal data to create an account."
            )
        return consent


# ---------- Login ----------
class ClientLoginForm(AuthenticationForm):
    """
    Один input «identifier»:
        • username
        • e-mail
        • телефон
    (Шаблон логина у тебя сейчас использует {{ form.username }} и {{ form.password }},
    так что эту форму подключай только если обновишь шаблон под 'identifier'.)
    """
    identifier = forms.CharField(label="E-mail / телефон / логин")

    def clean(self):
        identifier = self.cleaned_data.get("identifier")
        password = self.cleaned_data.get("password")
        self.user_cache = authenticate(self.request, username=identifier, password=password)
        if self.user_cache is None:
            raise forms.ValidationError("Неверные учётные данные.")
        self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class AccountPasswordResetForm(PasswordResetForm):
    """
    Customizes the password reset form widgets for branding and accessibility.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {
                "class": "auth-input",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )


class AccountSetPasswordForm(SetPasswordForm):
    """
    Provides consistent styling for the password reset confirm step.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ("new_password1", "new_password2"):
            if field in self.fields:
                self.fields[field].widget.attrs.update(
                    {
                        "class": "auth-input",
                        "autocomplete": "new-password",
                    }
                )


# ---------- Profile edit ----------
class ClientProfileForm(forms.Form):
    first_name = forms.CharField(required=False, max_length=150, label="Имя")
    last_name  = forms.CharField(required=False, max_length=150, label="Фамилия")
    email      = forms.EmailField(required=True, label="E-mail")
    phone      = forms.CharField(required=True, max_length=20, label="Телефон")
    birth_date = forms.DateField(required=False, input_formats=["%Y-%m-%d"], label="Дата рождения")

    # --- NEW: редактирование доп. полей профиля ---
    address = forms.CharField(
        required=False, label="Адрес",
        widget=forms.Textarea(attrs={"rows": 2})
    )
    postal_code = forms.CharField(
        required=False,
        max_length=6,
        label="Postal code",
    )
    how_heard = forms.ChoiceField(
        required=False, label="How did you hear about us?",
        choices=[("", "— Select —")] + list(HowHeard.choices)
    )
    email_marketing_consent = forms.BooleanField(
        required=False, label="Согласен получать новости и предложения на e-mail"
    )

    def __init__(self, *args, **kwargs):
        self.user: CustomUserDisplay = kwargs.pop("user")
        super().__init__(*args, **kwargs)

        # Префиллим текущими значениями профиля (если форма открывается GET'ом)
        prof = getattr(self.user, "userprofile", None)
        if prof:
            self.fields["phone"].initial = prof.phone
            self.fields["birth_date"].initial = prof.birth_date
            self.fields["address"].initial = prof.address
            self.fields["postal_code"].initial = prof.postal_code
            self.fields["how_heard"].initial = prof.how_heard
            self.fields["email_marketing_consent"].initial = prof.email_marketing_consent

        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["email"].initial = self.user.email

        autocomplete_map = {
            "first_name": "given-name",
            "last_name": "family-name",
            "email": "email",
            "phone": "tel",
            "birth_date": "bday",
            "address": "street-address",
            "postal_code": "postal-code",
        }
        placeholders = {
            "first_name": "Jane",
            "last_name": "Doe",
            "postal_code": "T2X1A1",
        }
        for field_name, field in self.fields.items():
            widget = field.widget
            if field_name in autocomplete_map:
                widget.attrs["autocomplete"] = autocomplete_map[field_name]
            if field_name in placeholders:
                widget.attrs.setdefault("placeholder", placeholders[field_name])
            widget.attrs.setdefault("data-autofill-key", field_name)
        if "email_marketing_consent" in self.fields:
            self.fields["email_marketing_consent"].widget.attrs.setdefault("data-track", "marketing-consent")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").lower().strip()
        if CustomUserDisplay.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise ValidationError("Этот e-mail уже используется.")
        return email

    def clean_phone(self):
        raw = (self.cleaned_data.get("phone") or "").strip()
        # нормализация под E.164 с принудительным +1
        raw = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
        if raw and not raw.startswith("+"):
            raw = "+1" + raw
        try:
            parsed = phonenumbers.parse(raw, None)
            phone_e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise ValidationError("Неверный формат телефона.")
        # уникальность среди профилей, исключая текущего пользователя
        qs = UserProfile.objects.filter(phone=phone_e164)
        qs = qs.exclude(user=self.user)
        if qs.exists():
            raise ValidationError("Этот телефон уже используется.")
        return phone_e164

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get("birth_date")
        if not birth_date:
            return birth_date

        today = timezone.now().date()
        if birth_date > today:
            raise ValidationError("Can not be born in the future")

        # минимальный возраст — 18 лет
        age = today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )
        if age < 18:
            raise ValidationError("Can not be below 18 yo")

        return birth_date

    def clean_postal_code(self):
        postal_code = (self.cleaned_data.get("postal_code") or "").strip()
        if not postal_code:
            return ""
        try:
            return clean_ab_postal_code(postal_code)
        except ValidationError as exc:
            # clean_ab_postal_code уже возвращает ValidationError с корректным сообщением
            raise ValidationError(exc.message if hasattr(exc, "message") else exc.messages[0])

    def save(self):
        self.user.first_name = self.cleaned_data.get("first_name", "") or ""
        self.user.last_name  = self.cleaned_data.get("last_name", "") or ""
        self.user.email      = self.cleaned_data["email"]
        self.user.save(update_fields=["first_name", "last_name", "email"])

        # Обновляем/создаём UserProfile
        prof, _ = UserProfile.objects.get_or_create(user=self.user)
        prof.phone      = self.cleaned_data["phone"]              # уже E.164
        prof.birth_date = self.cleaned_data.get("birth_date") or None
        prof.address    = self.cleaned_data.get("address", "") or ""
        prof.postal_code = self.cleaned_data.get("postal_code", "") or ""
        prof.how_heard  = self.cleaned_data.get("how_heard", "") or ""

        # согласие + timestamp через метод модели
        consent = bool(self.cleaned_data.get("email_marketing_consent"))
        prof.set_marketing_consent(consent)

        billing_contact = dict(getattr(prof, "billing_contact", {}) or {})
        updated_billing = False

        def _set_contact(key: str, value: str, *, force: bool = False) -> None:
            nonlocal updated_billing
            if value in (None, ""):
                if force and billing_contact.get(key):
                    billing_contact.pop(key, None)
                    updated_billing = True
                return
            if force or billing_contact.get(key) != value:
                billing_contact[key] = value
                updated_billing = True

        full_name = f"{self.user.first_name} {self.user.last_name}".strip()
        _set_contact("name", full_name, force=True)
        _set_contact("email", self.cleaned_data["email"], force=True)
        _set_contact("phone", prof.phone or "", force=True)
        _set_contact("postal_code", prof.postal_code or "", force=True)

        address_value = (self.cleaned_data.get("address", "") or "").strip()
        if address_value:
            lines = [line.strip() for line in address_value.split("\n") if line.strip()]
            if lines:
                _set_contact("address_line1", lines[0], force=True)
                if len(lines) > 1:
                    _set_contact("address_line2", " ".join(lines[1:]), force=True)
        else:
            _set_contact("address_line1", "", force=True)
            _set_contact("address_line2", "", force=True)

        if updated_billing:
            prof.billing_contact = {k: v for k, v in billing_contact.items() if v not in (None, "")}
            prof.billing_contact_updated_at = timezone.now()

        prof.save(update_fields=[
            "phone", "birth_date", "address", "postal_code", "how_heard",
            "email_marketing_consent", "email_marketing_consented_at",
            "billing_contact", "billing_contact_updated_at",
        ])
        return self.user

class HealthConditionsForm(forms.Form):
    allergies = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Comma-separated: e.g. Lidocaine, Pollen"})
    )
    medications = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    contraindications = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    chronic = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    surgeries = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        autofill_fields = ("allergies", "medications", "contraindications", "chronic", "surgeries", "notes")
        for name in autofill_fields:
            field = self.fields.get(name)
            if not field:
                continue
            field.widget.attrs.setdefault("data-autofill-key", name)
            field.widget.attrs.setdefault("autocomplete", "off")

    def _split_csv(self, s: str):
        return [x.strip() for x in s.split(",") if x.strip()] if s else []

    def to_json(self):
        cd = self.cleaned_data
        return {
            "allergies": self._split_csv(cd.get("allergies")),
            "medications": self._split_csv(cd.get("medications")),
            "contraindications": self._split_csv(cd.get("contraindications")),
            "chronic": self._split_csv(cd.get("chronic")),
            "surgeries": self._split_csv(cd.get("surgeries")),
            "notes": cd.get("notes") or "",
        }

    def load_initial_from_json(self, data: dict):
        def join_csv(v): return ", ".join(v) if isinstance(v, (list, tuple)) else (v or "")
        self.initial.update({
            "allergies": join_csv(data.get("allergies")),
            "medications": join_csv(data.get("medications")),
            "contraindications": join_csv(data.get("contraindications")),
            "chronic": join_csv(data.get("chronic")),
            "surgeries": join_csv(data.get("surgeries")),
            "notes": data.get("notes", ""),
        })
# -----------------------------
# Retail sales
# -----------------------------

class ProductSaleForm(forms.Form):
    product = forms.ModelChoiceField(
        label="Product",
        queryset=Product.objects.none(),
    )
    client = forms.ModelChoiceField(
        label="Client",
        required=False,
        queryset=UserProfile.objects.none(),
        help_text="Optional: link sale to an existing client.",
    )
    quantity = forms.IntegerField(
        label="Quantity",
        min_value=1,
        initial=1,
    )
    unit_price = forms.DecimalField(
        label="Unit price (CAD)",
        required=False,
        min_value=Decimal("0.00"),
        decimal_places=2,
        max_digits=10,
        help_text="Leave blank to use the product's default price.",
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    sold_at = forms.DateTimeField(
        label="Sale date & time",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, employee_profile: UserProfile | None = None, **kwargs):
        self.employee_profile = employee_profile
        super().__init__(*args, **kwargs)

        self.fields["product"].queryset = Product.objects.filter(is_active=True).order_by("name")

        client_qs = (
            UserProfile.objects.filter(userrole__role__name="Client")
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
            .distinct()
        )
        self.fields["client"].queryset = client_qs

        if not self.is_bound:
            local_now = timezone.localtime(timezone.now())
            self.fields["sold_at"].initial = local_now.strftime("%Y-%m-%dT%H:%M")

    def clean_unit_price(self):
        price = self.cleaned_data.get("unit_price")
        product = self.cleaned_data.get("product")
        if price is None:
            if product is None:
                return price
            return product.price
        return price

    def clean_sold_at(self):
        value = self.cleaned_data.get("sold_at")
        if not value:
            return timezone.now()
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean(self):
        cleaned = super().clean()
        product: Product | None = cleaned.get("product")
        quantity = cleaned.get("quantity") or 0
        if product and quantity and quantity > product.quantity_in_stock:
            self.add_error(
                "quantity",
                f"Only {product.quantity_in_stock} unit(s) of {product.name} remaining in stock.",
            )
        return cleaned

    def save(self, *, employee_profile: UserProfile | None = None) -> ProductSale:
        profile = employee_profile or self.employee_profile
        if profile is None:
            raise ValidationError("Employee profile is required to register a sale.")

        sale = ProductSale(
            product=self.cleaned_data["product"],
            sold_by=profile,
            client=self.cleaned_data.get("client"),
            quantity=self.cleaned_data["quantity"],
            unit_price=self.cleaned_data["unit_price"],
            sold_at=self.cleaned_data["sold_at"],
            notes=self.cleaned_data.get("notes", ""),
        )
        sale.full_clean()
        sale.save()
        return sale

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.utils.text import slugify

import phonenumbers

from core.models import (
    CustomUserDisplay,
    UserProfile,
    Role,
    HowHeard,  # TextChoices со значениями источников
)


# ---------- Registration ----------
class ClientRegistrationForm(UserCreationForm):
    """
    Регистрация клиента: e-mail, телефон, (необязательный) username + пароль.
    После save():
        • создаёт UserProfile (включая address / how_heard / email_marketing_consent),
        • назначает роль «Client».
    """

    email = forms.EmailField(required=True, label="E-mail")

    # Визуально предзаполняем +1 и показываем формат;
    # валидацию/нормализацию делаем в clean_phone()
    phone = forms.CharField(
        max_length=20,
        label="Телефон",
        initial="+1 ",
        widget=forms.TextInput(attrs={"placeholder": "(555) 123-4567"})
    )

    username = forms.CharField(required=False, label="Логин (можно оставить пустым)")

    # --- NEW: дополнительные поля регистрации ---
    address = forms.CharField(
        required=False, label="Адрес",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Street, Apt, City, ZIP"})
    )

    how_heard = forms.ChoiceField(
        required=False, label="How did you hear about us?",
        choices=[("", "— Select —")] + list(HowHeard.choices)
    )

    email_marketing_consent = forms.BooleanField(
        required=False, label="I agree to receive e-mail updates and offers"
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUserDisplay
        fields = (
            "username", "email", "phone",
            "address", "how_heard", "email_marketing_consent",
            "password1", "password2"
        )

    # --- Validation helpers ---

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").lower().strip()
        if CustomUserDisplay.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот e-mail уже используется.")
        return email

    def clean_phone(self):
        raw = (self.cleaned_data.get("phone") or "").strip()
        # Оставляем только цифры и '+'
        raw = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
        # Если код страны не указан — подставим +1
        if raw and not raw.startswith("+"):
            raw = "+1" + raw
        # Парсим и приводим к E.164
        try:
            parsed = phonenumbers.parse(raw, None)
        except phonenumbers.NumberParseException:
            raise forms.ValidationError("Неверный формат телефона.")
        phone_e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        # Проверка уникальности среди профилей
        if UserProfile.objects.filter(phone=phone_e164).exists():
            raise forms.ValidationError("Этот телефон уже используется.")
        return phone_e164

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if username:
            qs = CustomUserDisplay.objects.filter(username=username)
            instance_pk = getattr(self.instance, "pk", None)
            if instance_pk:
                qs = qs.exclude(pk=instance_pk)
            if qs.exists():
                raise forms.ValidationError("Такой логин уже занят.")
        return username or None

    # --- Save ---

    def save(self, commit=True):
        user = super().save(commit=False)

        # email / username
        user.email = self.cleaned_data["email"]
        provided_username = self.cleaned_data.get("username")
        if provided_username:
            user.username = provided_username
        else:
            base = slugify(user.email.split("@")[0]) or "user"
            candidate = base
            suffix = 1
            while CustomUserDisplay.objects.filter(username=candidate).exclude(pk=user.pk).exists():
                candidate = f"{base}{suffix}"
                suffix += 1
            user.username = candidate

        if commit:
            user.save()

            phone = self.cleaned_data["phone"]  # уже в E.164
            address = self.cleaned_data.get("address") or ""
            how_heard = self.cleaned_data.get("how_heard") or ""

            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "phone": phone,
                    "address": address,
                    "how_heard": how_heard,
                },
            )
            if not created:
                profile.phone = phone
                profile.address = address
                profile.how_heard = how_heard

            consent = bool(self.cleaned_data.get("email_marketing_consent"))
            profile.set_marketing_consent(consent)
            profile.save(update_fields=[
                "phone", "address", "how_heard",
                "email_marketing_consent", "email_marketing_consented_at",
            ])

            client_role, _ = Role.objects.get_or_create(name="Client")
            profile.userrole_set.get_or_create(role=client_role)

        return user


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
            self.fields["how_heard"].initial = prof.how_heard
            self.fields["email_marketing_consent"].initial = prof.email_marketing_consent

        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["email"].initial = self.user.email

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
        prof.how_heard  = self.cleaned_data.get("how_heard", "") or ""

        # согласие + timestamp через метод модели
        consent = bool(self.cleaned_data.get("email_marketing_consent"))
        prof.set_marketing_consent(consent)

        prof.save(update_fields=[
            "phone", "birth_date", "address", "how_heard",
            "email_marketing_consent", "email_marketing_consented_at",
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

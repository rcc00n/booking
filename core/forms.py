import json
import re
from pathlib import Path

from dal import autocomplete
from django import forms
from django.contrib.admin import TabularInline
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    UserCreationForm,
    UserChangeForm,
    AdminUserCreationForm,
)
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.template import TemplateDoesNotExist, engines
from django.utils.safestring import mark_safe

import phonenumbers

from .models import *
from .validators import *


def _services_for_selection(include_ids=None, *, include_inactive_ids=False):
    """
    Build queryset of services filtered to active ones, optionally including specific ids even if inactive.
    """
    base = Service.objects.filter(is_active=True)
    if include_inactive_ids and include_ids:
        extra_ids = set(include_ids)
        base = Service.objects.filter(Q(pk__in=extra_ids) | Q(is_active=True))
    return base.select_related("category").order_by("category__name", "name")


HEALTH_CHRONIC_CHOICES = [
    ("asthma", "Asthma"),
    ("diabetes", "Diabetes"),
    ("hypertension", "Hypertension"),
    ("thyroid", "Thyroid disorder"),
]

HEALTH_CONTRA_CHOICES = [
    ("fever", "Fever / Infection"),
    ("wounds", "Open wounds / Cuts"),
    ("pregnancy", "Pregnancy"),
    ("allergy_unknown", "Allergy to unknown agents"),
]

EDITABLE_FIELDS_FOR_MASTER = (
    "service", "start_time", "end_time", "unit_price", "promocode",
)


class ProductSaleAdminForm(forms.ModelForm):
    """
    Shared base form for product sale editing in admin UIs.
    Supports enhanced widgets via data attributes consumed by custom JS.
    """
    class Meta:
        model = ProductSale
        fields = "__all__"

    class Media:
        js = ("core/js/product_sale_admin.js",)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.appointment = kwargs.pop("appointment", None)
        super().__init__(*args, **kwargs)

        sold_by = self.fields.get("sold_by")
        if sold_by:
            sold_by.widget.attrs.setdefault(
                "data-placeholder", "Start typing to choose an employee"
            )

        client = self.fields.get("client")
        if client:
            client.widget.attrs.setdefault(
                "data-placeholder", "Start typing to search clients"
            )

        appointment = self.fields.get("appointment")
        if appointment:
            appointment.widget.attrs.setdefault(
                "data-placeholder", "Link to an appointment (optional)"
            )

        product = self.fields.get("product")
        if product:
            product.widget.attrs.setdefault("data-price-endpoint", "")
            product.widget.attrs.setdefault("data-product-sale-role", "product")

        unit_price = self.fields.get("unit_price")
        if unit_price:
            unit_price.widget.attrs.update(
                {
                    "data-unit-price-input": "1",
                    "autocomplete": "off",
                    "data-product-sale-role": "unit-price",
                }
            )

        quantity = self.fields.get("quantity")
        if quantity:
            quantity.widget.attrs.update(
                {
                    "data-quantity-input": "1",
                    "data-product-sale-role": "quantity",
                }
            )


class AppointmentProductSaleForm(ProductSaleAdminForm):
    """
    Specialized form for embedding product sales into the appointment change form.
    Hides fields that should not be edited in that context and applies sensible defaults.
    """

    def __init__(self, *args, **kwargs):
        request = kwargs.get("request")
        appointment = kwargs.get("appointment")
        super().__init__(*args, **kwargs)

        if "sold_at" in self.fields:
            self.fields.pop("sold_at")

        client_field = self.fields.get("client")
        if client_field:
            qs = UserProfile.objects.select_related("user").all()
            client_field.queryset = qs.order_by(
                "user__first_name",
                "user__last_name",
                "user__username",
            )

        sold_by_field = self.fields.get("sold_by")
        if sold_by_field:
            filters = Q(user__is_superuser=True) | Q(user__is_staff=True)
            profile = getattr(request.user, "userprofile", None) if request else None
            if profile:
                filters |= Q(pk=profile.pk)
            if self.instance and getattr(self.instance, "sold_by_id", None):
                filters |= Q(pk=self.instance.sold_by_id)
            sold_by_field.queryset = (
                UserProfile.objects.select_related("user")
                .filter(filters)
                .order_by(
                    "user__first_name",
                    "user__last_name",
                    "user__username",
                )
            )

        defaults = {}
        if appointment and appointment.client_id and "client" in self.fields:
            defaults["client"] = appointment.client_id
        profile = getattr(request.user, "userprofile", None) if request else None
        if profile and "sold_by" in self.fields:
            defaults["sold_by"] = profile.pk
        if "quantity" in self.fields:
            defaults.setdefault("quantity", 1)

        for key, value in defaults.items():
            if key in self.fields and key not in self.initial:
                self.initial[key] = value
            field = self.fields.get(key)
            if field and not field.initial:
                field.initial = value

        # Keep notes compact in inline UI.
        notes = self.fields.get("notes")
        if notes:
            notes.widget.attrs.setdefault("rows", 2)


def _normalize_phone(value: str) -> str:
    """Bring phone number to E.164, default country +1."""
    raw = (value or "").strip()
    if not raw:
        raise ValidationError("Phone number is required.")

    filtered = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    if filtered and not filtered.startswith("+"):
        filtered = "+1" + filtered

    try:
        parsed = phonenumbers.parse(filtered, None)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError("Invalid phone number format.") from exc

    if not phonenumbers.is_possible_number(parsed):
        raise ValidationError("Invalid phone number format.")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

# -----------------------------
# Appointment Form
# -----------------------------

class AppointmentItemAdminForm(forms.ModelForm):
    class Meta:
        model = AppointmentItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self._current_master = None
        if self.user:
            self._current_master = MasterProfile.objects.filter(user=self.user).first()

        # 1) Ограничим выбор мастера ТОЛЬКО текущим мастером
        if "master" in self.fields and self._current_master:
            self.fields["master"].queryset = MasterProfile.objects.filter(pk=self._current_master.pk)

        # 2) Если это существующая позиция и её master != текущий мастер — делаем её read-only
        readonly = False
        if self.instance and self.instance.pk and self._current_master:
            if getattr(self.instance, "master_id", None) != self._current_master.id:
                readonly = True

        if readonly:
            for name, field in self.fields.items():
                # Поле master и остальные — в readonly (disabled)
                field.disabled = True
                # помогаем фронту понять, что надо подложить hidden-клон
                field.widget.attrs["data-ro"] = "1"
        else:
            # даже если позиция «моя», менять поле master нельзя
            if "master" in self.fields:
                self.fields["master"].disabled = True
                self.fields["master"].widget.attrs["data-ro"] = "1"

    def clean_master(self):
        # Защитимся от подмены master через POST
        if self._current_master:
            return self._current_master
        return self.cleaned_data.get("master")

    def clean(self):
        cleaned = super().clean()
        if not self._current_master:
            # не мастер — пусть решает общий админ, здесь ничего не ограничиваем
            return cleaned

        # Нельзя редактировать чужие позиции
        if self.instance and self.instance.pk:
            if getattr(self.instance, "master_id", None) != self._current_master.id:
                # если пришли изменения каких-либо editable полей — стоп
                for f in EDITABLE_FIELDS_FOR_MASTER:
                    if f in self.changed_data:
                        raise ValidationError("Вы не можете редактировать позиции другого мастера.")
        return cleaned

class AppointmentAdminForm(forms.ModelForm):
    current_status = forms.ModelChoiceField(
        queryset=AppointmentStatus.objects.all(),
        required=False,
        label="Status"
    )

    class Meta:
        model = Appointment
        fields = (
            "client",
            "start_time",
            "payment_status",    # NOTE: если есть
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_ids = []
        if self.instance.pk:
            last = (AppointmentStatusHistory.objects
                    .filter(appointment=self.instance)
                    .select_related("status")
                    .order_by("-set_at")
                    .first())
            if last:
                self.fields["current_status"].initial = last.status_id
            else:
                # fallback: если хочешь значение по умолчанию
                first_status = AppointmentStatus.objects.order_by("id").first()
                if first_status:
                    self.fields["current_status"].initial = first_status.pk

        # Нормальный класс под твои стили
        self.fields["current_status"].widget.attrs.update({"class": "ab-select"})
        now = timezone.now()
        qs = PromoCode.objects.all()

        # Если у вас в PromoCode есть поля "active/starts_at/ends_at", отфильтруем валидные коды:
        if hasattr(PromoCode, "active"):
            qs = qs.filter(active=True)
        if hasattr(PromoCode, "starts_at"):
            qs = qs.filter(starts_at__lte=now)
        if hasattr(PromoCode, "ends_at"):
            qs = qs.filter(ends_at__gte=now)
        if "promocode" in self.fields:
            self.fields["promocode"].queryset = qs
            self.fields["promocode"].required = False
            self.fields["promocode"].help_text = "Выберите действующий промокод (опционально)."


# ──────────────────────────────────────────────────────────────────────────────
# Позиции AppointmentItem
# ──────────────────────────────────────────────────────────────────────────────

class AppointmentAddForm(forms.ModelForm):
    """Форма 'создать визит': показываем только клиента."""
    class Meta:
        model = Appointment
        fields = ("client",)

class AppointmentItemInlineForm(forms.ModelForm):
    promocode = forms.ModelChoiceField(
        label="Promocode",
        required=False,
        queryset=PromoCode.objects.all(),  # или фильтрация по активным/дате, если надо
        help_text="Опционально: промокод для данной позиции",
    )
    class Meta:
        model = AppointmentItem
        fields = "__all__"

    def __init__(self, *args, parent_obj=None, **kwargs):
        super().__init__(*args, **kwargs)

        # 1) Инициализация от родителя: только для НОВОЙ строки (у которой нет PK)
        if not self.instance.pk and parent_obj:
            if "master" in self.fields and getattr(parent_obj, "master_id", None):
                self.fields["master"].initial = parent_obj.master
            if "start_time" in self.fields and getattr(parent_obj, "start_time", None):
                self.fields["start_time"].initial = parent_obj.start_time

        # 2) Инициализация unit_price от услуги (если ещё не задан)
        service = self.initial.get("service") or getattr(self.instance, "service", None)
        if service and not hasattr(service, 'duration_min'):
            service = Service.objects.filter(pk=service).first()
        service_field = self.fields.get("service")
        if service_field:
            current_service_id = None
            if getattr(self.instance, "service_id", None):
                current_service_id = self.instance.service_id
            elif "service" in self.initial:
                current_service_id = self.initial["service"]
            if isinstance(current_service_id, Service):
                current_service_id = current_service_id.pk
            elif hasattr(current_service_id, "pk"):
                current_service_id = current_service_id.pk
            include_ids = [current_service_id] if current_service_id else None
            service_field.queryset = _services_for_selection(
                include_ids=include_ids,
                include_inactive_ids=True,
            )
        if "unit_price" in self.fields:
            has_price_initial = self.initial.get("unit_price") or getattr(self.instance, "unit_price", None)
            if not has_price_initial and service and getattr(service, "base_price", None) is not None:
                self.fields["unit_price"].initial = service.base_price
        if not self.is_bound and "duration_override_min" in self.fields:
            override = getattr(self.instance, "duration_override_min", None)
            if override:
                self.fields["duration_override_min"].initial = override
            elif service:
                total_duration = (service.duration_min or 0) + (getattr(service, "extra_time_min", 0) or 0)
                if total_duration:
                    self.fields["duration_override_min"].initial = total_duration

        # 3) Сохраняем ссылку на родителя для метода ниже (не обязательно, но удобно)
        self._parent_obj = parent_obj

        if self.instance and self.instance.pk:
            link = AppointmentItemPromoCode.objects.filter(item=self.instance).select_related("promocode").first()
            if link:
                self.fields["promocode"].initial = link.promocode_id

    def fix_promocode_queryset(self):
        """
        Если вы фильтруете промокоды (active/дата и т.п.),
        добавьте сюда текущий выбранный, чтобы он был виден при редактировании.
        """
        if "promocode" not in self.fields:
            return
        qs = self.fields["promocode"].queryset
        current_id = getattr(self.instance, "promocode_id", None)
        if current_id:
            self.fields["promocode"].queryset = qs.model.objects.filter(Q(pk=current_id) | Q(pk__in=qs.values("pk")))


    def save(self, commit=True):
        # сохраняем сам Item

        item = super().save(commit)
        promo = self.cleaned_data.get("promocode")
        # синхронизируем through-модель
        if item.pk:
            if promo:
                AppointmentItemPromoCode.objects.update_or_create(
                    item=item,
                    defaults={"promocode": promo}
                )
            else:
                # если поле очищено — удаляем связь
                AppointmentItemPromoCode.objects.filter(item=item).delete()

            # пересчёт цен/скидок для Item (и/или Апойнтмента)
            # сделайте один из вариантов, который у вас реально есть:
            if hasattr(item, "recompute_pricing"):
                item.recompute_pricing()
            else:
                # fallback: триггерим save() или вызовите ваш сервис пересчёта
                item.save()

        return item


class ServiceDiscountAdminForm(forms.ModelForm):
    class Meta:
        model = ServiceDiscount
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("service")
        if field:
            current_id = getattr(self.instance, "service_id", None)
            include_ids = [current_id] if current_id else None
            field.queryset = _services_for_selection(include_ids, include_inactive_ids=True)


class PromoCodeAdminForm(forms.ModelForm):
    class Meta:
        model = PromoCode
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("applicable_services")
        if field:
            current_ids = []
            if self.instance and self.instance.pk:
                current_ids = list(
                    self.instance.applicable_services.values_list("pk", flat=True)
                )
            field.queryset = _services_for_selection(current_ids, include_inactive_ids=True)


class ServiceMasterAdminForm(forms.ModelForm):
    class Meta:
        model = ServiceMaster
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("service")
        if field:
            current_id = getattr(self.instance, "service_id", None)
            include_ids = [current_id] if current_id else None
            field.queryset = _services_for_selection(include_ids)
# -----------------------------
# Custom User Creation Form
# -----------------------------

class HealthFieldsMixin(forms.Form):
    """
    Миксин превращает JSON из UserProfile.health в набор отдельных полей формы
    и обратно, чтобы админке/формам было удобно.
    """
    has_allergies = forms.BooleanField(required=False, label="Allergies")
    allergies_text = forms.CharField(required=False, label="Allergy details", widget=forms.Textarea(attrs={"rows": 2}))
    gender = forms.ChoiceField(
        required=False,
        label="Gender",
        choices=[("", "—"), ("male", "Male"), ("female", "Female"), ("other", "Other")]
    )
    chronic_conditions = forms.MultipleChoiceField(
        required=False, choices=HEALTH_CHRONIC_CHOICES,
        label="Chronic conditions",
        widget=forms.CheckboxSelectMultiple
    )

    medications = forms.CharField(required=False, label="Current medications", widget=forms.Textarea(attrs={"rows": 2}))
    pregnant = forms.BooleanField(required=False, label="Pregnancy")
    skin_sensitivity = forms.ChoiceField(
        required=False, label="Skin sensitivity",
        choices=[("", "—"), ("low", "Low"), ("normal", "Normal"), ("high", "High")]
    )
    recent_procedures = forms.CharField(required=False, label="Recent procedures", widget=forms.Textarea(attrs={"rows": 2}))
    contraindications = forms.MultipleChoiceField(
        required=False, choices=HEALTH_CONTRA_CHOICES,
        label="Contraindications",
        widget=forms.CheckboxSelectMultiple
    )
    health_notes = forms.CharField(required=False, label="Health notes", widget=forms.Textarea(attrs={"rows": 2}))

    # --- helpers ---
    def _health_from_initial(self, user_instance):
        prof = getattr(user_instance, "userprofile", None)
        return (getattr(prof, "health_conditions", None) or {}) if prof else {}

    def _set_health_initials(self, user_instance):
        data = self._health_from_initial(user_instance)
        self.fields["gender"].initial = data.get("gender", "")
        self.fields["has_allergies"].initial = bool(data.get("has_allergies"))
        self.fields["allergies_text"].initial = data.get("allergies_text", "")
        self.fields["chronic_conditions"].initial = data.get("chronic_conditions", [])
        self.fields["medications"].initial = data.get("medications", "")
        self.fields["pregnant"].initial = bool(data.get("pregnant"))
        self.fields["skin_sensitivity"].initial = data.get("skin_sensitivity", "")
        self.fields["recent_procedures"].initial = data.get("recent_procedures", "")
        self.fields["contraindications"].initial = data.get("contraindications", [])
        self.fields["health_notes"].initial = data.get("health_notes", "")

    def _collect_health_payload(self):
        # Нормализуем в «плоский» JSON (только нужные ключи)
        cd = self.cleaned_data
        return {
            "has_allergies": bool(cd.get("has_allergies")),
            "allergies_text": cd.get("allergies_text", "").strip(),
            "gender": cd.get("gender") or "",
            "chronic_conditions": cd.get("chronic_conditions") or [],
            "medications": cd.get("medications", "").strip(),
            "pregnant": bool(cd.get("pregnant")),
            "skin_sensitivity": cd.get("skin_sensitivity") or "",
            "recent_procedures": cd.get("recent_procedures", "").strip(),
            "contraindications": cd.get("contraindications") or [],
            "health_notes": cd.get("health_notes", "").strip(),
        }

class CustomUserCreationForm(HealthFieldsMixin, AdminUserCreationForm):
    """
    Custom user creation form with additional fields:
    - Email, phone, birth date, and roles
    - Automatically creates and links a UserProfile
    - Assigns roles after saving the user
    """
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    phone = forms.CharField(required=True)
    birth_date = forms.DateField(required=False, widget=forms.SelectDateWidget(years=range(1950, 2030)))
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Street, Apt, City, ZIP"}),
        label="Address",
    )
    personal_discount_percent = forms.IntegerField(
        required=False, min_value=0, max_value=100, initial=0, label="Personal discount, %"
    )
    # новые поля
    postal_code = forms.CharField(
        required=False,
        label="Postal code (AB)",
        max_length=6,
        widget=forms.TextInput(attrs={"placeholder": "T2X1A1"})
    )

    email_marketing_consent = forms.BooleanField(
        required=False,
        label="Agreed for marketing emails"
    )
    how_heard = forms.ChoiceField(
        required=False,
        label="How did you hear about us?",
        choices=[("", "—")] + list(HowHeard.choices)
    )
    notes = forms.CharField(required=False, widget=forms.Textarea)


    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name',
            'phone', 'birth_date',
            'address',
            'usable_password', 'password1', 'password2',
            'is_staff', 'is_active', 'is_superuser',
            'groups', "postal_code", "email_marketing_consent",
            "notes", 'personal_discount_percent'
        ]
    def clean_postal_code(self):
        val = self.cleaned_data.get("postal_code", "").strip()
        return clean_ab_postal_code(val) if val else ""
    def save(self, commit=True):
        """
        Overridden save method to:
        - Set password
        - Create and populate UserProfile
        - Assign roles to the new user
        """
        user = super().save(commit=False)

        # Ensure identity fields are in sync (ModelForm should handle, keep explicit for clarity)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']

        phone = self.cleaned_data.get('phone')
        user.username = phone

        try:
            user = self.set_password_and_save(user, commit=commit)
        except IntegrityError as exc:
            self.add_error('phone', "User with such phone already exists.")
            raise forms.ValidationError("User with such phone already exists.") from exc

        if commit and hasattr(self, 'save_m2m'):
            self.save_m2m()

        if commit:
            birth_date = self.cleaned_data.get('birth_date')
            how_heard = self.cleaned_data.get('how_heard')
            email_marketing_consent = self.cleaned_data.get('email_marketing_consent')
            notes = self.cleaned_data.get('notes')
            address = (self.cleaned_data.get('address') or "").strip()

            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.phone = phone
            profile.birth_date = birth_date
            profile.how_heard = how_heard
            profile.personal_discount_percent = self.cleaned_data.get('personal_discount_percent') or 0
            profile.set_marketing_consent(email_marketing_consent)
            profile.notes = notes
            profile.health_conditions = self._collect_health_payload()
            profile.postal_code = self.cleaned_data.get('postal_code', "")
            profile.address = address

            if not hasattr(self, "is_client_register"):
                profile.source = "offline"
            profile.save()

            client_role, _ = Role.objects.get_or_create(name="Client")
            UserRole.objects.get_or_create(user=profile, role=client_role)

        return user


    def clean_phone(self):
        raw_phone = self.cleaned_data.get('phone', "")
        try:
            phone = _normalize_phone(raw_phone)
        except ValidationError as exc:
            raise forms.ValidationError(exc.message)

        User = get_user_model()
        if User.objects.filter(username=phone).exists():
            raise forms.ValidationError("User with such phone number already exists.")

        if UserProfile.objects.filter(phone=phone).exists():
            raise forms.ValidationError("User with such phone number already exists.")
        return phone


class UserImportUploadForm(forms.Form):
    import_file = forms.FileField(label="Upload file")

    SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xlsm")

    def clean_import_file(self):
        uploaded = self.cleaned_data["import_file"]
        filename = uploaded.name.lower()
        if not any(filename.endswith(ext) for ext in self.SUPPORTED_EXTENSIONS):
            raise forms.ValidationError("Unsupported file type. Please upload CSV or XLSX.")
        uploaded.seek(0)
        return uploaded


class UserImportRowForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    phone = forms.CharField(max_length=32)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not username:
            raise forms.ValidationError("Username is required.")
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean_phone(self):
        raw_phone = self.cleaned_data.get("phone", "")
        try:
            phone = _normalize_phone(raw_phone)
        except ValidationError as exc:
            raise forms.ValidationError(exc.message)

        if UserProfile.objects.filter(phone=phone).exists():
            raise forms.ValidationError("Phone already exists.")
        return phone
# -----------------------------
# Custom User Change Form
# -----------------------------

class UserProfileChangeForm(forms.ModelForm):
    # «виртуальные» поля из связанного User
    has_allergies = forms.BooleanField(required=False)
    allergies_text = forms.CharField(required=False, widget=forms.Textarea)
    gender = forms.CharField(required=False)
    chronic_conditions = forms.CharField(required=False, widget=forms.Textarea)
    medications = forms.CharField(required=False, widget=forms.Textarea)
    pregnant = forms.BooleanField(required=False)
    skin_sensitivity = forms.BooleanField(required=False)
    recent_procedures = forms.CharField(required=False, widget=forms.Textarea)
    contraindications = forms.CharField(required=False, widget=forms.Textarea)
    health_notes = forms.CharField(required=False, widget=forms.Textarea)
    # если files — поле у User (ManyToMany/ForeignKey), можно отрендерить как обычное:
    # при M2M желательно widget=FilteredSelectMultiple, но можно начать с простого


    class Meta:
        model = UserProfile
        fields = (
            "user",
            "phone", "birth_date", "address", "postal_code",
            "how_heard",
            "notes",
            # ВАЖНО: тут только реальные поля UserProfile!
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        u = self.instance.user if getattr(self.instance, "user_id", None) else None

        # --- инициализация полей из User ---
        for name in (
                "has_allergies", "allergies_text", "gender", "chronic_conditions",
                "medications", "pregnant", "skin_sensitivity",
                "recent_procedures", "contraindications", "health_notes",
        ):
            if name in self.fields and u and hasattr(u, name):
                self.fields[name].initial = getattr(u, name)
        for name, field in self.fields.items():
            if name != "notes":
                field.disabled = True

        # --- files (ManyToMany у User) ---


    def save(self, commit=True):
        profile = super().save(commit=False)
        u = profile.user

        for name in (
                "has_allergies", "allergies_text", "gender", "chronic_conditions",
                "medications", "pregnant", "skin_sensitivity",
                "recent_procedures", "contraindications", "health_notes",
        ):
            if name in self.cleaned_data and hasattr(u, name):
                setattr(u, name, self.cleaned_data[name])

        if commit:
            u.save()
            profile.save()
        return profile

class CustomUserChangeForm(HealthFieldsMixin, UserChangeForm):
    """
    Custom form for editing existing users in the admin.
    - Pre-fills UserProfile fields (phone, birth_date)
    - Allows role selection and syncs them on save
    """
    password = ReadOnlyPasswordHashField(label="Password")
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    phone = forms.CharField(required=True)
    birth_date = forms.DateField(required=False, widget=forms.SelectDateWidget(years=range(1950, 2030)))
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Street, Apt, City, ZIP"}),
        label="Address",
    )
    personal_discount_percent = forms.IntegerField(
        required=False, min_value=0, max_value=100, label="Personal discount, %"
    )
    postal_code = forms.CharField(
        required=False,
        label="Postal code (AB)",
        max_length=6,
        widget=forms.TextInput(attrs={"placeholder": "T2X1A1"})
    )
    email_marketing_consent = forms.BooleanField(
        required=False,
        label="Agreed for marketing emails"
    )
    how_heard = forms.ChoiceField(
        required=False,
        label="How did you hear about us?",
        choices=[("", "—")] + list(HowHeard.choices)
    )
    notes = forms.CharField(required=False, widget=forms.Textarea)
    files = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={'multiple': False}),
        label="Upload files"
    )
    class Meta:
        model = User
        fields = [
            'email',
            'first_name',
            'last_name',
            'is_staff',
            'is_active',
            'is_superuser',
            'groups',
            'user_permissions',
            'password',
            'postal_code',
            'address',
            'how_heard',
            'email_marketing_consent',
            'notes',
            'files',
            'personal_discount_percent',


        ]

    def __init__(self, *args, **kwargs):
        """
        Populate form with data from related UserProfile and UserRole
        """
        super().__init__(*args, **kwargs)

        password_field = self.fields.get('password')
        if password_field:
            password_field.widget = forms.HiddenInput()
            password_field.required = False
            password_field.help_text = ""

        if self.instance and hasattr(self.instance, 'userprofile'):
            self._set_health_initials(self.instance)
            up = self.instance.userprofile
            self.fields['personal_discount_percent'].initial = (
                    self.instance.userprofile.personal_discount_percent or 0
            )
            self.fields['phone'].initial = self.instance.userprofile.phone
            self.fields['birth_date'].initial = self.instance.userprofile.birth_date
            self.fields['how_heard'].initial = self.instance.userprofile.how_heard
            self.fields['email_marketing_consent'].initial = self.instance.userprofile.email_marketing_consent
            self.fields['notes'].initial = self.instance.userprofile.notes
            self.fields['postal_code'].initial = getattr(up, 'postal_code', "")
            self.fields['address'].initial = getattr(up, 'address', "")

    def clean_postal_code(self):
        val = self.cleaned_data.get("postal_code", "").strip()
        return clean_ab_postal_code(val) if val else ""

    def save(self, commit=True):
        """
        Overridden save method to:
        - Save UserProfile data
        - Sync UserRole assignments
        """
        user = super().save(commit=False)
        phone_raw = self.cleaned_data.get('phone', "")
        try:
            phone = _normalize_phone(phone_raw)
        except ValidationError as exc:
            self.add_error('phone', exc.message)
            raise forms.ValidationError(exc.message) from exc
        user.username = phone
        try:
            user.save()
        except IntegrityError as exc:
            self.add_error('phone', "User with such phone number already exists.")
            raise forms.ValidationError("User with such phone number already exists.") from exc

        # Update profile
        birth_date = self.cleaned_data.get('birth_date', None)
        how_heard = self.cleaned_data.get('how_heard', None)
        notes = self.cleaned_data.get('notes', None)
        address = (self.cleaned_data.get('address') or "").strip()

        email_marketing_consent = self.cleaned_data.get('email_marketing_consent', False)
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.phone = phone
        profile.birth_date = birth_date
        profile.how_heard = how_heard
        profile.notes = notes
        profile.personal_discount_percent = self.cleaned_data.get('personal_discount_percent') or 0
        profile.set_marketing_consent(email_marketing_consent)
        profile.health_conditions = self._collect_health_payload()
        profile.postal_code = self.cleaned_data.get('postal_code', "")
        profile.address = address
        profile.save()


        uploaded_files = self.files.getlist('files')
        for f in uploaded_files:
            ClientFile.objects.create(
                user=user,
                file=f,
                file_type=""
            )
        return user


    def clean_phone(self):
        raw_phone = self.cleaned_data.get('phone', "")
        try:
            phone = _normalize_phone(raw_phone)
        except ValidationError as exc:
            raise forms.ValidationError(exc.message)

        qs = UserProfile.objects.filter(phone=phone)
        if self.instance.pk:
            qs = qs.exclude(user=self.instance)
        if qs.exists():
            raise forms.ValidationError("User with such phone number already exists.")

        User = get_user_model()
        user_qs = User.objects.filter(username=phone)
        if self.instance.pk:
            user_qs = user_qs.exclude(pk=self.instance.pk)
        if user_qs.exists():
            raise forms.ValidationError("User with such phone number already exists.")
        return phone

class ServicesDropdown(forms.CheckboxSelectMultiple):
    template_name = "widget/service_dropdown.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled_choices = set()


class MasterCreateFullForm(forms.ModelForm):
    # Общие поля
    email = forms.EmailField()
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    phone = forms.CharField(required=True)
    birth_date = forms.DateField(required=False, widget=forms.SelectDateWidget(years=range(1950, 2030)))

    services = forms.ModelMultipleChoiceField(
        label="Services",
        required=False,
        queryset=Service.objects.none(),
        widget=ServicesDropdown(attrs={
            "id": "id_services_dropdown",
            "placeholder": "Select services"
        }),
    )

    password1 = forms.CharField(widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(widget=forms.PasswordInput, required=False)
    postal_code = forms.CharField(
        required=False,
        label="Postal code",
        max_length=6,
        widget=forms.TextInput(attrs={"placeholder": "T2X1A1"})
    )
    class Meta:
        model = MasterProfile
        fields = ['profession', 'bio', 'services']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_phone_e164: str | None = None
        self._phone_changed: bool = True
        current_ids = []

        # Если редактируем — заменяем пароли на read-only поле
        if self.instance and self.instance.pk:

            current_ids = list(
                ServiceMaster.objects.filter(
                    master=self.instance
                ).values_list('service_id', flat=True)
            )
            user_profile = self.instance.user
            user = user_profile.user  # сам Django User
            self.fields['password'] = ReadOnlyPasswordHashField(label="Password")
            self.initial['password'] = user.password

            # Удаляем поля пароля
            self.fields.pop('password1')
            self.fields.pop('password2')

            # Заполняем initial для полей пользователя
            self.fields['email'].initial = user.email
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name

            self.fields['phone'].initial = user_profile.phone
            self.fields['postal_code'].initial = getattr(user_profile, 'postal_code', "")
            self.fields['birth_date'].initial = user_profile.birth_date

            current_phone = user_profile.phone
            if current_phone:
                try:
                    self._original_phone_e164 = _normalize_phone(current_phone)
                except ValidationError:
                    # Stored phone might already be normalized or slightly off. Keep raw fallback.
                    self._original_phone_e164 = current_phone.strip()
        services_qs = _services_for_selection()
        self.fields["services"].queryset = services_qs
        if current_ids:
            active_current = list(
                services_qs.filter(pk__in=current_ids).values_list("pk", flat=True)
            )
            self.initial["services"] = active_current

        cats = (
            ServiceCategory.objects.for_catalog()
            .filter(only_discounted_services=False)
            .prefetch_related(
                Prefetch(
                    "service_set",
                    queryset=_services_for_selection(),
                )
            )
        )
        choices = []
        for cat in cats:
            opts = [(str(s.pk), s.name) for s in cat.service_set.all()]
            if opts:
                choices.append((cat.name, opts))
        # Неотнесённые к категории — в конец
        uncategorized = services_qs.filter(category__isnull=True)
        if uncategorized.exists():
            choices.append(("Other", [(str(s.pk), s.name) for s in uncategorized]))

        self.fields["services"].choices = choices

    def clean_password2(self):
        # Только если создаём
        if self.instance and self.instance.pk:
            return None

        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match")

        validate_password(password2)
        return password2

    def clean_phone(self):
        raw_phone = self.cleaned_data.get('phone', "")
        try:
            phone = _normalize_phone(raw_phone)
        except ValidationError as exc:
            raise forms.ValidationError(exc.message)

        self._phone_changed = True
        if self._original_phone_e164 and phone == self._original_phone_e164:
            self._phone_changed = False
            return phone

        qs = UserProfile.objects.filter(phone=phone)

        if self.instance.pk and hasattr(self.instance, 'user'):
            # If editing, exclude the current user
            qs = qs.exclude(user=self.instance.user.user)

        if qs.exists():
            raise forms.ValidationError('This phone number is already registered!')

        User = get_user_model()
        user_qs = User.objects.filter(username=phone)
        if self.instance.pk and hasattr(self.instance, 'user'):
            user_qs = user_qs.exclude(pk=self.instance.user.user_id)
        if user_qs.exists():
            raise forms.ValidationError('This phone number is already registered!')

        return phone

    def save(self, commit=True):
        """
       На создании:
         - создаём User, UserProfile, MasterProfile (как и раньше)
         - создаём связи ServiceMaster по отмеченным услугам

       На редактировании:
         - обновляем User / UserProfile (как и раньше)
         - синхронизируем ServiceMaster: добавляем новые, удаляем снятые
       """
        selected_services = list(self.cleaned_data.get('services') or [])
        phone = self.cleaned_data.get('phone')
        if not phone:
            raise forms.ValidationError('Phone number is required.')
        phone_changed = getattr(self, "_phone_changed", True)

        if not self.instance.pk:
            # Создание нового пользователя
            User = get_user_model()
            try:
                user = User.objects.create_user(
                    username=phone,
                    email=self.cleaned_data['email'],
                    password=self.cleaned_data['password1'],
                    first_name=self.cleaned_data['first_name'],
                    last_name=self.cleaned_data['last_name'],
                )
            except IntegrityError as exc:
                self.add_error('phone', 'User with such phone already exists.')
                raise forms.ValidationError('User with such phone already exists.') from exc
            user.is_staff = True
            user.is_active = True
            user.save()

            # Профиль пользователя
            user_profile, _ = UserProfile.objects.get_or_create(user=user)
            user_profile.phone = phone
            user_profile.postal_code = self.cleaned_data.get('postal_code') or ""
            user_profile.email_marketing_consent = True
            user_profile.birth_date = self.cleaned_data.get('birth_date')
            user_profile.save()

            # Назначаем роль Master
            master_role = Role.objects.filter(name="Master").first()
            # if master_role:
            #     user.userrole_set.create(role=master_role)

            # Профиль мастера
            master = super().save(commit=False)
            master.user = user_profile
            if commit:
                master.save()

            assign_services_to_master(master, selected_services)

            return master

        else:
            master = super().save(commit=False)
            # Редактирование мастера
            user_profile = self.instance.user
            user = user_profile.user

            user.email = self.cleaned_data['email']
            user.first_name = self.cleaned_data['first_name']
            user.last_name = self.cleaned_data['last_name']
            if phone_changed and user.username != phone:
                user.username = phone
            try:
                user.save()
            except IntegrityError as exc:
                self.add_error('phone', 'User with such phone already exists.')
                raise forms.ValidationError('User with such phone already exists.') from exc

            user_profile.phone = phone
            user_profile.postal_code = self.cleaned_data.get('postal_code') or ""
            user_profile.birth_date = self.cleaned_data.get('birth_date')
            user_profile.save()

            current_ids = set(ServiceMaster.objects.filter(
                master=master
            ).values_list('service_id', flat=True))
            new_ids = set(s.id for s in selected_services)

            to_add_ids = new_ids - current_ids
            to_del_ids = current_ids - new_ids

            if to_add_ids:
                add_map = {s.id: s for s in selected_services if s.id in to_add_ids}
                ServiceMaster.objects.bulk_create(
                    [ServiceMaster(service=add_map[sid], master=master) for sid in to_add_ids],
                    ignore_conflicts=True
                )
            if to_del_ids:
                ServiceMaster.objects.filter(master=master, service_id__in=to_del_ids).delete()

            if commit:
                master.save()

            return master

    class Media:
        # ÐÐµÐ±Ð¾Ð»ÑŒÑˆÐ°Ñ ÐºÐ¾ÑÐ¼ÐµÑ‚Ð¸ÐºÐ° Ð´Ð»Ñ Ñ‡ÐµÐºÐ±Ð¾ÐºÑÐ¾Ð² (Ð¾Ð¿Ñ†Ð¸Ð¾Ð½Ð°Ð»ÑŒÐ½Ð¾)
        css = {
            'all': (
                # Ð¼Ð¾Ð¶Ð½Ð¾ Ð¿Ð¾Ð»Ð¾Ð¶Ð¸Ñ‚ÑŒ ÑÑ‚Ð¾Ñ‚ CSS Ð² static Ð¸ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ Ð·Ð´ÐµÑÑŒ
                # Ð¿Ñ€Ð¸Ð¼ÐµÑ€ Ð²ÑÑ‚Ñ€Ð¾ÐµÐ½Ð½Ð¾Ð³Ð¾ Ð¼Ð¸Ð½Ð¸-CSS:
                # admin ÑÐ°Ð¼Ð° Ð¿Ñ€Ð¾Ð³Ð»Ð¾Ñ‚Ð¸Ñ‚ inline-css? ÐžÐ±Ñ‹Ñ‡Ð½Ð¾ Ð»ÑƒÑ‡ÑˆÐµ Ð²Ð½ÐµÑˆÐ½Ð¸Ð¹ Ñ„Ð°Ð¹Ð».
            )
        }


def assign_services_to_master(master, selected_services):
    # 1) Ð¼Ð°ÑÑ‚ÐµÑ€ Ð´Ð¾Ð»Ð¶ÐµÐ½ Ð±Ñ‹Ñ‚ÑŒ ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½
    if not master.pk:
        master.save()

    # 2) Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÐ¼ Ð¿Ð¾ ID, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð½Ðµ Ð±Ñ‹Ð»Ð¾ Ð¾ÑˆÐ¸Ð±ÐºÐ¸ Ñ Ð½ÐµÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½Ð½Ñ‹Ð¼Ð¸ Ð¸Ð½ÑÑ‚Ð°Ð½ÑÐ°Ð¼Ð¸
    service_ids = []
    for s in selected_services:
        sid = getattr(s, "pk", s)  # Ð¿Ð¾Ð´Ð´ÐµÑ€Ð¶Ð¸Ð¼ ÐºÐ°Ðº Ð¾Ð±ÑŠÐµÐºÑ‚Ñ‹, Ñ‚Ð°Ðº Ð¸ ÑƒÐ¶Ðµ id
        if sid:
            service_ids.append(sid)

    if not service_ids:
        return

    # 3) Ð½Ð°Ð¹Ð´Ñ‘Ð¼ ÑƒÐ¶Ðµ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ðµ ÑÐ²ÑÐ·Ð¸, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð½Ðµ Ð´ÑƒÐ±Ð»Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ
    existing = set(
        ServiceMaster.objects
        .filter(master_id=master.pk, service_id__in=service_ids)
        .values_list("service_id", flat=True)
    )

    # 4) ÑÐ¾Ð·Ð´Ð°Ð´Ð¸Ð¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð½ÐµÐ´Ð¾ÑÑ‚Ð°ÑŽÑ‰Ð¸Ðµ ÑÐ²ÑÐ·Ð¸
    for sid in service_ids:
        if sid not in existing:
            ServiceMaster.objects.create(master_id=master.pk, service_id=sid)


class QuarterHourTimeInput(forms.TimeInput):
    input_type = "time"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("attrs", {})
        kwargs["attrs"]["step"] = 900   # 15 минут
        super().__init__(*args, **kwargs)

class MasterAvailabilityForm(forms.ModelForm):
    class Meta:
        model = MasterAvailability
        fields = "__all__"
        widgets = {
            "start_time": forms.SplitDateTimeWidget(
                date_attrs={"type": "date"},
                time_attrs={"type": "time", "step": 900},  # 15 минут
            ),
            "end_time": forms.SplitDateTimeWidget(
                date_attrs={"type": "date"},
                time_attrs={"type": "time", "step": 900},  # 15 минут
            ),
        }

    class Media:
        # Можно оставить CDN, а позже переложить в static
        css = {
            "all": [
                "https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",
                "https://cdn.jsdelivr.net/npm/flatpickr/dist/themes/material_blue.css",
                "admin/css/ma_flatpickr_overrides.css",       # наш небольшой тюнинг (ниже)
            ]
        }
        js = [
            "https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.js",
            "admin/js/quarter_timepicker.js",                 # твой селектор 15 минут
            "admin/js/ma_flatpickr_init.js",                  # инициализация календаря (ниже)
        ]


INTAKE_FIELD_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


class IntakeSchemaWidget(forms.Widget):
    template_name = "core/widgets/intake_schema_widget.html"

    def format_value(self, value):
        if not value:
            return json.dumps({"sections": [], "meta": {}}, ensure_ascii=False)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return value
            return json.dumps(parsed, ensure_ascii=False)
        return json.dumps(value, ensure_ascii=False)

    def get_context(self, name, value, attrs):
        formatted = self.format_value(value)
        try:
            raw = json.loads(formatted)
        except json.JSONDecodeError:
            raw = {"sections": [], "meta": {}}
        context = super().get_context(name, formatted, attrs)
        context["widget"]["builder_value"] = raw
        return context

    class Media:
        css = {"all": ["core/css/intake_builder.css"]}
        js = ["core/js/intake_builder.js"]


class ClientIntakeFormAdminForm(forms.ModelForm):
    schema = forms.JSONField(required=False, widget=IntakeSchemaWidget())

    class Meta:
        model = ClientIntakeForm
        fields = "__all__"

    def clean_schema(self):
        raw = self.cleaned_data.get("schema")
        if not raw:
            return {"sections": [], "meta": {}}
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError(
                    f"Form builder configuration must be valid JSON: {exc}"
                ) from exc
        else:
            data = raw
        if not isinstance(data, dict):
            raise forms.ValidationError("Form builder configuration must be a JSON object.")
        data.setdefault("sections", [])
        data.setdefault("meta", {})

        seen_keys = set()
        for section in data["sections"]:
            if not isinstance(section, dict):
                raise forms.ValidationError("Each section must be an object.")
            fields = section.get("fields") or []
            if not isinstance(fields, list):
                raise forms.ValidationError("Section fields must be a list.")
            for field in fields:
                if not isinstance(field, dict):
                    raise forms.ValidationError("Field definitions must be JSON objects.")
                key = field.get("key")
                if not key:
                    raise forms.ValidationError("Every field must have a key.")
                if not INTAKE_FIELD_KEY_RE.match(str(key)):
                    raise forms.ValidationError(
                        f"Field key '{key}' is invalid. Use letters, digits or underscores and start with a letter."
                    )
                if key in seen_keys:
                    raise forms.ValidationError(f"Field key '{key}' is duplicated.")
                seen_keys.add(key)
        return data

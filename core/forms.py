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
from django.template import TemplateDoesNotExist, engines
from django.utils.text import slugify
from django.utils.safestring import mark_safe
from django.db.models import Prefetch, Q
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.contrib.auth.password_validation import validate_password
from .models import *
from .validators import *


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
        if "unit_price" in self.fields:
            has_price_initial = self.initial.get("unit_price") or getattr(self.instance, "unit_price", None)
            if not has_price_initial and service and getattr(service, "base_price", None) is not None:
                self.fields["unit_price"].initial = service.base_price

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
            'username', 'email', 'first_name', 'last_name',
            'phone', 'birth_date',
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

        if not (self.cleaned_data.get('username') or user.username):
            base = slugify(user.email.split('@')[0]) or 'user'
            candidate = base
            idx = 1
            User = get_user_model()
            while User.objects.filter(username=candidate).exists():
                candidate = f"{base}{idx}"
                idx += 1
            user.username = candidate

        user = self.set_password_and_save(user, commit=commit)

        if commit and hasattr(self, 'save_m2m'):
            self.save_m2m()

        if commit:
            phone = self.cleaned_data.get('phone')
            birth_date = self.cleaned_data.get('birth_date')
            how_heard = self.cleaned_data.get('how_heard')
            email_marketing_consent = self.cleaned_data.get('email_marketing_consent')
            notes = self.cleaned_data.get('notes')

            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.phone = phone
            profile.birth_date = birth_date
            profile.how_heard = how_heard
            profile.personal_discount_percent = self.cleaned_data.get('personal_discount_percent') or 0
            profile.set_marketing_consent(email_marketing_consent)
            profile.notes = notes
            profile.health_conditions = self._collect_health_payload()
            profile.postal_code = self.cleaned_data.get('postal_code', "")

            if created and not hasattr(self, "is_client_register"):
                profile.source = "offline"
            profile.save()

            client_role, _ = Role.objects.get_or_create(name="Client")
            UserRole.objects.get_or_create(user=profile, role=client_role)

        return user


    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if UserProfile.objects.filter(phone=phone).exists():
            raise forms.ValidationError("User with such phone number already exists.")
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
            "phone", "birth_date", "postal_code",
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
            'username',
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
        user.save()

        # Update profile
        phone = self.cleaned_data.get('phone', "")
        birth_date = self.cleaned_data.get('birth_date', None)
        how_heard = self.cleaned_data.get('how_heard', None)
        notes = self.cleaned_data.get('notes', None)

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
        phone = self.cleaned_data.get('phone')
        qs = UserProfile.objects.filter(phone=phone)
        if self.instance.pk:
            qs = qs.exclude(user=self.instance)
        if qs.exists():
            raise forms.ValidationError("User with such phone number already exists.")
        return phone

class ServicesDropdown(forms.CheckboxSelectMultiple):
    template_name = "widget/service_dropdown.html"


class MasterCreateFullForm(forms.ModelForm):
    # Общие поля
    username = forms.CharField()
    email = forms.EmailField()
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    phone = forms.CharField(required=True)
    birth_date = forms.DateField(required=False, widget=forms.SelectDateWidget(years=range(1950, 2030)))

    services = forms.ModelMultipleChoiceField(
        label="Services",
        required=False,
        queryset=Service.objects.select_related("category").order_by("category__name", "name"),
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
        fields = ['profession', 'bio', 'room', 'services']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Если редактируем — заменяем пароли на read-only поле
        if self.instance and self.instance.pk:

            current_ids = ServiceMaster.objects.filter(
                master=self.instance
            ).values_list('service_id', flat=True)
            self.fields['services'].initial = list(current_ids)

            user_profile = self.instance.user
            user = user_profile.user  # сам Django User
            self.fields['password'] = ReadOnlyPasswordHashField(label="Password")
            self.initial['password'] = user.password

            # Удаляем поля пароля
            self.fields.pop('password1')
            self.fields.pop('password2')

            # Заполняем initial для полей пользователя
            self.fields['username'].initial = user.username
            self.fields['email'].initial = user.email
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name

            self.fields['phone'].initial = user_profile.phone
            self.fields['postal_code'].initial = getattr(user_profile, 'postal_code', "")
            self.fields['birth_date'].initial = user_profile.birth_date
        cats = (ServiceCategory.objects
                .order_by("name")
                .prefetch_related("service_set"))
        choices = []
        for cat in cats:
            opts = [(str(s.pk), s.name) for s in cat.service_set.all()]
            if opts:
                choices.append((cat.name, opts))
        # Неотнесённые к категории — в конец
        uncategorized = Service.objects.filter(category__isnull=True).order_by("name")
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
        phone = self.cleaned_data.get('phone')

        qs = UserProfile.objects.filter(phone=phone)

        if self.instance.pk:
            # если редактируем, исключаем текущего пользователя
            qs = qs.exclude(user=self.instance.user.user)

        if qs.exists():
            raise forms.ValidationError("This phone number is already registered!")

        return phone

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if not username:
            return username
        User = get_user_model()
        qs = User.objects.filter(username=username)
        if self.instance.pk and hasattr(self.instance, "user"):
            qs = qs.exclude(pk=self.instance.user.user_id)
        if qs.exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

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
        if not self.instance.pk:
            # Создание нового пользователя
            User = get_user_model()
            user = User.objects.create_user(
                username=self.cleaned_data['username'],
                email=self.cleaned_data['email'],
                password=self.cleaned_data['password1'],
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
            )
            user.is_staff = True
            user.is_active = True
            user.save()

            # Профиль пользователя
            user_profile, _ = UserProfile.objects.get_or_create(user=user)
            user_profile.phone = self.cleaned_data.get('phone')
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

            user.username = self.cleaned_data['username']
            user.email = self.cleaned_data['email']
            user.first_name = self.cleaned_data['first_name']
            user.last_name = self.cleaned_data['last_name']
            user.save()

            user_profile.phone = self.cleaned_data.get('phone')
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


            return master

    class Media:
        # Небольшая косметика для чекбоксов (опционально)
        css = {
            'all': (
                # можно положить этот CSS в static и подключить здесь
                # пример встроенного мини-CSS:
                # admin сама проглотит inline-css? Обычно лучше внешний файл.
            )
        }


def assign_services_to_master(master, selected_services):
    # 1) мастер должен быть сохранён
    if not master.pk:
        master.save()

    # 2) работаем по ID, чтобы не было ошибки с несохранёнными инстансами
    service_ids = []
    for s in selected_services:
        sid = getattr(s, "pk", s)  # поддержим как объекты, так и уже id
        if sid:
            service_ids.append(sid)

    if not service_ids:
        return

    # 3) найдём уже существующие связи, чтобы не дублировать
    existing = set(
        ServiceMaster.objects
        .filter(master_id=master.pk, service_id__in=service_ids)
        .values_list("service_id", flat=True)
    )

    # 4) создадим только недостающие связи
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

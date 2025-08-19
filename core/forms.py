from dal import autocomplete
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import *

# -----------------------------
# Appointment Form
# -----------------------------

class AppointmentForm(forms.ModelForm):
    """
    Custom form for the Appointment model.
    Adds autocomplete functionality for the 'service' field.
    """
    status = forms.ModelChoiceField(
        queryset=AppointmentStatus.objects.all(),
        required=True,
        label="Appointment status"
    )
    promocode = forms.CharField(required=False, label="Promocode")
    class Meta:
        model = Appointment
        fields = '__all__'
        widgets = {
            'service': autocomplete.ModelSelect2(url='service-autocomplete')
        }
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        instance = self.instance

        # Обнови instance перед вызовом clean()
        instance.master = cleaned_data.get("master")
        instance.start_time = cleaned_data.get("start_time")
        instance.service = cleaned_data.get("service")
        promocode_str = cleaned_data.get("promocode")
        service = cleaned_data.get("service")
        try:
            instance.clean()
        except ValidationError as e:
            raise forms.ValidationError(e)

        if promocode_str:
            try:
                code = PromoCode.objects.get(code=promocode_str.upper())
                if not code.is_valid_for(service):
                    raise forms.ValidationError("Этот промокод недействителен для выбранной услуги или срока.")
                cleaned_data["applied_promocode"] = code
            except PromoCode.DoesNotExist:
                raise forms.ValidationError("Неверный промокод.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.save()

        promocode = self.cleaned_data.get("applied_promocode")
        if promocode:
            discount = instance.service.base_price * (promocode.discount_percent / 100)
            AppointmentPromoCode.objects.create(
                appointment=instance,
                promocode=promocode,
                discount_applied=discount
            )

        new_status = self.cleaned_data['status']
        profile = getattr(self.user, "userprofile", None)
        print(self.user)
        latest = instance.appointmentstatushistory_set.order_by('-set_at').first()
        if not latest or latest.status != new_status:
            AppointmentStatusHistory.objects.create(
                appointment=instance,
                status=new_status,
                set_by=profile
            )

        return instance

# -----------------------------
# Custom User Creation Form
# -----------------------------

class CustomUserCreationForm(UserCreationForm):
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
    # новые поля
    address = forms.CharField(
        required=False,
        label="Address",
        widget=forms.Textarea(attrs={"rows": 1})
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
            'password1', 'password2',
            'is_staff', 'is_active', 'is_superuser',
            'groups', "address", "email_marketing_consent",
            "notes"
        ]

    def save(self, commit=True):
        """
        Overridden save method to:
        - Set password
        - Create and populate UserProfile
        - Assign roles to the new user
        """
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.save()

        # Create or update UserProfile
        phone = self.cleaned_data.get('phone')
        birth_date = self.cleaned_data.get('birth_date')
        address = self.cleaned_data.get('address')
        how_heard = self.cleaned_data.get('how_heard')
        email_marketing_consent = self.cleaned_data.get('email_marketing_consent')
        notes = self.cleaned_data.get('notes')
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.phone = phone
        profile.birth_date = birth_date
        profile.address = address
        profile.how_heard = how_heard
        profile.set_marketing_consent(email_marketing_consent)
        profile.notes = notes

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

class CustomUserChangeForm(UserChangeForm):
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
        label="Address",
        widget=forms.Textarea(attrs={"rows": 1})
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
            'address',
            'how_heard',
            'email_marketing_consent',
            'notes',
            'files'
        ]

    def __init__(self, *args, **kwargs):
        """
        Populate form with data from related UserProfile and UserRole
        """
        super().__init__(*args, **kwargs)

        if self.instance and hasattr(self.instance, 'userprofile'):
            self.fields['phone'].initial = self.instance.userprofile.phone
            self.fields['birth_date'].initial = self.instance.userprofile.birth_date
            self.fields['address'].initial = self.instance.userprofile.address
            self.fields['how_heard'].initial = self.instance.userprofile.how_heard
            self.fields['email_marketing_consent'].initial = self.instance.userprofile.email_marketing_consent
            self.fields['notes'].initial = self.instance.userprofile.notes


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
        address = self.cleaned_data.get('address', "")
        how_heard = self.cleaned_data.get('how_heard', None)
        notes = self.cleaned_data.get('notes', None)

        email_marketing_consent = self.cleaned_data.get('email_marketing_consent', False)
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.phone = phone
        profile.birth_date = birth_date
        profile.address = address
        profile.how_heard = how_heard
        profile.notes = notes
        profile.set_marketing_consent(email_marketing_consent)
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


class MasterCreateFullForm(forms.ModelForm):
    # Общие поля
    username = forms.CharField()
    email = forms.EmailField()
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    phone = forms.CharField(required=True)
    birth_date = forms.DateField(required=False, widget=forms.SelectDateWidget(years=range(1950, 2030)))

    password1 = forms.CharField(widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(widget=forms.PasswordInput, required=False)
    address = forms.CharField(
        required=False,
        label="Address",
        widget=forms.Textarea(attrs={"rows": 1})
    )
    class Meta:
        model = MasterProfile
        fields = ['profession', 'bio', 'work_start', 'work_end', 'room']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Если редактируем — заменяем пароли на read-only поле
        if self.instance and self.instance.pk:
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
            self.fields['address'].initial = user_profile.address
            self.fields['birth_date'].initial = user_profile.birth_date

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
            qs = qs.exclude(user=self.instance.user)

        if qs.exists():
            raise forms.ValidationError("This phone number is already registered!")

        return phone

    def save(self, commit=True):
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
            user_profile = UserProfile.objects.create(
                user=user,
                phone=self.cleaned_data.get('phone'),
                address=self.cleaned_data.get('address'),
                email_marketing_consent=True,
                birth_date=self.cleaned_data.get('birth_date')
            )

            # Назначаем роль Master
            master_role = Role.objects.filter(name="Master").first()
            if master_role:
                user.userrole_set.create(role=master_role)

            # Профиль мастера
            master = super().save(commit=False)
            master.user = user_profile
            if commit:
                master.save()
            return master

        else:
            # Редактирование мастера
            user_profile = self.instance.user
            user = user_profile.user

            user.username = self.cleaned_data['username']
            user.email = self.cleaned_data['email']
            user.first_name = self.cleaned_data['first_name']
            user.last_name = self.cleaned_data['last_name']
            user.save()

            user_profile.phone = self.cleaned_data.get('phone')
            user_profile.address = self.cleaned_data.get('address')
            user_profile.birth_date = self.cleaned_data.get('birth_date')
            user_profile.save()

            return super().save(commit=commit)
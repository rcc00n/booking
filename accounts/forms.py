from django import forms
from django.contrib.auth.forms import UserCreationForm
from core.models import Role, CustomUserDisplay, UserRole, UserProfile

class PublicRegistrationForm(UserCreationForm):
    email       = forms.EmailField(required=True)
    phone       = forms.CharField(label='Телефон')
    birth_date  = forms.DateField(label='Дата рождения', required=False,
                                  widget=forms.SelectDateWidget(years=range(1940, 2026)))
    # Клиент может выбрать роль; по ТЗ главная роль — «Client»
    roles       = forms.ModelChoiceField(
        label='Тип пользователя',
        queryset=Role.objects.filter(name__in=['Client', 'Master']),
        empty_label=None
    )

    class Meta:
        model  = CustomUserDisplay
        fields = ('username', 'email', 'phone', 'birth_date', 'roles',
                  'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()

            # профиль
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    'phone': self.cleaned_data['phone'],
                    'birth_date': self.cleaned_data['birth_date'],
                })

            # одна выбранная роль
            role = self.cleaned_data['roles']
            UserRole.objects.create(user=user, role=role)

        return user

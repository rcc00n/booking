from django.shortcuts import render

# Create your views here.
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from core.models import CustomUserDisplay
from .forms import PublicRegistrationForm
from .decorators import role_required

class RegisterView(CreateView):
    model         = CustomUserDisplay
    form_class    = PublicRegistrationForm
    template_name = 'accounts/register.html'
    success_url   = reverse_lazy('accounts:login')

class LoginView(auth_views.LoginView):
    template_name = 'accounts/login.html'

class LogoutView(auth_views.LogoutView):
    pass

# ---------- Dashboards ----------
@role_required('Client')
def client_dashboard(request):
    return TemplateView.as_view(template_name='accounts/dashboard_client.html')(request)

@role_required('Master')
def master_dashboard(request):
    return TemplateView.as_view(template_name='accounts/dashboard_master.html')(request)

@role_required('Admin')  # или 'Reception'
def admin_dashboard(request):
    return TemplateView.as_view(template_name='accounts/dashboard_admin.html')(request)


def dashboard_router(request):
    """
    После логина перебрасывает пользователя
    в нужный кабинет в зависимости от роли.
    """
    role_qs = request.user.userrole_set.select_related('role')
    role_names = {ur.role.name for ur in role_qs}

    if 'Admin' in role_names:
        return redirect('accounts:admin')
    if 'Master' in role_names:
        return redirect('accounts:master')
    return redirect('accounts:client')  # по умолчанию клиент

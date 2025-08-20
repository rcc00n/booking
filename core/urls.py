# core/urls.py
from django.urls import path
# from core.views import ClientDashboardView
from .views import client_dashboard, health_edit, health_view

app_name = "core"

urlpatterns = [
    # личный кабинет клиента
        path("accounts/", client_dashboard, name="client-dashboard"),
        path("health/edit/", health_edit, name="health-edit"),
        path("health/", health_view, name="health-view"),
]

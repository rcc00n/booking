"""
URL configuration for the *booking* project.

Определяет корневые маршруты сайта и подключает URL‑конфиги
приложений.
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from core.autocomplete import ServiceAutocomplete

urlpatterns = [
    # --- административная панель ---
    path("admin/", admin.site.urls),

    # --- публичная часть / кабинеты пользователей ---
    # Если приложение *accounts* находится в пакете booking.accounts,
    # замените на "booking.accounts.urls".
    path("accounts/", include("accounts.urls", namespace="accounts")),

    # --- вспомогательные сервис‑эндпойнты ---
    path(
        "autocomplete/service-master/",
        ServiceAutocomplete.as_view(),
        name="service-master-autocomplete",
    ),

    # --- корневой URL: переадресуем на страницу логина ---
    path("", RedirectView.as_view(pattern_name="accounts:login", permanent=False)),
]

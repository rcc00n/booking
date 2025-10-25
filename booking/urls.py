"""
URL configuration for the booking project.

Routes:
  /admin/                 → Django admin
  /accounts/              → модуль аккаунтов (login/register/dashboard/...) + каталог (на корне)
  /autocomplete/...       → Select2 endpoints
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.autocomplete import ServiceAutocomplete
from django.views.generic import RedirectView, TemplateView
from core.views import (
    service_search,
    service_price,
    service_promocodes_api,
    terminal_connection_token,
    api_terminal_start,
)
from core.payments.stripe_api import stripe_webhook
from core.admin import stats_view
from accounts.views import health_view, health_edit
urlpatterns = [
    path("admin/", admin.site.urls),

    # ВАЖНО: подключаем accounts БЕЗ namespace, чтобы {% url 'register' %} и т.п. работали
    path("accounts/", include("accounts.urls")),

    path("autocomplete/service/", ServiceAutocomplete.as_view(), name="service-autocomplete"),
    path("admin/stats/", admin.site.admin_view(stats_view), name="admin-stats"),
    path("api/service/<uuid:pk>/price/", service_price, name="service-price"),
    path(
        "accounts/api/services/<slug:service_id>/promocodes/",
        service_promocodes_api,
        name="service_promocodes_api",
    ),

    path("", RedirectView.as_view(pattern_name="client-dashboard", permanent=False)),
    # Ничего из core тут не монтируем, чтобы не перехватывать /accounts/
    path('accounts/api/services/search/', service_search, name='service-search'),

    path("health/edit/", health_edit, name="health-edit"),
    path("health/", health_view, name="health-view"),
    path("stripe/webhook/", stripe_webhook, name="stripe-webhook"),
    path(
        "legal/email-updates/",
        TemplateView.as_view(template_name="legal/email_updates.html"),
        name="legal-email-updates",
    ),
    path(
        "legal/data-processing/",
        TemplateView.as_view(template_name="legal/data_processing.html"),
        name="legal-data-processing",
    ),
    path("api/terminal/connection_token/", terminal_connection_token, name="terminal-conn-token"),
    path(
        "api/appointment/<uuid:appt_id>/terminal/start/",
        api_terminal_start,
        name="api-terminal-start",
    ),
]

if settings.MEDIA_URL.startswith("/") and settings.MEDIA_ROOT:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


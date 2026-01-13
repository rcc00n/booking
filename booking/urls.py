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
from core.autocomplete import ServiceAutocomplete, MasterUserProfileAutocomplete  # // CHANGED
from django.views.generic import RedirectView
from core.views import (
    service_search,
    service_translations_api,
    service_price,
    service_promocodes_api,
    terminal_connection_token,
    api_terminal_start,
    admin_item_status_update,
    admin_item_reschedule,
    SupportDocumentDetailView,
)
from core.payments.stripe_api import stripe_webhook
from core.admin import stats_view
from accounts.views import health_view, health_edit
from core.models import SupportDocument
from booking.api import AvailabilityView, AppointmentCreateView, AppointmentItemStatusView
urlpatterns = [
    path("admin/api/appointment-items/<uuid:item_id>/status/", admin_item_status_update, name="admin-item-status-update"),
    path("admin/api/appointment-items/<uuid:item_id>/reschedule/", admin_item_reschedule, name="admin-item-reschedule"),
path("", include("core.urls")),
    path("admin/", admin.site.urls),

    # ВАЖНО: подключаем accounts БЕЗ namespace, чтобы {% url 'register' %} и т.п. работали
    path("accounts/", include("accounts.urls")),
    path("autocomplete/service/", ServiceAutocomplete.as_view(), name="service-autocomplete"),
    path("autocomplete/master/", MasterUserProfileAutocomplete.as_view(), name="master-userprofile-autocomplete"),  # // CHANGED
    path("admin/stats/", admin.site.admin_view(stats_view), name="admin-stats"),
    path("api/service/<uuid:pk>/price/", service_price, name="service-price"),
    path("api/availability/", AvailabilityView.as_view(), name="api-availability"),
    path("api/appointments/", AppointmentCreateView.as_view(), name="api-appointments"),
    path(
        "api/items/<uuid:item_id>/status/",
        AppointmentItemStatusView.as_view(),
        name="api-item-status",
    ),
    path(
        "accounts/api/services/<slug:service_id>/promocodes/",
        service_promocodes_api,
        name="service_promocodes_api",
    ),

    path("", RedirectView.as_view(pattern_name="client-dashboard", permanent=False)),
    # Ничего из core тут не монтируем, чтобы не перехватывать /accounts/
    path('accounts/api/services/search/', service_search, name='service-search'),
    path('accounts/api/services/translations/', service_translations_api, name='service-translations'),

    path("health/edit/", health_edit, name="health-edit"),
    path("health/", health_view, name="health-view"),
    path("stripe/webhook/", stripe_webhook, name="stripe-webhook"),
    path(
        "legal/email-updates/",
        SupportDocumentDetailView.as_view(),
        {"document_type": SupportDocument.DocumentType.EMAIL_UPDATES},
        name="legal-email-updates",
    ),
    path(
        "legal/data-processing/",
        SupportDocumentDetailView.as_view(),
        {"document_type": SupportDocument.DocumentType.PRIVACY_NOTICE},
        name="legal-data-processing",
    ),
    path(
        "legal/terms/",
        SupportDocumentDetailView.as_view(),
        {"document_type": SupportDocument.DocumentType.TERMS_AND_CONDITIONS},
        name="legal-terms",
    ),
    path(
        "support/<slug:slug>/",
        SupportDocumentDetailView.as_view(),
        name="support-document-detail",
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

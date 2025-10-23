from django.urls import path
from .views import (
    RoleBasedLoginView,
    ClientDashboardView,
    MasterDashboardView,
    ClientAppointmentsListView,
    ClientRegisterView,
    MainMenuView,  # можно оставить, если где-то используется
    ProductSalesView,
    api_verification_begin,
    api_verification_confirm,
    api_verification_resend,
)
from django.contrib.auth.views import LogoutView
from core.views import (
    public_mainmenu, api_availability, api_book,
    api_appointment_cancel, api_appointment_reschedule,   # ?+? D'D_D?D?D?D,?,?O
    api_cart_summary, api_cart_add, api_cart_remove,
    api_payment_verify,
)
from core.payments.stripe_api import (
    stripe_create_cart_intent,
    stripe_finalize_cart_booking,
    stripe_list_cards,
    stripe_set_default_card,
    stripe_no_show_charge,
    stripe_webhook
)


urlpatterns = [
    # Публичная главная (каталог) для всех
    path("", public_mainmenu, name="client-dashboard"),
    path("home/", public_mainmenu, name="mainmenu"),

    # Аутентификация
    path("login/",    RoleBasedLoginView.as_view(),   name="login"),
    path("register/", ClientRegisterView.as_view(),   name="register"),

    # Личные кабинеты (как у тебя уже реализовано)
    path("dashboard/", ClientDashboardView.as_view(), name="dashboard"),
    path("master/",    MasterDashboardView.as_view(), name="master_dashboard"),
    path("master/sales/", ProductSalesView.as_view(), name="product-sales"),
    path("client/appointments/", ClientAppointmentsListView.as_view(), name="client_appointments"),

    # API бронирования (требует логина)
    path("api/availability/", api_availability, name="api-availability"),
    path("api/book/",         api_book,         name="api-book"),
    path("api/cart/",             api_cart_summary,   name="api-cart"),
    path("api/cart/add/",        api_cart_add,       name="api-cart-add"),
    path("api/cart/<int:item_id>/remove/", api_cart_remove, name="api-cart-remove"),
    path("api/verification/begin/",   api_verification_begin,   name="api-verify-begin"),
    path("api/verification/confirm/", api_verification_confirm, name="api-verify-confirm"),
    path("api/verification/resend/",  api_verification_resend,  name="api-verify-resend"),
    path("api/payments/cart/create-intent/", stripe_create_cart_intent, name="stripe-cart-intent"),
    path("api/payments/cart/finalize/", stripe_finalize_cart_booking, name="stripe-cart-finalize"),
    path("api/payments/cards/", stripe_list_cards, name="stripe-cards"),
    path("api/payments/cards/set-default/", stripe_set_default_card, name="stripe-set-default"),
    path("api/payments/no-show/charge/", stripe_no_show_charge, name="stripe-no-show-charge"),
    path(
        "api/appointment/<uuid:appt_id>/payments/verify/",
        api_payment_verify,
        name="api-payment-verify",
    ),
    path("api/stripe/webhook/", stripe_webhook, name="api-stripe-webhook"),
    path("logout/", LogoutView.as_view(next_page="/accounts/"), name="logout"),
    
    path("api/appointment/<uuid:appt_id>/cancel/",     api_appointment_cancel,     name="api-appt-cancel"),
    path("api/appointment/<uuid:appt_id>/reschedule/", api_appointment_reschedule, name="api-appt-reschedule"),
]







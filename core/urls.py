from django.urls import path

from core.views import payment_refund_view

urlpatterns = [
    path(
        "admin/core/payment/<uuid:pk>/refund/",
        payment_refund_view,
        name="admin-payment-refund",
    ),
]

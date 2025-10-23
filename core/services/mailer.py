"""
Mail helpers for delivering payment receipts.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string


def _resolve_client_email(payment: Any) -> str | None:
    appointment = getattr(payment, "appointment", None)
    client = getattr(appointment, "client", None)
    if not client:
        return None

    email = getattr(client, "email", None)
    if email:
        return email

    user = getattr(client, "user", None)
    if user:
        return (getattr(user, "email", "") or "").strip() or None
    return None


def _resolve_client_name(payment: Any) -> str:
    appointment = getattr(payment, "appointment", None)
    client = getattr(appointment, "client", None)
    if not client:
        return ""
    name_getter = getattr(client, "get_full_name", None)
    if callable(name_getter):
        name = name_getter()
        if name:
            return name
    user = getattr(client, "user", None)
    if user:
        user_full_name = getattr(user, "get_full_name", None)
        if callable(user_full_name):
            name = user_full_name()
            if name:
                return name
        if getattr(user, "username", ""):
            return user.username
    return ""


def send_payment_receipt_email(payment, pdf_bytes: bytes) -> bool:
    """
    Compose and send the payment receipt email with the PDF attached.
    """
    if not payment or not pdf_bytes:
        return False

    appointment = getattr(payment, "appointment", None)
    client = getattr(appointment, "client", None)
    if not (appointment and client):
        return False

    client_email = _resolve_client_email(payment)
    if not client_email:
        return False

    subject = render_to_string("emails/payment_receipt_subject.txt", {"payment": payment}).strip()
    body = render_to_string(
        "emails/payment_receipt_body.txt",
        {
            "payment": payment,
            "client_name": _resolve_client_name(payment),
            "appointment_datetime": getattr(appointment, "start_time", None),
            "business": {
                "name": getattr(settings, "BUSINESS_NAME", "Malva Booking"),
            },
        },
    )

    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[client_email],
        bcc=[getattr(settings, "BUSINESS_BCC_EMAIL", "")] if getattr(settings, "BUSINESS_BCC_EMAIL", "") else None,
        reply_to=[
            getattr(settings, "BUSINESS_SUPPORT_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        ],
    )
    filename = f"receipt_{payment.id}.pdf"
    msg.attach(filename, pdf_bytes, "application/pdf")
    msg.send(fail_silently=False)
    return True

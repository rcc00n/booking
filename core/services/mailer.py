"""
Mail helpers for delivering payment receipts.
"""
from __future__ import annotations

from typing import Any
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from core.services.pricing import get_appointment_grand_total
from core.services.payments import get_total_received_for_appointment


def _quantize(amount: Any) -> Decimal:
    if isinstance(amount, Decimal):
        try:
            return amount.quantize(Decimal("0.01"))
        except Exception:
            return Decimal("0.00")
    if amount in (None, "", "null"):
        return Decimal("0.00")
    try:
        return Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


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

    grand_total = _quantize(get_appointment_grand_total(appointment))
    received_to_date = _quantize(get_total_received_for_appointment(appointment))
    balance_due = grand_total - received_to_date
    overpaid_amount = Decimal("0.00")
    if balance_due < Decimal("0.00"):
        overpaid_amount = _quantize(-balance_due)
        balance_due = Decimal("0.00")
    else:
        balance_due = _quantize(balance_due)
    totals_context = {
        "grand_total": grand_total,
        "received_to_date": received_to_date,
        "balance_due": balance_due,
        "overpaid_amount": overpaid_amount,
        "currency": (payment.currency or getattr(settings, "STRIPE_CURRENCY", "cad") or "cad").upper(),
    }

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
            "totals": totals_context,
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

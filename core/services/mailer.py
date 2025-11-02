"""
Mail helpers for delivering payment and refund receipts.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from core.models import PaymentRefund
from core.services.payments import get_total_received_for_appointment
from core.services.pricing import get_appointment_grand_total

logger = logging.getLogger(__name__)


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


def _metadata_lookup(payment: Any, key: str) -> str:
    metadata = getattr(payment, "metadata", None)
    if isinstance(metadata, dict):
        value = metadata.get(key)
        if isinstance(value, str):
            return value.strip()
        if value is not None:
            return str(value).strip()
    return ""


def send_refund_receipt_email(refund: PaymentRefund, pdf_bytes: bytes) -> bool:
    """
    Send a refund receipt email with the generated PDF attachment to the client.
    """
    if not refund or not pdf_bytes:
        return False

    payment = getattr(refund, "payment", None)
    if payment is None:
        logger.warning("Refund %s: missing payment reference; skipping email", getattr(refund, "pk", "?"))
        return False

    appointment = getattr(payment, "appointment", None)

    client_email = _resolve_client_email(payment) or _metadata_lookup(payment, "client_email")
    if not client_email:
        logger.warning("Refund %s: no client email found; skipping email", refund.pk)
        return False

    client_name = (
        _resolve_client_name(payment)
        or _metadata_lookup(payment, "client_name")
        or "Client"
    )

    currency = (getattr(payment, "currency", None) or getattr(settings, "STRIPE_CURRENCY", "cad") or "cad").upper()

    ctx = {
        "client_name": client_name,
        "refund": {
            "id": str(refund.pk),
            "amount": getattr(refund, "amount", None),
            "currency": currency,
        },
        "appointment_datetime": getattr(appointment, "start_time", None),
    }

    subject = render_to_string("emails/refund_receipt_subject.txt", ctx).strip()
    body = render_to_string("emails/refund_receipt_body.txt", ctx)

    bcc_email = getattr(settings, "BUSINESS_BCC_EMAIL", "")
    reply_to_email = getattr(settings, "BUSINESS_SUPPORT_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", ""))

    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[client_email],
        bcc=[bcc_email] if bcc_email else None,
        reply_to=[reply_to_email] if reply_to_email else None,
    )
    msg.attach(f"refund_receipt_{refund.pk}.pdf", pdf_bytes, "application/pdf")

    try:
        msg.send(fail_silently=False)
        return True
    except Exception as exc:  # noqa: BLE001 - email failure should not break refund flow
        logger.exception("Failed to send refund receipt email for refund %s: %s", refund.pk, exc)
        return False

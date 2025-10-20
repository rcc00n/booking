"""
Receipt generation services for payments.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timezone import localtime

from core.models import AppointmentItem, Payment
from core.utils.pdf import render_html_to_pdf


@dataclass
class ReceiptTotals:
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    currency: str


def _quantize(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return value.quantize(Decimal("0.01"))


def _payment_totals(payment: Payment, items: Iterable[AppointmentItem]) -> ReceiptTotals:
    subtotal = Decimal("0.00")
    for item in items:
        price = getattr(item, "final_price", None) or getattr(item, "unit_price", None) or Decimal("0.00")
        subtotal += _quantize(price)

    total = _quantize(payment.amount_received or payment.amount or Decimal("0.00"))

    discount_total = subtotal - total
    if discount_total < Decimal("0.00"):
        discount_total = Decimal("0.00")

    metadata: Dict[str, Any] = payment.metadata or {}
    cart_pricing = metadata.get("cart_pricing") if isinstance(metadata, dict) else {}
    computed_tax = Decimal("0.00")
    if isinstance(cart_pricing, dict):
        tax_minor = cart_pricing.get("tax_total")
        if isinstance(tax_minor, int):
            computed_tax = Decimal(tax_minor) / Decimal("100")
        else:
            tax_decimal = cart_pricing.get("tax_total_decimal")
            if isinstance(tax_decimal, (int, float, str)):
                try:
                    computed_tax = Decimal(str(tax_decimal))
                except Exception:
                    computed_tax = Decimal("0.00")

    return ReceiptTotals(
        subtotal=_quantize(subtotal),
        discount_total=_quantize(discount_total),
        tax_total=_quantize(computed_tax),
        total=total,
        currency=(payment.currency or settings.STRIPE_CURRENCY or "cad").upper(),
    )


def build_payment_context(payment: Payment) -> Dict[str, Any]:
    appointment = payment.appointment
    client = getattr(appointment, "client", None)
    user = getattr(client, "user", None)

    items_qs = []
    if appointment:
        items_qs = list(
            appointment.items.select_related(
                "service",
                "master__user__user",
            )
            .all()
        )

    totals = _payment_totals(payment, items_qs)

    business = {
        "name": getattr(settings, "BUSINESS_NAME", "Malva Booking"),
        "address": getattr(settings, "BUSINESS_ADDRESS", ""),
        "phone": getattr(settings, "BUSINESS_PHONE", ""),
        "email": getattr(settings, "BUSINESS_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        "support_email": getattr(settings, "BUSINESS_SUPPORT_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        "website": getattr(settings, "BUSINESS_WEBSITE", ""),
    }

    def _master_name(item: AppointmentItem) -> str:
        master = getattr(item, "master", None)
        if not master:
            return ""
        profile_user = getattr(master, "user", None)
        if profile_user and hasattr(profile_user, "get_full_name"):
            name = profile_user.get_full_name().strip()
            if name:
                return name
        if profile_user and getattr(profile_user, "user", None):
            name = profile_user.user.get_full_name().strip()
            if name:
                return name
        return str(master)

    items_payload: List[Dict[str, Any]] = []
    for item in items_qs:
        start_dt = localtime(item.start_time) if getattr(item, "start_time", None) else None
        items_payload.append(
            {
                "name": getattr(getattr(item, "service", None), "name", ""),
                "master": _master_name(item),
                "duration_min": item.duration_min if hasattr(item, "duration_min") else None,
                "start_at": start_dt,
                "price": _quantize(getattr(item, "final_price", None) or getattr(item, "unit_price", None)),
            }
        )

    return {
        "payment": payment,
        "appointment": appointment,
        "client": client,
        "client_contact": {
            "name": getattr(client, "get_full_name", lambda: "")(),
            "email": getattr(user, "email", ""),
            "phone": getattr(client, "phone", ""),
        },
        "items": items_payload,
        "totals": totals,
        "issued_at": timezone.now(),
        "business": business,
        "receipt_number": getattr(payment, "public_id", None) or str(payment.pk),
    }


def generate_payment_receipt_pdf(payment_id: str) -> bytes:
    payment = (
        Payment.objects.select_related(
            "appointment__client__user",
        )
        .prefetch_related("appointment__items__service", "appointment__items__master__user__user")
        .get(pk=payment_id)
    )
    context = build_payment_context(payment)
    html = render_to_string("pdf/payment_receipt.html", context)
    return render_html_to_pdf(html)


def persist_payment_receipt(payment_id: str, force: bool = False) -> str:
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.receipt_pdf and not force:
            return payment.receipt_pdf.name

    pdf_bytes = generate_payment_receipt_pdf(payment_id)

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.receipt_pdf and not force:
            return payment.receipt_pdf.name

        if payment.receipt_pdf and force:
            payment.receipt_pdf.delete(save=False)

        filename = f"receipt_{payment.pk}.pdf"
        payment.receipt_pdf.save(filename, ContentFile(pdf_bytes), save=False)
        payment.save(update_fields=["receipt_pdf", "updated_at"])

        stored_path = payment.receipt_pdf.name

    return stored_path

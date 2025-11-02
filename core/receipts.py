"""
Refund receipt helpers that bridge the existing payment receipt context builders.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timezone import localtime

from core.models import PaymentRefund
from core.services.receipts import build_payment_context
from core.utils.pdf import render_html_to_pdf

logger = logging.getLogger(__name__)


def _refund_currency(payment_context: Dict[str, Any], payment) -> str:
    totals = payment_context.get("totals")
    currency = getattr(payment, "currency", None)
    if currency:
        return str(currency).upper()
    if totals is not None:
        currency = getattr(totals, "currency", None)
        if currency:
            return str(currency).upper()
    return getattr(settings, "STRIPE_CURRENCY", "CAD").upper()


def generate_refund_receipt_pdf(refund: PaymentRefund) -> bytes:
    """
    Render a PDF refund receipt using the refund_receipt.html template.
    Reuses the payment receipt context while augmenting it with refund-specific fields.
    """
    if refund is None:
        logger.warning("generate_refund_receipt_pdf called with no refund instance")
        return b""

    payment = getattr(refund, "payment", None)
    if payment is None:
        logger.warning("Refund %s has no payment associated; skipping receipt generation", refund.pk)
        return b""

    context = build_payment_context(payment)

    issued_at = localtime(refund.created_at) if getattr(refund, "created_at", None) else timezone.now()
    receipt_number = f"R-{refund.pk}"
    currency = _refund_currency(context, payment)

    context.update(
        {
            "issued_at": issued_at,
            "receipt_number": receipt_number,
            "refund": {
                "id": str(refund.pk),
                "amount": getattr(refund, "amount", None),
                "currency": currency,
                "created_at": getattr(refund, "created_at", None),
            },
        }
    )

    # Keep appointment reference in sync with the refund in case the payment context lacks it.
    if "appointment" not in context or context["appointment"] is None:
        context["appointment"] = getattr(refund, "appointment", None)

    html = render_to_string("refund_receipt.html", context)
    return render_html_to_pdf(html)


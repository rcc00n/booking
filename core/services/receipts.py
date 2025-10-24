"""
Receipt generation services for payments.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timezone import localtime

from core.models import AppointmentItem, Payment
from core.services.pricing import compute_appointment_pricing, PricingComputationError, get_appointment_grand_total
from core.utils.pdf import render_html_to_pdf
from core.services.payments import get_total_received_for_appointment

ZERO = Decimal("0.00")


def _quantize(value: Decimal | None) -> Decimal:
    if value is None:
        return ZERO
    return value.quantize(Decimal("0.01"))


def _to_decimal(value: Any) -> Decimal:
    if value in (None, "", "null"):
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def _decimal_from_minor(value: Any) -> Decimal:
    """
    Convert an integer (in minor units) or stringified integer to a Decimal dollar value.
    """
    if value in (None, "", "null"):
        return ZERO
    try:
        if isinstance(value, int):
            return Decimal(value) / Decimal("100")
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return Decimal(int(value.strip())) / Decimal("100")
        return _to_decimal(value)
    except Exception:
        return ZERO


def _parse_metadata(metadata: Any) -> Dict[str, Any]:
    if isinstance(metadata, dict):
        return dict(metadata)
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except json.JSONDecodeError:
            return {}
    return {}


@dataclass
class PricingLine:
    name: str = ""
    base_price: Decimal = ZERO
    discount_amount: Decimal = ZERO
    final_price: Decimal = ZERO
    tax_amount: Decimal = ZERO
    total_with_tax: Decimal = ZERO
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_payload(
        self,
        appointment_item: Optional[AppointmentItem] = None,
    ) -> Dict[str, Any]:
        """
        Render a template-ready row, merging appointment data (master, start time, duration).
        """
        service_name = self.name
        master_name = ""
        start_at = None
        duration_min = None
        if appointment_item:
            service = getattr(appointment_item, "service", None)
            if not service_name and service:
                service_name = getattr(service, "name", "") or service_name
            master_name = _master_display(appointment_item)
            duration_min = getattr(appointment_item, "duration_min", None)
            start_raw = getattr(appointment_item, "start_time", None)
            if start_raw:
                try:
                    start_at = localtime(start_raw)
                except Exception:
                    start_at = start_raw

        # For the PDF we show the pre-discount amount in the main column.
        display_price = self.base_price if self.base_price > ZERO else self.final_price
        return {
            "name": service_name,
            "master": master_name,
            "duration_min": duration_min,
            "start_at": start_at,
            "base_price": self.base_price,
            "discount_amount": self.discount_amount,
            "final_price": self.final_price,
            "tax_amount": self.tax_amount,
            "total_with_tax": self.total_with_tax,
            "display_price": display_price,
        }


@dataclass
class ReceiptTotals:
    currency: str
    base_subtotal: Decimal
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    service_fee: Decimal
    processing_fee: Decimal
    total: Decimal
    grand_total: Decimal = ZERO
    received_to_date: Decimal = ZERO
    balance_due: Decimal = ZERO
    overpaid_amount: Decimal = ZERO
    summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PricingSummary:
    currency: str
    base_subtotal: Decimal = ZERO
    subtotal: Decimal = ZERO
    discount_total: Decimal = ZERO
    tax_total: Decimal = ZERO
    service_fee: Decimal = ZERO
    processing_fee: Decimal = ZERO
    total: Decimal = ZERO
    items: List[PricingLine] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_totals(self) -> ReceiptTotals:
        details = dict(self.details or {})
        return ReceiptTotals(
            currency=self.currency,
            base_subtotal=_quantize(self.base_subtotal),
            subtotal=_quantize(self.subtotal),
            discount_total=_quantize(self.discount_total),
            tax_total=_quantize(self.tax_total),
            service_fee=_quantize(self.service_fee),
            processing_fee=_quantize(self.processing_fee),
            total=_quantize(self.total),
            summary=details,
        )

    def normalized(self) -> "PricingSummary":
        """
        Ensure totals are consistent with line items. Metadata can be missing/partial;
        reconcile sums to avoid showing zeros on the receipt.
        """
        if self.items:
            sum_base = sum((line.base_price for line in self.items), ZERO)
            sum_final = sum((line.final_price for line in self.items), ZERO)
            sum_discount = sum((line.discount_amount for line in self.items), ZERO)
            sum_tax = sum((line.tax_amount for line in self.items), ZERO)
            if self.base_subtotal <= ZERO and sum_base > ZERO:
                self.base_subtotal = _quantize(sum_base)
            if self.subtotal <= ZERO and sum_final > ZERO:
                self.subtotal = _quantize(sum_final)
            if self.discount_total <= ZERO and sum_discount > ZERO:
                self.discount_total = _quantize(sum_discount)
            if self.tax_total <= ZERO and sum_tax > ZERO:
                self.tax_total = _quantize(sum_tax)
        computed_total = _quantize(self.subtotal + self.tax_total + self.service_fee + self.processing_fee)
        if self.total <= ZERO and computed_total > ZERO:
            self.total = computed_total
        return self


def _pricing_from_metadata(payment: Payment, metadata: Dict[str, Any]) -> Optional[PricingSummary]:
    summary = metadata.get("cart_pricing")
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except json.JSONDecodeError:
            summary = None
    if not isinstance(summary, dict):
        return None

    currency = (
        summary.get("currency")
        or metadata.get("cart_currency")
        or payment.currency
        or getattr(settings, "STRIPE_CURRENCY", "cad")
    ).upper()

    processing_fee = summary.get("processing_fee_minor")
    service_fee = summary.get("service_fee_minor")
    total_minor = summary.get("grand_total_minor")

    if processing_fee in (None, "", "0"):
        processing_fee = metadata.get("cart_processing_fee_minor")
    if service_fee in (None, "", "0"):
        service_fee = metadata.get("cart_service_fee_minor")
    if total_minor in (None, "", "0"):
        total_minor = metadata.get("cart_total_minor")

    items: List[PricingLine] = []
    for entry in summary.get("items", []):
        base_price = _quantize(_decimal_from_minor(entry.get("base_minor")))
        discount_amount = _quantize(_decimal_from_minor(entry.get("discount_minor")))
        final_price = _quantize(base_price - discount_amount)
        if final_price < ZERO:
            final_price = ZERO
        tax_amount = _quantize(_decimal_from_minor(entry.get("tax_minor")))
        total_with_tax = _quantize(_decimal_from_minor(entry.get("total_minor")))
        if total_with_tax <= ZERO:
            total_with_tax = _quantize(final_price + tax_amount)
        items.append(
            PricingLine(
                name=str(entry.get("name", "")),
                base_price=base_price,
                discount_amount=discount_amount,
                final_price=final_price,
                tax_amount=tax_amount,
                total_with_tax=total_with_tax,
                metadata={k: v for k, v in entry.items() if k not in {"name", "base_minor", "discount_minor", "total_minor", "tax_minor"}},
            )
        )

    details = {}
    if isinstance(summary.get("details"), dict):
        details = dict(summary["details"])
    elif isinstance(metadata.get("cart_pricing_details"), dict):
        details = dict(metadata["cart_pricing_details"])

    return PricingSummary(
        currency=currency,
        base_subtotal=_quantize(_decimal_from_minor(summary.get("base_subtotal_minor"))),
        subtotal=_quantize(_decimal_from_minor(summary.get("subtotal_minor"))),
        discount_total=_quantize(_decimal_from_minor(summary.get("discount_minor"))),
        tax_total=_quantize(_decimal_from_minor(summary.get("tax_minor"))),
        service_fee=_quantize(_decimal_from_minor(service_fee)),
        processing_fee=_quantize(_decimal_from_minor(processing_fee)),
        total=_quantize(_decimal_from_minor(total_minor)),
        items=items,
        details=details,
    ).normalized()


def _pricing_from_appointment(payment: Payment, appointment) -> Optional[PricingSummary]:
    if appointment is None:
        return None
    try:
        snapshot = compute_appointment_pricing(appointment)
    except PricingComputationError:
        return None

    totals = snapshot.get("totals", {})
    currency = (
        snapshot.get("currency")
        or getattr(settings, "STRIPE_CURRENCY", "cad")
        or payment.currency
    ).upper()

    base_services = _quantize(_to_decimal(totals.get("base_services_subtotal")))
    product_subtotal = _quantize(_to_decimal(totals.get("product_subtotal")))
    items: List[PricingLine] = []
    for entry in snapshot.get("items", []):
        base_price = _quantize(_to_decimal(entry.get("base_price")))
        final_price = _quantize(_to_decimal(entry.get("final_price")))
        discount_amount = _quantize(_to_decimal(entry.get("discount_amount")))
        tax_amount = _quantize(_to_decimal(entry.get("tax_amount")))
        total_with_tax = _quantize(final_price + tax_amount)
        items.append(
            PricingLine(
                name=str(entry.get("name", "")),
                base_price=base_price,
                discount_amount=discount_amount,
                final_price=final_price,
                tax_amount=tax_amount,
                total_with_tax=total_with_tax,
                metadata={k: v for k, v in entry.items() if k not in {"name", "base_price", "final_price", "discount_amount", "tax_amount"}},
            )
        )

    # Compute a service fee if the appointment tracks it separately.
    service_fee = _to_decimal(getattr(appointment, "service_fee", ZERO))
    processing_fee = _to_decimal(totals.get("processing_fee", ZERO))

    return PricingSummary(
        currency=currency,
        base_subtotal=_quantize(base_services + product_subtotal),
        subtotal=_quantize(_to_decimal(totals.get("final_subtotal"))),
        discount_total=_quantize(_to_decimal(totals.get("discount_total"))),
        tax_total=_quantize(_to_decimal(totals.get("tax_total"))),
        service_fee=_quantize(service_fee),
        processing_fee=_quantize(processing_fee),
        total=_quantize(_to_decimal(totals.get("grand_total"))),
        items=items,
        details=dict(snapshot.get("summary", {})),
    ).normalized()


def _master_display(item: AppointmentItem) -> str:
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


def _appointment_items(appointment) -> List[AppointmentItem]:
    if appointment is None:
        return []
    qs = appointment.items.select_related("service", "master__user__user")
    return list(qs.order_by("start_time"))


def _merge_items(pricing: PricingSummary, appointment) -> List[Dict[str, Any]]:
    appointment_items = _appointment_items(appointment)
    merged: List[Dict[str, Any]] = []

    for index, line in enumerate(pricing.items):
        appointment_item = appointment_items[index] if index < len(appointment_items) else None
        payload = line.as_payload(appointment_item)
        if not payload["name"] and appointment_item:
            service = getattr(appointment_item, "service", None)
            payload["name"] = getattr(service, "name", "") or payload["name"]
        merged.append(payload)

    # If the appointment has extra items not present in metadata, append them.
    if len(appointment_items) > len(pricing.items):
        for appointment_item in appointment_items[len(pricing.items):]:
            base_price = _quantize(_to_decimal(getattr(appointment_item, "unit_price", None)))
            final_price = _quantize(_to_decimal(getattr(appointment_item, "final_price", None) or base_price))
            discount_amount = _quantize(base_price - final_price) if base_price > final_price else ZERO
            tax_amount = _quantize(_to_decimal(getattr(appointment_item, "tax_amount", None)))
            line = PricingLine(
                name=getattr(getattr(appointment_item, "service", None), "name", ""),
                base_price=base_price,
                discount_amount=discount_amount,
                final_price=final_price,
                tax_amount=tax_amount,
                total_with_tax=_quantize(final_price + tax_amount),
            )
            merged.append(line.as_payload(appointment_item))

    return merged


def _client_contact(payment: Payment, metadata: Dict[str, Any]) -> Dict[str, str]:
    appointment = getattr(payment, "appointment", None)
    client = getattr(appointment, "client", None)
    user = getattr(client, "user", None)
    contact = {
        "name": getattr(client, "get_full_name", lambda: "")() if client else "",
        "email": getattr(user, "email", "") if user else "",
        "phone": getattr(client, "phone", "") if client else "",
    }
    if not any(contact.values()):
        contact = {
            "name": metadata.get("client_name", ""),
            "email": metadata.get("client_email", ""),
            "phone": metadata.get("client_phone", ""),
        }
    return contact


def _business_profile() -> Dict[str, str]:
    return {
        "name": getattr(settings, "BUSINESS_NAME", "Malva Booking"),
        "address": getattr(settings, "BUSINESS_ADDRESS", ""),
        "phone": getattr(settings, "BUSINESS_PHONE", ""),
        "email": getattr(settings, "BUSINESS_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        "support_email": getattr(settings, "BUSINESS_SUPPORT_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        "website": getattr(settings, "BUSINESS_WEBSITE", ""),
    }


def build_payment_context(payment: Payment) -> Dict[str, Any]:
    metadata = _parse_metadata(payment.metadata)
    appointment = getattr(payment, "appointment", None)

    pricing = _pricing_from_metadata(payment, metadata)
    if pricing is None:
        pricing = _pricing_from_appointment(payment, appointment)
    if pricing is None:
        pricing = PricingSummary(
            currency=(payment.currency or getattr(settings, "STRIPE_CURRENCY", "cad") or "cad").upper(),
        )

    items_payload = _merge_items(pricing, appointment)
    totals = pricing.normalized().to_totals()
    if appointment:
        grand_total = _quantize(get_appointment_grand_total(appointment))
        received_to_date = _quantize(get_total_received_for_appointment(appointment))
    else:
        grand_total = totals.total
        received_to_date = ZERO
    balance_due = grand_total - received_to_date
    overpaid_amount = ZERO
    if balance_due < ZERO:
        overpaid_amount = _quantize(-balance_due)
        balance_due = ZERO
    totals.grand_total = grand_total
    totals.received_to_date = received_to_date
    totals.balance_due = _quantize(balance_due)
    totals.overpaid_amount = overpaid_amount

    return {
        "payment": payment,
        "appointment": appointment,
        "client": getattr(appointment, "client", None),
        "client_contact": _client_contact(payment, metadata),
        "items": items_payload,
        "totals": totals,
        "issued_at": timezone.now(),
        "business": _business_profile(),
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

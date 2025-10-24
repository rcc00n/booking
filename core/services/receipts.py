"""
Receipt generation services for payments.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional
import json

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timezone import localtime

from core.models import AppointmentItem, Payment
from core.services.pricing import compute_appointment_pricing, PricingComputationError
from core.utils.pdf import render_html_to_pdf


@dataclass
class ReceiptTotals:
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    processing_fee: Decimal
    service_fee: Decimal
    total: Decimal
    currency: str
    base_subtotal: Decimal = Decimal("0.00")
    summary: Dict[str, Any] = field(default_factory=dict)


def _quantize(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return value.quantize(Decimal("0.01"))


def _from_minor_units(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    try:
        if isinstance(value, int):
            return Decimal(value) / Decimal("100")
        if isinstance(value, str) and value.strip().isdigit():
            return Decimal(int(value.strip())) / Decimal("100")
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _to_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _payment_totals(
    payment: Payment,
    items: Iterable[AppointmentItem],
) -> tuple[ReceiptTotals, Optional[Dict[str, Any]]]:
    appointment = getattr(payment, "appointment", None)
    raw_metadata: Any = payment.metadata or {}
    if isinstance(raw_metadata, str):
        try:
            metadata: Dict[str, Any] = json.loads(raw_metadata)
        except json.JSONDecodeError:
            metadata = {}
    elif isinstance(raw_metadata, dict):
        metadata = dict(raw_metadata)
    else:
        metadata = {}
    service_fee_source = metadata.get("service_fee_minor")
    if service_fee_source in (None, ""):
        service_fee_source = metadata.get("cart_service_fee_minor")
    service_fee = _quantize(_from_minor_units(service_fee_source))
    if service_fee == Decimal("0.00"):
        service_fee = _quantize(_to_decimal(metadata.get("service_fee")))
    pricing_snapshot: Optional[Dict[str, Any]] = None
    if appointment is not None:
        try:
            pricing_snapshot = compute_appointment_pricing(appointment)
        except PricingComputationError:
            pricing_snapshot = None

    if pricing_snapshot:
        totals_data = pricing_snapshot.get("totals", {})
        subtotal = _quantize(totals_data.get("final_subtotal", Decimal("0.00")))
        tax_total = _quantize(totals_data.get("tax_total", Decimal("0.00")))
        discount_total = _quantize(totals_data.get("discount_total", Decimal("0.00")))
        processing_fee = _quantize(totals_data.get("processing_fee", Decimal("0.00")))
        service_fee_candidate = totals_data.get("service_fee", Decimal("0.00"))
        if isinstance(service_fee_candidate, dict):
            service_fee_candidate = service_fee_candidate.get("amount", Decimal("0.00"))
        service_fee_from_totals = _quantize(_to_decimal(service_fee_candidate))
        if service_fee_from_totals > Decimal("0.00"):
            service_fee = service_fee_from_totals
        total = _quantize(totals_data.get("grand_total", payment.amount_received or payment.amount or Decimal("0.00")))
        base_subtotal = _quantize(
            totals_data.get("base_services_subtotal", Decimal("0.00"))
            + totals_data.get("product_subtotal", Decimal("0.00"))
        )
        if discount_total < Decimal("0.00"):
            discount_total = Decimal("0.00")

        receipt_totals = ReceiptTotals(
            subtotal=subtotal,
            discount_total=discount_total,
            tax_total=tax_total,
            processing_fee=processing_fee,
            service_fee=service_fee,
            total=total,
            currency=(payment.currency or pricing_snapshot.get("currency") or settings.STRIPE_CURRENCY or "cad").upper(),
            base_subtotal=base_subtotal,
            summary=pricing_snapshot.get("summary", {}),
        )
        return receipt_totals, pricing_snapshot

    subtotal = Decimal("0.00")
    base_subtotal = Decimal("0.00")
    item_tax_total = Decimal("0.00")
    processing_fee = Decimal("0.00")
    for item in items:
        price = getattr(item, "final_price", None) or getattr(item, "unit_price", None) or Decimal("0.00")
        price = _quantize(price)
        subtotal += price
        base_subtotal += price
        item_tax_total += _quantize(getattr(item, "tax_amount", Decimal("0.00")) or Decimal("0.00"))

    sales_list = []
    if appointment is not None:
        product_sales_rel = getattr(appointment, "product_sales", None)
        if product_sales_rel is not None:
            sales_list = list(product_sales_rel.all())
            for sale in sales_list:
                sale_total = _quantize(getattr(sale, "total_amount", Decimal("0.00")) or Decimal("0.00"))
                subtotal += sale_total
                base_subtotal += sale_total
                item_tax_total += _quantize(getattr(sale, "tax_amount", Decimal("0.00")) or Decimal("0.00"))

    total = _quantize(payment.amount_received or payment.amount or Decimal("0.00"))

    if base_subtotal < subtotal:
        base_subtotal = subtotal

    discount_total = base_subtotal - subtotal
    if discount_total < Decimal("0.00"):
        discount_total = Decimal("0.00")

    computed_tax = item_tax_total
    summary_meta = None
    summary_source = metadata.get("cart_pricing")
    if isinstance(summary_source, str):
        try:
            summary_meta = json.loads(summary_source)
        except json.JSONDecodeError:
            summary_meta = None
    elif isinstance(summary_source, dict):
        summary_meta = summary_source

    if isinstance(summary_meta, dict):
        subtotal = _quantize(_from_minor_units(summary_meta.get("subtotal_minor")))
        discount_total = _quantize(_from_minor_units(summary_meta.get("discount_minor")))
        base_subtotal = subtotal + discount_total
        computed_tax = _quantize(_from_minor_units(summary_meta.get("tax_minor")))
        processing_fee = _quantize(_from_minor_units(summary_meta.get("processing_fee_minor")))
        service_fee_candidate = summary_meta.get("service_fee_minor")
        if service_fee_candidate is None:
            service_fee_candidate = metadata.get("service_fee_minor") or metadata.get("cart_service_fee_minor")
        service_fee_from_summary = _quantize(_from_minor_units(service_fee_candidate))
        if service_fee_from_summary > Decimal("0.00"):
            service_fee = service_fee_from_summary
        total_minor = summary_meta.get("grand_total_minor")
        if isinstance(total_minor, int):
            total = _quantize(_from_minor_units(total_minor))
    if service_fee <= Decimal("0.00"):
        derived_service_fee = total - (subtotal + computed_tax + processing_fee)
        derived_service_fee = _quantize(derived_service_fee)
        if derived_service_fee > Decimal("0.00"):
            service_fee = derived_service_fee
        else:
            service_fee = Decimal("0.00")

    receipt_totals = ReceiptTotals(
        subtotal=_quantize(subtotal),
        discount_total=_quantize(discount_total),
        tax_total=_quantize(computed_tax),
        processing_fee=_quantize(processing_fee),
        service_fee=_quantize(service_fee),
        total=total,
        currency=(payment.currency or settings.STRIPE_CURRENCY or "cad").upper(),
        base_subtotal=_quantize(base_subtotal),
        summary=summary_meta or {},
    )
    return receipt_totals, None


def build_payment_context(payment: Payment) -> Dict[str, Any]:
    appointment = payment.appointment
    client = getattr(appointment, "client", None)
    user = getattr(client, "user", None)
    metadata_raw: Dict[str, Any] = payment.metadata or {}

    items_qs = []
    if appointment:
        items_qs = list(
            appointment.items.select_related(
                "service",
                "master__user__user",
            )
            .all()
        )

    totals, pricing_snapshot = _payment_totals(payment, items_qs)
    if not pricing_snapshot and isinstance(metadata_raw, dict):
        pricing_snapshot = metadata_raw.get("cart_pricing")
        if isinstance(pricing_snapshot, str):
            try:
                pricing_snapshot = json.loads(pricing_snapshot)
            except json.JSONDecodeError:
                pricing_snapshot = None
    summary_meta = totals.summary if isinstance(totals.summary, dict) and totals.summary else None
    if summary_meta is None and isinstance(metadata_raw, dict):
        summary_candidate = metadata_raw.get("cart_pricing")
        if isinstance(summary_candidate, str):
            try:
                summary_candidate = json.loads(summary_candidate)
            except json.JSONDecodeError:
                summary_candidate = None
        if isinstance(summary_candidate, dict) and summary_candidate:
            summary_meta = summary_candidate

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

    pricing_item_lookup: Dict[str, Dict[str, Any]] = {}
    if pricing_snapshot:
        pricing_item_lookup = {
            entry.get("id"): entry for entry in pricing_snapshot.get("items", []) if entry.get("id")
        }

    items_payload: List[Dict[str, Any]] = []
    for item in items_qs:
        start_dt = localtime(item.start_time) if getattr(item, "start_time", None) else None
        pricing_entry = pricing_item_lookup.get(str(getattr(item, "pk", "")), {}) if pricing_item_lookup else {}
        base_price = _to_decimal(pricing_entry.get("base_price"))
        if base_price <= Decimal("0.00"):
            try:
                base_price = item._effective_unit_price()
            except Exception:
                base_price = getattr(item, "unit_price", None) or getattr(getattr(item, "service", None), "base_price", Decimal("0.00"))
        base_price = _quantize(base_price)
        final_price = _quantize(getattr(item, "final_price", None) or getattr(item, "unit_price", None) or base_price)
        discount_amount = pricing_entry.get("discount_amount")
        if discount_amount is not None:
            discount_amount = _quantize(abs(_to_decimal(discount_amount)))
        else:
            calc_discount = base_price - final_price
            discount_amount = _quantize(calc_discount if calc_discount > 0 else Decimal("0.00"))
        tax_amount = _quantize(getattr(item, "tax_amount", Decimal("0.00")) or Decimal("0.00"))
        items_payload.append(
            {
                "name": getattr(getattr(item, "service", None), "name", ""),
                "master": _master_name(item),
                "duration_min": item.duration_min if hasattr(item, "duration_min") else None,
                "start_at": start_dt,
                "base_price": base_price,
                "final_price": final_price,
                "price": base_price,
                "discount_amount": discount_amount,
                "tax_amount": tax_amount,
            }
        )

    if summary_meta and items_payload:
        summary_items = summary_meta.get("items", [])
        for idx, entry in enumerate(summary_items):
            base_minor = entry.get("base_minor")
            total_minor = entry.get("total_minor")
            discount_minor = entry.get("discount_minor")
            if idx < len(items_payload):
                target = items_payload[idx]
            else:
                target = {
                    "name": entry.get("name", ""),
                    "master": "",
                    "duration_min": None,
                    "start_at": None,
                    "base_price": Decimal("0.00"),
                    "final_price": Decimal("0.00"),
                    "price": Decimal("0.00"),
                    "discount_amount": Decimal("0.00"),
                    "tax_amount": Decimal("0.00"),
                }
                items_payload.append(target)
            if base_minor is not None:
                target["base_price"] = _quantize(_from_minor_units(base_minor))
            if total_minor is not None:
                target["final_price"] = _quantize(_from_minor_units(total_minor))
            if discount_minor is not None:
                target["discount_amount"] = _quantize(_from_minor_units(discount_minor))
            target["price"] = target.get("base_price", Decimal("0.00"))

    if not items_payload and summary_meta:
        for entry in summary_meta.get("items", []):
            if not isinstance(entry, dict):
                continue
            base_minor = entry.get("base_minor")
            total_minor = entry.get("total_minor")
            discount_minor = entry.get("discount_minor")
            items_payload.append(
                {
                    "name": entry.get("name", ""),
                    "master": "",
                    "duration_min": None,
                    "start_at": None,
                    "base_price": _quantize(_from_minor_units(base_minor)),
                    "final_price": _quantize(_from_minor_units(total_minor)),
                    "price": _quantize(_from_minor_units(base_minor)),
                    "discount_amount": _quantize(_from_minor_units(discount_minor)),
                    "tax_amount": Decimal("0.00"),
                }
            )

    if not items_payload and isinstance(pricing_snapshot, dict):
        for entry in pricing_snapshot.get("items", []):
            if not isinstance(entry, dict):
                continue
            start_at = entry.get("start_time") or entry.get("start_at")
            try:
                start_dt = localtime(start_at) if hasattr(start_at, "tzinfo") else None
            except Exception:
                start_dt = None
            total_minor = entry.get("total_minor")
            if isinstance(total_minor, int):
                price_value = Decimal(total_minor) / Decimal("100")
            else:
                price_value = _to_decimal(
                    entry.get("unit_price_decimal")
                    or entry.get("subtotal_decimal")
                    or entry.get("unit_price")
                    or entry.get("subtotal")
                )
            discount_value = _to_decimal(entry.get("discount_total_decimal") or entry.get("discount_amount"))
            if discount_value < 0:
                discount_value = -discount_value
            base_value = price_value + discount_value
            items_payload.append(
                {
                    "name": entry.get("name") or entry.get("service", {}).get("name", ""),
                    "master": (entry.get("master") or {}).get("name") or entry.get("master_name", ""),
                    "duration_min": entry.get("duration_min") or entry.get("service", {}).get("duration_min"),
                    "start_at": start_dt,
                    "base_price": _quantize(base_value),
                    "final_price": _quantize(price_value),
                    "price": _quantize(base_value),
                    "discount_amount": _quantize(discount_value),
                    "tax_amount": _quantize(_to_decimal(entry.get("tax") or entry.get("tax_amount"))),
                }
            )

    client_contact = {
        "name": getattr(client, "get_full_name", lambda: "")(),
        "email": getattr(user, "email", ""),
        "phone": getattr(client, "phone", ""),
    }
    if not any(client_contact.values()) and isinstance(metadata_raw, dict):
        client_contact = {
            "name": metadata_raw.get("client_name", ""),
            "email": metadata_raw.get("client_email", ""),
            "phone": metadata_raw.get("client_phone", ""),
        }

    return {
        "payment": payment,
        "appointment": appointment,
        "client": client,
        "client_contact": client_contact,
        "items": items_payload,
        "totals": totals,
        "pricing_snapshot": pricing_snapshot,
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

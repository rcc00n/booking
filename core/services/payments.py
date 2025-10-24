"""Payment/Stripe service helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

import stripe
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from core.models import Appointment, Payment, PaymentMethod, PaymentStatus


@dataclass
class PaymentIntentBundle:
    payment: Payment
    intent: Optional[stripe.PaymentIntent]


TERMINAL_STATUSES = {"succeeded", "canceled"}


def _require_stripe() -> None:
    """Ensure Stripe credentials are configured and prime the module."""
    if not settings.STRIPE_SECRET_KEY:
        raise ImproperlyConfigured("STRIPE_SECRET_KEY is not configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY
    if getattr(settings, "STRIPE_API_VERSION", None):
        stripe.api_version = settings.STRIPE_API_VERSION


def _to_minor_units(amount: Decimal) -> int:
    cents = (amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _from_minor_units(amount: Optional[int]) -> Decimal:
    if amount is None:
        return Decimal("0.00")
    return (Decimal(amount) / Decimal("100")).quantize(Decimal("0.01"))


def ensure_payment_method(name: str = "Stripe") -> PaymentMethod:
    method, _ = PaymentMethod.objects.get_or_create(name=name)
    return method


def ensure_payment_status(name: str) -> PaymentStatus:
    status, _ = PaymentStatus.objects.get_or_create(name=name)
    return status


def get_total_received_for_appointment(appointment: Appointment | None) -> Decimal:
    """
    Sum the received amounts for all succeeded payments tied to the appointment.
    Falls back to gross amount when amount_received is not populated.
    """
    if appointment is None:
        return Decimal("0.00")

    total = Decimal("0.00")
    succeeded = (
        Payment.objects.filter(appointment=appointment, status__iexact="succeeded")
        .values_list("amount_received", "amount")
    )
    for amount_received, amount in succeeded:
        value = amount_received or Decimal("0.00")
        if value <= Decimal("0.00"):
            value = amount or Decimal("0.00")
        total += value
    return total.quantize(Decimal("0.01"))


def _base_metadata(appointment: Appointment) -> dict[str, str]:
    user = appointment.client.user if appointment.client else None
    meta = {
        "appointment_id": str(appointment.id),
        "client_id": str(appointment.client_id or ""),
    }
    if user:
        meta["client_email"] = user.email or ""
        meta["client_name"] = user.get_full_name() or user.username
    return meta


def _terminal(payment: Payment) -> bool:
    return payment.status in TERMINAL_STATUSES


def _set_appointment_status_from_intent(appointment: Appointment, status: str) -> None:
    if status == "succeeded":
        target = ensure_payment_status("Paid")
    elif status in {"canceled", "payment_failed"}:
        target = ensure_payment_status("Failed")
    else:
        target = ensure_payment_status("Pending")
    if appointment.payment_status_id != target.id:
        appointment.payment_status = target
        appointment.save(update_fields=["payment_status"])


def create_or_update_payment_intent(
    appointment: Appointment,
    *,
    amount: Optional[Decimal] = None,
    currency: Optional[str] = None,
    payment_method_types: Optional[Iterable[str]] = None,
    allow_reuse_existing: bool = True,
) -> PaymentIntentBundle:
    """Create or update a Stripe PaymentIntent for the appointment."""

    if amount is not None:
        total = Decimal(amount)
    else:
        if hasattr(appointment, "total_with_tax"):
            total = Decimal(appointment.total_with_tax or Decimal("0.00"))
        else:
            total = Decimal(appointment.final_price or Decimal("0.00"))
    total = total.quantize(Decimal("0.01"))
    currency = (currency or settings.STRIPE_CURRENCY or "cad").lower()
    pm_types = list(payment_method_types or settings.STRIPE_PAYMENT_METHOD_TYPES)

    payments_enabled = getattr(settings, "STRIPE_PAYMENTS_ENABLED", True)
    if total <= Decimal("0.00") or not payments_enabled:
        method = ensure_payment_method("Manual")
        amount_received = total if total > Decimal("0.00") else Decimal("0.00")
        note = (
            "Payments handled offline" if (total > Decimal("0.00") and not payments_enabled)
            else "No payment required"
        )
        metadata = {"note": note}
        if appointment:
            fee_value = getattr(appointment, "card_processing_fee", None) or Decimal("0.00")
            try:
                fee_minor = _to_minor_units(Decimal(fee_value))
            except Exception:
                fee_minor = 0
            if fee_minor:
                metadata["card_processing_fee_minor"] = str(fee_minor)
        with transaction.atomic():
            payment = Payment.objects.create(
                appointment=appointment,
                amount=total,
                currency=currency,
                method=method,
                status="succeeded",
                amount_received=amount_received,
                metadata=metadata,
            )
            paid_status = ensure_payment_status("Paid")
            appointment.payment_status = paid_status
            appointment.save(update_fields=["payment_status"])
        return PaymentIntentBundle(payment=payment, intent=None)

    _require_stripe()

    method = ensure_payment_method("Stripe")
    metadata = _base_metadata(appointment)

    existing = None
    if allow_reuse_existing:
        existing = (
            appointment.payments.filter(method=method)
            .exclude(status__in=TERMINAL_STATUSES)
            .order_by("-created_at")
            .first()
        )

    amount_minor = _to_minor_units(total)

    if existing and existing.stripe_payment_intent_id:
        intent = stripe.PaymentIntent.modify(
            existing.stripe_payment_intent_id,
            amount=amount_minor,
            currency=currency,
            metadata=metadata,
            payment_method_types=pm_types,
        )
        _apply_intent(existing, intent, amount_decimal=total)
        _set_appointment_status_from_intent(appointment, intent.status)
        return PaymentIntentBundle(payment=existing, intent=intent)

    intent = stripe.PaymentIntent.create(
        amount=amount_minor,
        currency=currency,
        payment_method_types=pm_types,
        metadata=metadata,
        capture_method="automatic",
    )

    with transaction.atomic():
        payment = Payment.objects.create(
            appointment=appointment,
            amount=total,
            currency=currency,
            method=method,
            status=intent.status,
            stripe_payment_intent_id=intent.id,
            livemode=bool(intent.livemode),
            metadata=metadata,
            raw_response=intent.to_dict_recursive(),
        )
    _apply_intent(payment, intent, amount_decimal=total)
    _set_appointment_status_from_intent(appointment, intent.status)
    return PaymentIntentBundle(payment=payment, intent=intent)


def create_or_update_terminal_intent(
    appointment: Appointment,
    *,
    amount: Decimal | None = None,
    currency: str | None = None,
) -> PaymentIntentBundle:
    """
    Create or update a Stripe Terminal PaymentIntent ensuring card-present method types.
    Delegates to create_or_update_payment_intent so downstream persistence stays consistent.
    """
    pm_types = ["card_present", "interac_present"]
    return create_or_update_payment_intent(
        appointment,
        amount=amount,
        currency=currency,
        payment_method_types=pm_types,
        allow_reuse_existing=True,
    )


def _apply_intent(
    payment: Payment,
    intent: stripe.PaymentIntent,
    *,
    amount_decimal: Optional[Decimal] = None,
) -> Payment:
    capture_ts = None
    charge = None
    if getattr(intent, "charges", None):
        charge = intent.charges.data[0] if intent.charges.data else None
    if charge and charge.get("created"):
        capture_ts = datetime.fromtimestamp(charge["created"], tz=dt_timezone.utc)

    payment.amount = amount_decimal if amount_decimal is not None else _from_minor_units(intent.amount)
    payment.status = intent.status
    payment.livemode = bool(intent.livemode)
    payment.stripe_payment_method_id = getattr(intent, "payment_method", None)
    payment.amount_received = _from_minor_units(getattr(intent, "amount_received", None))
    if charge:
        payment.amount_refunded = _from_minor_units(charge.get("amount_refunded"))
    else:
        payment.amount_refunded = Decimal("0.00")
    payment.raw_response = intent.to_dict_recursive()
    payment.metadata = intent.metadata or {}
    payment.captured_at = capture_ts

    if charge:
        payment.stripe_charge_id = charge.get("id")
        payment.receipt_url = charge.get("receipt_url", "") or ""

    payment.save()
    return payment


def sync_payment_from_intent(intent_id: str) -> Payment:
    """Fetch an intent from Stripe and persist its state."""
    _require_stripe()
    intent = stripe.PaymentIntent.retrieve(intent_id, expand=["charges"])
    payment = Payment.objects.filter(stripe_payment_intent_id=intent.id).first()
    if not payment:
        raise Payment.DoesNotExist(f"Payment matching intent {intent.id} not found")
    _apply_intent(payment, intent)
    _set_appointment_status_from_intent(payment.appointment, intent.status)
    return payment


def handle_webhook_event(event: stripe.Event) -> Payment:
    """Handle relevant webhook events and update payments accordingly."""
    if event.type not in {
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
        "payment_intent.canceled",
        "payment_intent.processing",
    }:
        raise ValueError(f"Unhandled Stripe event type {event.type}")

    intent = event.data.object
    payment = Payment.objects.filter(stripe_payment_intent_id=intent.id).first()
    if not payment:
        raise Payment.DoesNotExist(f"Payment for intent {intent.id} not found")

    _apply_intent(payment, intent)

    _set_appointment_status_from_intent(payment.appointment, intent.status)

    return payment

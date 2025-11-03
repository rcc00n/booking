"""Payment/Stripe service helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

import stripe
import logging
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from core.models import Appointment, Payment, PaymentMethod, PaymentStatus

logger = logging.getLogger(__name__)


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


def get_outstanding_amount(appointment: Appointment | None) -> Decimal:
    """
    Return the remaining balance for an appointment (grand total minus payments received).
    """
    if appointment is None:
        return Decimal("0.00")

    if hasattr(appointment, "total_with_tax"):
        total = Decimal(appointment.total_with_tax or Decimal("0.00"))
    else:
        total = Decimal(getattr(appointment, "final_price", Decimal("0.00")) or Decimal("0.00"))
    received = get_total_received_for_appointment(appointment)
    remaining = total - received
    if remaining <= Decimal("0.00"):
        return Decimal("0.00")
    return remaining.quantize(Decimal("0.01"))


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


def _stripe_obj_get(obj, attr, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    try:
        return getattr(obj, attr)
    except AttributeError:
        getter = getattr(obj, "get", None)
        if callable(getter):
            try:
                return getter(attr, default)
            except Exception:
                return default
        return default


def _normalize_intent_id(candidate) -> Optional[str]:
    if candidate is None:
        return None
    if isinstance(candidate, str):
        return candidate
    intent_id = getattr(candidate, "id", None)
    return intent_id or None


def _extract_payment_intent_id(event_object) -> Optional[str]:
    intent_candidate = _stripe_obj_get(event_object, "payment_intent")
    intent_id = _normalize_intent_id(intent_candidate)
    if intent_id:
        return intent_id

    charge_candidate = _stripe_obj_get(event_object, "charge")
    charge_intent = _stripe_obj_get(charge_candidate, "payment_intent")
    charge_intent_id = _normalize_intent_id(charge_intent)
    if charge_intent_id:
        return charge_intent_id

    charge_id = None
    if isinstance(charge_candidate, str):
        charge_id = charge_candidate
    else:
        charge_id = _stripe_obj_get(charge_candidate, "id")

    if charge_id:
        try:
            _require_stripe()
            charge = stripe.Charge.retrieve(charge_id)
        except stripe.error.StripeError:
            logger.exception("Unable to retrieve Stripe charge %s while handling refund event", charge_id)
            return None
        intent_candidate = _stripe_obj_get(charge, "payment_intent")
        intent_id = _normalize_intent_id(intent_candidate)
        if intent_id:
            return intent_id

    return None


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
    charges_collection = getattr(intent, "charges", None)
    charges_data = list(getattr(charges_collection, "data", []) or [])
    primary_charge = _stripe_obj_get(intent, "latest_charge")

    if isinstance(primary_charge, str):
        primary_charge = next(
            (item for item in charges_data if _stripe_obj_get(item, "id") == primary_charge),
            None,
        )
    if primary_charge is None and charges_data:
        primary_charge = charges_data[0]

    capture_ts = None
    created_ts = _stripe_obj_get(primary_charge, "created")
    if created_ts:
        try:
            capture_ts = datetime.fromtimestamp(int(created_ts), tz=dt_timezone.utc)
        except (TypeError, ValueError):
            capture_ts = None

    payment.amount = amount_decimal if amount_decimal is not None else _from_minor_units(getattr(intent, "amount", None))
    payment.status = getattr(intent, "status", payment.status)
    payment.livemode = bool(getattr(intent, "livemode", payment.livemode))
    payment.stripe_payment_method_id = getattr(intent, "payment_method", None)
    payment.amount_received = _from_minor_units(_stripe_obj_get(intent, "amount_received"))

    refunded_minor_total = 0
    for charge_obj in charges_data:
        refunded_minor = _stripe_obj_get(charge_obj, "amount_refunded")
        if refunded_minor:
            try:
                refunded_minor_total += int(refunded_minor)
            except (TypeError, ValueError):
                logger.warning(
                    "Unexpected Stripe charge refund amount %s for payment %s",
                    refunded_minor,
                    payment.pk,
                )

    if refunded_minor_total == 0:
        single_refund = _stripe_obj_get(primary_charge, "amount_refunded")
        if single_refund:
            try:
                refunded_minor_total = int(single_refund)
            except (TypeError, ValueError):
                refunded_minor_total = 0

    payment.amount_refunded = _from_minor_units(refunded_minor_total)

    payment.raw_response = intent.to_dict_recursive()
    payment.metadata = intent.metadata or {}
    payment.captured_at = capture_ts

    if primary_charge:
        charge_id = _stripe_obj_get(primary_charge, "id")
        if charge_id:
            payment.stripe_charge_id = charge_id
        receipt_url = _stripe_obj_get(primary_charge, "receipt_url")
        if receipt_url is not None:
            payment.receipt_url = receipt_url or ""

    logger.info(
        "Synced payment %s from intent %s (refunded_minor=%s)",
        payment.pk,
        getattr(intent, "id", None),
        refunded_minor_total,
    )

    payment.save()
    return payment


def sync_payment_from_intent(intent_id: str) -> Payment:
    """Fetch an intent from Stripe and persist its state."""
    _require_stripe()
    intent = stripe.PaymentIntent.retrieve(intent_id, expand=["charges", "latest_charge"])
    payment = Payment.objects.filter(stripe_payment_intent_id=intent.id).first()
    if not payment:
        raise Payment.DoesNotExist(f"Payment matching intent {intent.id} not found")
    _apply_intent(payment, intent)
    _set_appointment_status_from_intent(payment.appointment, intent.status)
    return payment


def handle_webhook_event(event: stripe.Event) -> Payment:
    """Handle relevant webhook events and update payments accordingly."""
    event_type = event.type

    if event_type in {
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
        "payment_intent.canceled",
        "payment_intent.processing",
    }:
        intent = event.data.object
        payment = Payment.objects.filter(stripe_payment_intent_id=intent.id).first()
        if not payment:
            raise Payment.DoesNotExist(f"Payment for intent {intent.id} not found")
        _apply_intent(payment, intent)
        _set_appointment_status_from_intent(payment.appointment, intent.status)
        return payment

    if event_type in {"charge.refunded", "refund.updated"}:
        event_object = event.data.object
        intent_id = _extract_payment_intent_id(event_object)
        if not intent_id:
            raise ValueError(f"Refund event {event_type} missing payment_intent reference")
        payment = sync_payment_from_intent(intent_id)
        logger.info(
            "Processed Stripe refund webhook %s for payment intent %s",
            event_type,
            intent_id,
        )
        return payment

    raise ValueError(f"Unhandled Stripe event type {event_type}")

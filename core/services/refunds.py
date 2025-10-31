"""Admin-facing refund orchestration utilities."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Sequence, TYPE_CHECKING

import logging

import stripe
from django.db import transaction
from django.utils import timezone

from core.models import Appointment, Payment, PaymentRefund
from core.services import payments as payment_services

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)

TWOPLACES = Decimal("0.01")
HUNDRED = Decimal("100")


class RefundError(Exception):
    """Raised when refund allocation or execution fails."""


@dataclass(frozen=True)
class RefundAllocation:
    """Describes a payment and amount (in minor units) allocated for a refund."""

    payment: Payment
    amount_minor: int


class RefundService:
    """Core refund orchestration helpers for admin workflows."""

    @staticmethod
    def _to_minor_units(amount: Decimal) -> int:
        quantized = Decimal(amount or Decimal("0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return int((quantized * HUNDRED).to_integral_value(rounding=ROUND_HALF_UP))

    @staticmethod
    def _minor_to_decimal(value: int) -> Decimal:
        return (Decimal(value) / HUNDRED).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    @staticmethod
    def _infer_method(payment: Payment) -> str:
        method_name = ""
        if payment.method_id and getattr(payment, "method", None):
            method_name = (payment.method.name or "").strip().lower()

        if payment.stripe_payment_intent_id or payment.stripe_charge_id:
            return PaymentRefund.METHOD_STRIPE
        if "stripe" in method_name or "card" in method_name:
            return PaymentRefund.METHOD_STRIPE
        if "transfer" in method_name:
            return PaymentRefund.METHOD_ETRANSFER
        return PaymentRefund.METHOD_CASH

    @classmethod
    def _available_minor(cls, payment: Payment) -> int:
        received = payment.amount_received or Decimal("0.00")
        if received <= Decimal("0.00"):
            received = payment.amount or Decimal("0.00")
        refunded = payment.amount_refunded or Decimal("0.00")
        received_minor = cls._to_minor_units(received)
        refunded_minor = cls._to_minor_units(refunded)
        remaining = max(0, received_minor - refunded_minor)
        return remaining

    @staticmethod
    def _sort_key(payment: Payment) -> tuple:
        capture = payment.captured_at or payment.created_at or timezone.now()
        return (capture, payment.created_at or capture, str(payment.pk))

    @classmethod
    def allocate_refund_for_appointment(
        cls,
        appointment: Appointment,
        requested_amount_minor: int,
    ) -> List[RefundAllocation]:
        """
        Determine refund allocations across payments tied to an appointment.
        Prefers Stripe/card payments before falling back to cash/e-transfer.
        """
        if appointment is None:
            raise RefundError("Appointment is required for refunds.")
        if requested_amount_minor <= 0:
            raise RefundError("Refund amount must be greater than zero.")

        payments_qs = (
            Payment.objects.filter(appointment=appointment, status__iexact="succeeded")
            .select_related("method")
        )
        payments: List[Payment] = sorted(payments_qs, key=cls._sort_key)

        print(
            "[Refund Debug] allocate_refund_for_appointment",
            {
                "appointment_id": str(getattr(appointment, "pk", "")),
                "requested_minor": requested_amount_minor,
                "succeeded_payments": [
                    {
                        "payment_id": str(p.pk),
                        "method": getattr(getattr(p, "method", None), "name", ""),
                        "amount_received": str(p.amount_received),
                        "amount_refunded": str(p.amount_refunded),
                        "available_minor": cls._available_minor(p),
                        "is_stripe": cls._infer_method(p) == PaymentRefund.METHOD_STRIPE,
                        "captured_at": getattr(p, "captured_at", None),
                    }
                    for p in payments
                ],
            },
        )

        if not payments:
            raise RefundError("No succeeded payments available for this appointment.")

        card_payments: List[Payment] = []
        offline_payments: List[Payment] = []

        for payment in payments:
            available = cls._available_minor(payment)
            if available <= 0:
                continue
            method = cls._infer_method(payment)
            if method == PaymentRefund.METHOD_STRIPE:
                card_payments.append(payment)
            else:
                offline_payments.append(payment)

        remaining = requested_amount_minor
        allocations: List[RefundAllocation] = []

        for group in (card_payments, offline_payments):
            for payment in group:
                available = cls._available_minor(payment)
                if available <= 0:
                    continue
                portion = min(available, remaining)
                if portion > 0:
                    allocations.append(RefundAllocation(payment=payment, amount_minor=portion))
                    remaining -= portion
                if remaining == 0:
                    break
            if remaining == 0:
                break

        if remaining > 0:
            raise RefundError("Requested refund exceeds available amount for this appointment.")

        return allocations

    @classmethod
    def perform_refund(
        cls,
        allocations: Sequence[RefundAllocation],
        actor: "AbstractBaseUser | None" = None,
    ) -> List[str]:
        """
        Execute refund allocations. Returns Stripe refund IDs for Stripe-backed refunds.
        """
        if not allocations:
            raise RefundError("No payment allocations provided for refund execution.")

        payment_ids = {alloc.payment.pk for alloc in allocations}
        if not payment_ids:
            raise RefundError("Allocations reference invalid payments.")

        stripe_ids: List[str] = []

        with transaction.atomic():
            locked = {
                pk: Payment.objects.select_for_update().get(pk=pk)
                for pk in payment_ids
            }

            for allocation in allocations:
                payment = locked.get(allocation.payment.pk)
                if payment is None:
                    raise RefundError("Payment referenced by allocation no longer exists.")
                if payment.appointment_id is None:
                    raise RefundError("Payment is not linked to an appointment.")

                appointment = payment.appointment
                method = cls._infer_method(payment)
                available_minor = cls._available_minor(payment)
                if allocation.amount_minor > available_minor:
                    raise RefundError("Refund amount exceeds remaining balance for a payment.")

                amount_decimal = cls._minor_to_decimal(allocation.amount_minor)

                if method == PaymentRefund.METHOD_STRIPE:
                    stripe_refund = cls._create_stripe_refund(payment, allocation.amount_minor, actor)
                    stripe_ids.append(stripe_refund.id)
                    print(
                        "[Refund Debug] Stripe refund dispatched",
                        {
                            "payment_id": str(payment.pk),
                            "appointment_id": str(payment.appointment_id),
                            "amount_minor": allocation.amount_minor,
                            "stripe_refund_id": stripe_refund.id,
                        },
                    )
                    cls._record_refund(
                        appointment=appointment,
                        payment=payment,
                        amount_minor=allocation.amount_minor,
                        amount_decimal=amount_decimal,
                        method=method,
                        actor=actor,
                        stripe_refund_id=stripe_refund.id,
                    )
                    cls._sync_payment_after_stripe_refund(payment, stripe_refund)
                else:
                    cls._apply_offline_refund(payment, allocation.amount_minor, amount_decimal)
                    print(
                        "[Refund Debug] Offline refund recorded",
                        {
                            "payment_id": str(payment.pk),
                            "appointment_id": str(payment.appointment_id),
                            "amount_minor": allocation.amount_minor,
                        },
                    )
                    cls._record_refund(
                        appointment=appointment,
                        payment=payment,
                        amount_minor=allocation.amount_minor,
                        amount_decimal=amount_decimal,
                        method=method,
                        actor=actor,
                        stripe_refund_id="",
                    )

        return stripe_ids

    @classmethod
    def _apply_offline_refund(
        cls,
        payment: Payment,
        amount_minor: int,
        amount_decimal: Decimal,
    ) -> None:
        remaining = cls._available_minor(payment)
        if amount_minor > remaining:
            raise RefundError("Refund exceeds available offline balance.")
        payment.amount_refunded = (payment.amount_refunded or Decimal("0.00")) + amount_decimal
        payment.amount_refunded = payment.amount_refunded.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        payment.save(update_fields=["amount_refunded", "updated_at"])
        print(
            "[Refund Debug] Updated offline payment amount_refunded",
            {
                "payment_id": str(payment.pk),
                "new_amount_refunded": str(payment.amount_refunded),
            },
        )

    @classmethod
    def _create_stripe_refund(
        cls,
        payment: Payment,
        amount_minor: int,
        actor: "AbstractBaseUser | None",
    ) -> stripe.Refund:
        payment_services._require_stripe()

        identifier = payment.stripe_charge_id or payment.stripe_payment_intent_id
        if not identifier:
            raise RefundError("Stripe payment information is missing for this refund.")

        timestamp = timezone.now().strftime("%Y%m%dT%H%M%S%f")
        idempotency_key = f"refund:{payment.pk}:{timestamp}:{amount_minor}"

        metadata: dict[str, str] = {
            "appointment_id": str(payment.appointment_id or ""),
            "payment_id": str(payment.pk),
            "amount_minor": str(amount_minor),
            "source": "admin_refund",
        }
        if actor and getattr(actor, "pk", None):
            metadata["actor_id"] = str(actor.pk)

        print(
            "[Refund Debug] Requesting Stripe refund",
            {
                "payment_id": str(payment.pk),
                "amount_minor": amount_minor,
                "charge_id": payment.stripe_charge_id,
                "intent_id": payment.stripe_payment_intent_id,
                "metadata": metadata,
            },
        )
        try:
            if payment.stripe_charge_id:
                refund = stripe.Refund.create(
                    charge=payment.stripe_charge_id,
                    amount=amount_minor,
                    metadata=metadata,
                    idempotency_key=idempotency_key,
                )
            else:
                refund = stripe.Refund.create(
                    payment_intent=payment.stripe_payment_intent_id,
                    amount=amount_minor,
                    metadata=metadata,
                    idempotency_key=idempotency_key,
                )
        except stripe.error.InvalidRequestError as exc:  # type: ignore[attr-defined]
            message = str(exc).lower()
            if "greater than unrefunded amount" in message or getattr(exc, "code", "") == "amount_too_large":
                if payment.stripe_payment_intent_id:
                    try:
                        payment_services.sync_payment_from_intent(payment.stripe_payment_intent_id)
                    except Exception:
                        logger.exception(
                            "Unable to refresh payment %s after Stripe amount_too_large error",
                            payment.pk,
                        )
                raise RefundError(
                    "Stripe reports this payment has already been refunded more than the requested amount. "
                    "Please refresh the page to see the latest refunded totals."
                ) from exc
            logger.exception("Stripe refund failed for payment %s", payment.pk)
            raise RefundError("Stripe rejected the refund request. Please review the refund amount.") from exc
        except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
            logger.exception("Stripe refund failed for payment %s", payment.pk)
            raise RefundError("Stripe refund failed. Please try again later.") from exc

        refund_id = getattr(refund, "id", None)
        if not refund_id:
            raise RefundError("Stripe did not return a refund identifier.")
        return refund

    @classmethod
    def _sync_payment_after_stripe_refund(
        cls,
        payment: Payment,
        stripe_refund: stripe.Refund,
    ) -> None:
        intent_candidate = payment.stripe_payment_intent_id or getattr(stripe_refund, "payment_intent", None)
        if intent_candidate and not isinstance(intent_candidate, str):
            intent_candidate = getattr(intent_candidate, "id", None)

        intent_id = str(intent_candidate) if intent_candidate else None
        if not intent_id:
            logger.warning(
                "Stripe refund %s for payment %s missing payment_intent; skipping sync",
                getattr(stripe_refund, "id", None),
                payment.pk,
            )
            return

        try:
            updated_payment = payment_services.sync_payment_from_intent(intent_id)
            # keep the locked payment snapshot in sync with refreshed values
            payment.amount_refunded = updated_payment.amount_refunded
            payment.status = updated_payment.status
        except Exception:
            logger.exception(
                "Failed to sync payment %s after Stripe refund %s",
                payment.pk,
                getattr(stripe_refund, "id", None),
            )

    @staticmethod
    def _record_refund(
        *,
        appointment: Appointment,
        payment: Payment,
        amount_minor: int,
        amount_decimal: Decimal,
        method: str,
        actor: "AbstractBaseUser | None",
        stripe_refund_id: str,
    ) -> None:
        PaymentRefund.objects.create(
            appointment=appointment,
            payment=payment,
            amount=amount_decimal,
            amount_minor=amount_minor,
            method=method,
            stripe_refund_id=stripe_refund_id,
            created_by=actor if actor and getattr(actor, "pk", None) else None,
        )


__all__ = ["RefundService", "RefundAllocation", "RefundError"]

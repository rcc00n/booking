"""
Shared helpers for payment-related fee calculations.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")
CARD_PROCESSING_PERCENT = Decimal("0.03")
CARD_PROCESSING_FIXED = Decimal("0.50")


def _to_decimal(amount: Decimal | float | int | str | None) -> Decimal:
    if amount is None:
        return Decimal("0.00")
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount))


def quantize(amount: Decimal | float | int | str | None) -> Decimal:
    """
    Normalize the provided amount to two decimal places.
    """
    return _to_decimal(amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def card_processing_fee(base_amount: Decimal | float | int | str | None) -> Decimal:
    """
    Compute the Stripe card processing surcharge (3% + $0.50) applied on top
    of the provided base amount. Returns a non-negative Decimal rounded to
    two decimal places.
    """
    amount = quantize(base_amount)
    if amount <= Decimal("0.00"):
        return Decimal("0.00")
    fee = (amount * CARD_PROCESSING_PERCENT) + CARD_PROCESSING_FIXED
    return quantize(fee)


def total_with_processing_fee(base_amount: Decimal | float | int | str | None) -> Decimal:
    """
    Convenience helper returning base amount plus the computed processing fee.
    """
    amount = quantize(base_amount)
    fee = card_processing_fee(amount)
    return quantize(amount + fee)


__all__ = [
    "card_processing_fee",
    "total_with_processing_fee",
    "quantize",
    "CARD_PROCESSING_PERCENT",
    "CARD_PROCESSING_FIXED",
]

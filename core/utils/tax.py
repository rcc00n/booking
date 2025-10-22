"""
Utilities for handling GST calculations across the project.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings


TWOPLACES = Decimal("0.01")
HUNDRED = Decimal("100")


def _coerce_decimal(value: object, default: Decimal) -> Decimal:
    """
    Safely convert arbitrary inputs to Decimal for monetary math.
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _sanitize_percent(value: object) -> Decimal:
    """
    Coerce a percentage value into a non-negative Decimal.
    """
    percent = _coerce_decimal(value, Decimal("5.0"))
    if percent < Decimal("0"):
        return Decimal("0.00")
    return percent


def gst_enabled() -> bool:
    """
    Whether GST collection is enabled.
    """
    return bool(getattr(settings, "GST_ENABLED", True))


def gst_percent() -> Decimal:
    """
    Return the configured GST percent, defaulting to 5.00.
    """
    return _sanitize_percent(getattr(settings, "GST_PERCENT", Decimal("5.0")))


def compute_tax(amount: object, *, percent: Decimal | None = None, enabled: bool | None = None) -> Decimal:
    """
    Compute GST for the given amount using ROUND_HALF_UP to two decimals.
    """
    if enabled is None:
        enabled = gst_enabled()
    if not enabled:
        return Decimal("0.00")

    base = _coerce_decimal(amount, Decimal("0.00"))
    if base <= Decimal("0.00"):
        return Decimal("0.00")

    percent_value = _sanitize_percent(percent if percent is not None else gst_percent())
    if percent_value <= Decimal("0"):
        return Decimal("0.00")

    tax = base * (percent_value / HUNDRED)
    return tax.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def total_with_tax(amount: object, *, percent: Decimal | None = None, enabled: bool | None = None) -> Decimal:
    """
    Convenience helper that returns amount + computed tax.
    """
    base = _coerce_decimal(amount, Decimal("0.00"))
    tax = compute_tax(base, percent=percent, enabled=enabled)
    return (base + tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


__all__ = ["gst_enabled", "gst_percent", "compute_tax", "total_with_tax"]

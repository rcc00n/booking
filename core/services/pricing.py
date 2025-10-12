"""Shared pricing utilities for booking carts."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Union

from django.conf import settings

from core.models import BookingCart, BookingCartItem, UserProfile


HUNDRED = Decimal("100")
TWOPLACES = Decimal("0.01")
DEFAULT_CURRENCY = (getattr(settings, "STRIPE_CURRENCY", "cad") or "cad").lower()
CURRENCY_SYMBOLS = {
    "cad": "CA$",
    "usd": "$",
}

UserLike = Union[UserProfile, Any]


class PricingComputationError(ValueError):
    """Raised when pricing data cannot be computed."""


def _quantize(amount: Decimal) -> Decimal:
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount or "0"))
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_minor_units(amount: Decimal) -> int:
    quantized = _quantize(amount)
    return int((quantized * HUNDRED).to_integral_value(rounding=ROUND_HALF_UP))


def _minor_to_decimal(value: int) -> Decimal:
    return (Decimal(value) / HUNDRED).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _format_currency(amount: Decimal, currency: str) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency.lower(), f"{currency.upper()} ")
    return f"{symbol}{_quantize(amount):,.2f}"


def _apply_percent_discount(amount: Decimal, percent: Decimal) -> Decimal:
    percent = max(Decimal("0"), min(percent, HUNDRED))
    factor = (HUNDRED - percent) / HUNDRED
    return amount * factor


def _master_label(master: Any) -> str:
    if not master:
        return ""
    user = getattr(master, "user", None)
    if user:
        full_name = user.get_full_name()
        if full_name:
            return full_name
        username = getattr(user, "username", "")
        if username:
            return username
    return getattr(master, "name", "") or ""


def _resolve_profile(user: UserLike) -> UserProfile:
    if isinstance(user, UserProfile):
        return user
    profile = getattr(user, "userprofile", None)
    if profile:
        return profile
    raise PricingComputationError("User profile is required for cart pricing.")


def _build_discount_entry(
    *,
    discount_type: str,
    percent: Decimal,
    amount: Decimal,
    currency: str,
) -> Dict[str, Any]:
    amount = _quantize(max(amount, Decimal("0.00")))
    if amount <= Decimal("0.00"):
        return {}
    return {
        "type": discount_type,
        "percent": int(percent),
        "amount": _to_minor_units(amount),
        "amount_decimal": f"{amount:.2f}",
        "amount_display": _format_currency(amount, currency),
        "label": f"{discount_type.title()} discount {int(percent)}%",
    }


def _build_item_pricing(
    cart_item: BookingCartItem,
    profile: UserProfile,
    currency: str,
) -> Dict[str, Any]:
    service = cart_item.service
    base_price = _quantize(
        getattr(service, "base_price", None) or Decimal("0.00")
    )
    price = base_price
    discounts: List[Dict[str, Any]] = []

    # Apply service discount if available.
    service_discount = getattr(service, "get_active_discount", lambda: None)()
    service_percent = Decimal(
        getattr(service_discount, "discount_percent", 0) or 0
    )
    if service_percent > 0:
        discounted_price = _apply_percent_discount(price, service_percent)
        discount_amount = price - discounted_price
        entry = _build_discount_entry(
            discount_type="service",
            percent=service_percent,
            amount=discount_amount,
            currency=currency,
        )
        if entry:
            discounts.append(entry)
        price = discounted_price

    # Apply personal discount snapshot.
    personal_percent = Decimal(
        getattr(profile, "personal_discount_percent", 0) or 0
    )
    if personal_percent > 0:
        discounted_price = _apply_percent_discount(price, personal_percent)
        discount_amount = price - discounted_price
        entry = _build_discount_entry(
            discount_type="personal",
            percent=personal_percent,
            amount=discount_amount,
            currency=currency,
        )
        if entry:
            discounts.append(entry)
        price = discounted_price

    price = _quantize(max(price, Decimal("0.00")))
    unit_minor = _to_minor_units(price)
    qty = 1
    subtotal_minor = unit_minor * qty
    subtotal_decimal = _minor_to_decimal(subtotal_minor)

    duration_min = int(
        (getattr(service, "duration_min", 0) or 0)
        + (getattr(service, "extra_time_min", 0) or 0)
    )

    service_payload = {
        "id": str(service.pk),
        "name": getattr(service, "name", ""),
        "duration_min": getattr(service, "duration_min", 0) or 0,
        "extra_time_min": getattr(service, "extra_time_min", 0) or 0,
        "base_price": _to_minor_units(base_price),
        "base_price_decimal": f"{base_price:.2f}",
        "base_price_display": _format_currency(base_price, currency),
        # Preserve legacy field expected by the UI (now discounted).
        "price": f"{price:.2f}",
        "price_display": _format_currency(price, currency),
    }

    master = cart_item.master if hasattr(cart_item, "master") else None
    master_payload: Optional[Dict[str, Any]]
    if master:
        master_payload = {
            "id": str(master.pk),
            "name": _master_label(master),
        }
    else:
        master_payload = None

    discount_payload = [entry for entry in discounts if entry]

    return {
        "id": str(cart_item.pk),
        "service_id": str(service.pk),
        "name": getattr(service, "name", ""),
        "qty": qty,
        "unit_price": unit_minor,
        "unit_price_decimal": f"{price:.2f}",
        "unit_price_display": _format_currency(price, currency),
        "subtotal": subtotal_minor,
        "subtotal_decimal": f"{subtotal_decimal:.2f}",
        "subtotal_display": _format_currency(subtotal_decimal, currency),
        "currency": currency,
        "duration_min": duration_min,
        "start_time": (
            cart_item.start_time.isoformat()
            if getattr(cart_item, "start_time", None)
            else None
        ),
        "service": service_payload,
        "master": master_payload,
        "discounts": discount_payload,
    }


def compute_cart_pricing(
    user: UserLike,
    *,
    cart: Optional[BookingCart] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute authoritative pricing for the authenticated user's booking cart.
    """
    profile = _resolve_profile(user)
    cart_obj = cart or BookingCart.for_user(profile)
    currency_code = (currency or DEFAULT_CURRENCY).lower()

    items_qs = cart_obj.items.select_related("service", "master__user")
    items_payload: List[Dict[str, Any]] = []
    total_minor = 0
    total_duration = 0

    for cart_item in items_qs:
        payload = _build_item_pricing(cart_item, profile, currency_code)
        items_payload.append(payload)
        total_minor += payload["subtotal"]
        total_duration += payload.get("duration_min", 0) or 0

    total_decimal = _minor_to_decimal(total_minor)

    return {
        "cart_id": str(cart_obj.pk),
        "currency": currency_code,
        "items": items_payload,
        "count": len(items_payload),
        "total": total_minor,
        "total_decimal": f"{total_decimal:.2f}",
        "total_display": _format_currency(total_decimal, currency_code),
        # Maintain legacy key for JS callers expecting total_price.
        "total_price": f"{total_decimal:.2f}",
        "total_duration_min": total_duration,
        "is_empty": len(items_payload) == 0,
    }


__all__ = ["compute_cart_pricing", "PricingComputationError"]

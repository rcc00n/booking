"""Stripe payment endpoints and webhook handlers."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

import stripe
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET, require_POST

from core.models import (
    Appointment,
    BookingCart,
    ClientCard,
    Payment,
    PaymentMethod,
    PaymentStatus,
    UserProfile,
)
from core.services.booking import create_appointment_from_cart_items
from core.services import payments as payment_services
from core.services.pricing import compute_cart_pricing, PricingComputationError
from core.tasks import generate_payment_receipt_task, email_payment_receipt_task

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY or None
if getattr(settings, "STRIPE_API_VERSION", None):
    stripe.api_version = settings.STRIPE_API_VERSION


# === Utility helpers ========================================================

def _require_stripe_config() -> None:
    print(settings.STRIPE_SECRET_KEY)
    if not settings.STRIPE_SECRET_KEY:
        raise ImproperlyConfigured("Stripe secret key is not configured.")
    if not stripe.api_key:
        stripe.api_key = settings.STRIPE_SECRET_KEY


def _default_currency() -> str:
    return (getattr(settings, "STRIPE_CURRENCY", "cad") or "cad").lower()


def _lockable(queryset):
    """
    Apply select_for_update only when the database backend supports it.
    """
    if getattr(connection.features, "has_select_for_update", False):
        return queryset.select_for_update()
    return queryset


def _to_minor_units(amount: Decimal) -> int:
    scaled = (amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(scaled)


def _from_minor_units(amount: Optional[int]) -> Decimal:
    if amount is None:
        return Decimal("0.00")
    return (Decimal(amount) / Decimal("100")).quantize(Decimal("0.01"))


def _serialize_stripe_object(data: Any) -> Any:
    if hasattr(data, "to_dict_recursive"):
        return data.to_dict_recursive()
    if isinstance(data, dict):
        return {key: _serialize_stripe_object(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_serialize_stripe_object(item) for item in data]
    return data


def _ensure_payment_status(name: str) -> PaymentStatus:
    status, _ = PaymentStatus.objects.get_or_create(name=name)
    return status


def _serialize_appointment_brief(appointment: Appointment) -> dict[str, Any]:
    """
    Return a compact, UI-friendly representation of the appointment with
    basic timing, service and payment information.
    """
    refreshed = (
        Appointment.objects.select_related("payment_status")
        .filter(pk=appointment.pk)
        .first()
    )
    appt = refreshed or appointment

    item = (
        appt.items.select_related("service", "master__user")
        .order_by("start_time")
        .first()
    )
    service_name = ""
    if item and item.service:
        service_name = item.service.name

    master_name = ""
    if item and item.master:
        master_user = getattr(item.master, "user", None)
        if master_user:
            master_name = master_user.get_full_name() or master_user.username

    return {
        "id": str(appt.pk),
        "start_time": appt.start_time.isoformat() if appt.start_time else None,
        "payment_status": getattr(appt.payment_status, "name", ""),
        "service_name": service_name,
        "master_name": master_name,
    }


def _payment_method_from_funding(funding: Optional[str]) -> PaymentMethod:
    mapping = {
        "credit": "Credit card",
        "debit": "Debit card",
        "prepaid": "Prepaid card",
    }
    method_name = mapping.get((funding or "").lower(), "Stripe")
    method, _ = PaymentMethod.objects.get_or_create(name=method_name)
    return method


def _retrieve_payment_method(payment_method: Optional[Any]) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    if payment_method is None:
        return None, None
    if hasattr(payment_method, "id"):
        try:
            return payment_method.id, payment_method.to_dict_recursive()
        except AttributeError:
            return getattr(payment_method, "id", None), None
    payment_method_id = str(payment_method)
    try:
        pm = stripe.PaymentMethod.retrieve(payment_method_id)
    except stripe.error.StripeError as exc:
        logger.warning("Failed to retrieve payment method %s: %s", payment_method_id, exc)
        return payment_method_id, None
    return payment_method_id, pm.to_dict_recursive()

def _store_profile_customer_id(profile: UserProfile, customer_id: str) -> None:
    if profile.stripe_customer_id != customer_id:
        profile.stripe_customer_id = customer_id
        profile.save(update_fields=["stripe_customer_id"])


def _clear_profile_customer(profile: UserProfile, customer_id: Optional[str]) -> None:
    if not customer_id:
        return
    ClientCard.objects.filter(client=profile, stripe_customer_id=customer_id).delete()
    if profile.stripe_customer_id == customer_id:
        profile.stripe_customer_id = ""
        profile.save(update_fields=["stripe_customer_id"])
    logger.info("Cleared invalid Stripe customer %s for profile %s", customer_id, profile.pk)


def _stripe_customer_exists(customer_id: str) -> bool:
    if not customer_id:
        return False
    _require_stripe_config()
    try:
        stripe.Customer.retrieve(customer_id)
        return True
    except stripe.error.InvalidRequestError as exc:
        if getattr(exc, "code", "") == "resource_missing":
            return False
        raise


def _get_or_create_stripe_customer(profile: UserProfile) -> str:
    existing_customer_id = profile.stripe_customer_id or ""
    if existing_customer_id:
        if _stripe_customer_exists(existing_customer_id):
            return existing_customer_id
        _clear_profile_customer(profile, existing_customer_id)

    existing_card = (
        ClientCard.objects.filter(client=profile)
        .order_by("-is_default", "-created_at")
        .first()
    )
    if existing_card:
        card_customer_id = existing_card.stripe_customer_id
        if card_customer_id and _stripe_customer_exists(card_customer_id):
            _store_profile_customer_id(profile, card_customer_id)
            return card_customer_id
        _clear_profile_customer(profile, card_customer_id)

    _require_stripe_config()
    customer = stripe.Customer.create(
        email=getattr(profile.user, "email", None) or None,
        name=profile.user.get_full_name() or profile.user.username,
        metadata={"user_id": str(profile.pk)},
    )
    _store_profile_customer_id(profile, customer.id)
    return customer.id


def _fetch_intent(intent_obj: Any) -> stripe.PaymentIntent:
    intent_id = getattr(intent_obj, "id", None)
    if not intent_id and isinstance(intent_obj, dict):
        intent_id = intent_obj.get("id")
    if not intent_id:
        raise ValueError("Stripe intent id is missing")
    _require_stripe_config()
    return stripe.PaymentIntent.retrieve(intent_id, expand=["charges", "payment_method"])


def _charge_from_intent(intent: stripe.PaymentIntent) -> Optional[dict[str, Any]]:
    charges = getattr(intent, "charges", None)
    if not charges:
        return None
    data = getattr(charges, "data", None)
    if not data:
        return None
    charge = data[0]
    return _serialize_stripe_object(charge)


def _charge_captured_at(charge: Optional[dict[str, Any]]) -> Optional[datetime]:
    if not charge:
        return None
    created = charge.get("created")
    if not created:
        return None
    return datetime.fromtimestamp(created, tz=dt_timezone.utc)


def _ensure_appointment_from_metadata(metadata: dict[str, Any]) -> Optional[Appointment]:
    appointment_id = metadata.get("appointment_id")
    if not appointment_id:
        return None
    try:
        return Appointment.objects.select_related("client").get(pk=appointment_id)
    except Appointment.DoesNotExist:
        logger.warning("Appointment %s referenced in metadata missing", appointment_id)
        return None


def _ensure_appointment_from_cart(
    profile: UserProfile,
    metadata: dict[str, Any],
    *,
    pricing: Optional[dict[str, Any]] = None,
) -> tuple[Optional[Appointment], Optional[dict[str, Any]]]:
    cart_id = metadata.get("cart_id")
    with transaction.atomic():
        cart_qs = _lockable(BookingCart.objects.filter(owner=profile))
        if cart_id:
            cart_qs = cart_qs.filter(pk=cart_id)
        cart = cart_qs.first()
        if not cart:
            logger.warning(
                "Booking cart missing for user %s while processing payment",
                profile.pk,
            )
            return None, pricing
        computed_pricing = pricing
        if computed_pricing is None:
            try:
                computed_pricing = compute_cart_pricing(profile, cart=cart)
            except PricingComputationError:
                logger.exception(
                    "Failed to compute cart pricing for user %s (cart %s)",
                    profile.pk,
                    cart.pk,
                )
                return None, pricing
        if computed_pricing.get("is_empty"):
            logger.warning(
                "Booking cart %s for user %s is empty during payment",
                cart.pk,
                profile.pk,
            )
            return None, computed_pricing
        items = list(cart.items.select_related("service", "master"))
        if not items:
            logger.warning(
                "Booking cart %s for user %s had no items during payment conversion",
                cart.pk,
                profile.pk,
            )
            return None, computed_pricing
        appointment = create_appointment_from_cart_items(
            profile=profile,
            items=items,
        )
        cart.clear()
    return appointment, computed_pricing

def _sync_client_card(
    profile: Optional[UserProfile],
    customer_id: Optional[str],
    payment_method_id: Optional[str],
    payment_method_data: Optional[dict[str, Any]],
) -> None:
    if not profile or not customer_id or not payment_method_id or not payment_method_data:
        return
    card_data = payment_method_data.get("card") or {}
    if not card_data:
        return

    defaults = {
        "client": profile,
        "stripe_customer_id": customer_id,
        "brand": card_data.get("brand", ""),
        "last4": card_data.get("last4", ""),
        "exp_month": card_data.get("exp_month") or 0,
        "exp_year": card_data.get("exp_year") or 0,
        "funding": card_data.get("funding", "unknown"),
    }
    with transaction.atomic():
        card_obj, created = ClientCard.objects.update_or_create(
            stripe_payment_method_id=payment_method_id,
            defaults=defaults,
        )
        if created and not ClientCard.objects.filter(client=profile, is_default=True).exclude(pk=card_obj.pk).exists():
            ClientCard.objects.filter(client=profile).exclude(pk=card_obj.pk).update(is_default=False)
            card_obj.is_default = True
            card_obj.save(update_fields=["is_default", "updated_at"])
        _store_profile_customer_id(profile, customer_id)


def _upsert_payment_from_intent(
    intent: stripe.PaymentIntent,
    appointment: Optional[Appointment],
    payment_method_id: Optional[str],
    payment_method_data: Optional[dict[str, Any]],
) -> Payment:
    charge = _charge_from_intent(intent)
    amount = _from_minor_units(getattr(intent, "amount", None))
    charge_id = charge.get("id") if charge else None
    receipt_url = charge.get("receipt_url") or "" if charge else ""
    amount_refunded = _from_minor_units(charge.get("amount_refunded")) if charge else Decimal("0.00")
    captured_at = _charge_captured_at(charge)
    amount_received = _from_minor_units(getattr(intent, "amount_received", None))
    currency = (getattr(intent, "currency", None) or _default_currency()).lower()
    metadata = dict(getattr(intent, "metadata", {}) or {})
    raw_response = intent.to_dict_recursive()
    method = _payment_method_from_funding((payment_method_data or {}).get("card", {}).get("funding"))

    with transaction.atomic():
        payment = _lockable(Payment.objects).filter(
            stripe_payment_intent_id=intent.id
        ).first()
        if payment is None:
            payment = Payment.objects.create(
                appointment=appointment,
                amount=amount,
                currency=currency,
                method=method,
                status=getattr(intent, "status", "requires_payment_method"),
                stripe_payment_intent_id=intent.id,
                stripe_payment_method_id=payment_method_id,
                stripe_charge_id=charge_id,
                receipt_url=receipt_url,
                livemode=bool(getattr(intent, "livemode", False)),
                metadata=metadata,
                raw_response=raw_response,
                amount_received=amount_received,
                amount_refunded=amount_refunded,
                captured_at=captured_at,
            )
        else:
            payment.appointment = appointment or payment.appointment
            payment.amount = amount
            payment.currency = currency
            payment.method = method
            payment.status = getattr(intent, "status", payment.status)
            payment.stripe_payment_method_id = payment_method_id
            payment.stripe_charge_id = charge_id
            payment.receipt_url = receipt_url
            payment.livemode = bool(getattr(intent, "livemode", payment.livemode))
            payment.metadata = metadata
            payment.raw_response = raw_response
            payment.amount_received = amount_received
            payment.amount_refunded = amount_refunded
            payment.captured_at = captured_at
            payment._skip_receipt_signal = True
            payment.save()
    return payment


def _update_appointment_payment_status(appointment: Optional[Appointment], succeeded: bool) -> None:
    if not appointment:
        return
    target = _ensure_payment_status("Paid" if succeeded else "Failed")
    if appointment.payment_status_id != target.id:
        appointment.payment_status = target
        appointment.save(update_fields=["payment_status"])


def _handle_payment_intent_succeeded(intent_obj: Any) -> Payment:
    intent = _fetch_intent(intent_obj)
    metadata = dict(getattr(intent, "metadata", {}) or {})
    appointment = _ensure_appointment_from_metadata(metadata)
    pricing_snapshot: Optional[dict[str, Any]] = None

    payment = (
        Payment.objects.filter(stripe_payment_intent_id=intent.id)
        .select_related("appointment__client")
        .first()
    )
    previous_metadata = dict(payment.metadata or {}) if payment else {}
    if payment and payment.appointment:
        appointment = payment.appointment

    profile: Optional[UserProfile] = appointment.client if appointment else None
    if not appointment:
        user_id = metadata.get("user_id")
        if user_id:
            profile = (
                UserProfile.objects.select_related("user")
                .filter(pk=user_id)
                .first()
            )
        if profile:
            appointment, pricing_snapshot = _ensure_appointment_from_cart(
                profile,
                metadata,
            )
            if appointment:
                profile = appointment.client
        elif payment and payment.appointment:
            appointment = payment.appointment
            profile = appointment.client
    elif appointment:
        profile = appointment.client

    payment_method_id = getattr(intent, "payment_method", None)
    if not payment_method_id:
        charge = _charge_from_intent(intent)
        payment_method_id = (charge or {}).get("payment_method")
    payment_method_id, payment_method_data = _retrieve_payment_method(payment_method_id)

    if profile and getattr(intent, "customer", None):
        _store_profile_customer_id(profile, intent.customer)

    payment = _upsert_payment_from_intent(intent, appointment, payment_method_id, payment_method_data)

    if profile or (appointment and appointment.client):
        _sync_client_card(profile or appointment.client, getattr(intent, "customer", None), payment_method_id, payment_method_data)

    meta_changed = False
    meta = dict(payment.metadata or {})
    if pricing_snapshot:
        meta["cart_pricing"] = pricing_snapshot
        expected_total = pricing_snapshot.get("total")
        intent_amount = getattr(intent, "amount_received", None)
        if intent_amount is None:
            intent_amount = getattr(intent, "amount", None)
        if (
            isinstance(intent_amount, int)
            and isinstance(expected_total, int)
            and expected_total != intent_amount
        ):
            meta["pricing_amount_mismatch"] = {
                "expected": expected_total,
                "intent": intent_amount,
            }
            logger.warning(
                "Stripe intent %s amount mismatch (expected %s, got %s)",
                intent.id,
                expected_total,
                intent_amount,
            )
        meta_changed = True

    if "cart_pricing" not in meta and "cart_pricing" in previous_metadata:
        meta["cart_pricing"] = previous_metadata["cart_pricing"]
        meta_changed = True

    if appointment and metadata.get("appointment_id") != str(appointment.pk):
        meta["appointment_id"] = str(appointment.pk)
        meta_changed = True

    if meta_changed:
        payment.metadata = meta
        payment.save(update_fields=["metadata", "updated_at"])

    _update_appointment_payment_status(appointment, succeeded=True)

    if payment.status == "succeeded":
        payment_id = str(payment.pk)
        generate_payment_receipt_task.delay(payment_id)
        email_payment_receipt_task.delay(payment_id)

    return payment


def _handle_payment_intent_failed(intent_obj: Any) -> Payment:
    intent = _fetch_intent(intent_obj)
    metadata = dict(getattr(intent, "metadata", {}) or {})
    appointment = _ensure_appointment_from_metadata(metadata)
    payment_method_id = getattr(intent, "payment_method", None)
    if not payment_method_id:
        charge = _charge_from_intent(intent)
        payment_method_id = (charge or {}).get("payment_method")
    payment_method_id, payment_method_data = _retrieve_payment_method(payment_method_id)
    payment = _upsert_payment_from_intent(intent, appointment, payment_method_id, payment_method_data)
    error = getattr(intent, "last_payment_error", None)
    if error:
        meta = dict(payment.metadata)
        meta["last_payment_error"] = _serialize_stripe_object(error)
        payment.metadata = meta
        payment.save(update_fields=["metadata", "updated_at"])
    _update_appointment_payment_status(appointment, succeeded=False)
    return payment


def _handle_payment_method_attached(method_obj: Any) -> None:
    data = _serialize_stripe_object(method_obj)
    customer_id = data.get("customer")
    if not customer_id:
        return
    profile = (
        UserProfile.objects.filter(stripe_customer_id=customer_id)
        .first()
    )
    if not profile:
        card_record = (
            ClientCard.objects.select_related("client")
            .filter(stripe_customer_id=customer_id)
            .first()
        )
        profile = getattr(card_record, "client", None)
    if not profile:
        logger.info("Skipping payment_method.attached for unknown customer %s", customer_id)
        return
    _sync_client_card(profile, customer_id, data.get("id"), data)

@login_required
@require_POST
@csrf_protect
def stripe_create_cart_intent(request):
    profile = request.user.userprofile
    cart = BookingCart.for_user(profile)
    try:
        with transaction.atomic():
            locked_cart = _lockable(
                BookingCart.objects.filter(pk=cart.pk)
            ).first()
            pricing = compute_cart_pricing(profile, cart=locked_cart or cart)
    except PricingComputationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if pricing.get("is_empty"):
        return JsonResponse({"error": "Cart is empty."}, status=400)

    if pricing["total"] <= 0:
        with transaction.atomic():
            appointment, pricing_snapshot = _ensure_appointment_from_cart(
                profile,
                {"cart_id": pricing["cart_id"]},
                pricing=pricing,
            )
            if not appointment:
                return JsonResponse(
                    {"error": "Unable to create appointment from cart."},
                    status=400,
                )
            bundle = payment_services.create_or_update_payment_intent(
                appointment,
                amount=Decimal("0.00"),
                currency=pricing["currency"],
            )
            payment = bundle.payment
            meta = dict(payment.metadata or {})
            meta["cart_pricing"] = pricing_snapshot or pricing
            meta["cart_checkout"] = {"mode": "free"}
            payment.metadata = meta
            payment.raw_response = {"source": "cart_zero_total"}
            payment.save(update_fields=["metadata", "raw_response", "updated_at"])
            _update_appointment_payment_status(appointment, succeeded=True)
        pricing_payload = pricing_snapshot or pricing
        return JsonResponse(
            {
                "requires_payment": False,
                "appointment_id": str(appointment.pk),
                "payment_id": str(payment.pk),
                "amount": pricing_payload["total_decimal"],
                "amount_minor": pricing_payload["total"],
                "currency": pricing_payload["currency"],
                "cart": pricing_payload,
            }
        )

    try:
        customer_id = _get_or_create_stripe_customer(profile)
    except ImproperlyConfigured as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except stripe.error.StripeError as exc:
        logger.exception("Stripe error retrieving customer for user %s", profile.pk)
        return JsonResponse({"error": getattr(exc, "user_message", str(exc))}, status=400)

    stripe_metadata = {
        "user_id": str(profile.pk),
        "cart_id": str(pricing["cart_id"]),
        "booking_type": "appointment_cart",
        "cart_total_minor": str(pricing["total"]),
        "cart_subtotal_minor": str(pricing.get("subtotal", 0)),
        "cart_tax_minor": str(pricing.get("tax_total", 0)),
        "cart_currency": pricing["currency"],
        "cart_item_count": str(pricing.get("count", len(pricing.get("items", [])))),
    }

    try:
        intent = stripe.PaymentIntent.create(
            amount=pricing["total"],
            currency=pricing["currency"],
            customer=customer_id,
            automatic_payment_methods={"enabled": True},
            setup_future_usage="off_session",
            metadata=stripe_metadata,
        )
    except ImproperlyConfigured as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except stripe.error.StripeError as exc:
        logger.exception("Stripe error creating payment intent for user %s", profile.pk)
        return JsonResponse({"error": getattr(exc, "user_message", str(exc))}, status=400)

    return JsonResponse(
        {
            "requires_payment": True,
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "amount": pricing["total_decimal"],
            "amount_minor": pricing["total"],
            "currency": pricing["currency"],
            "cart": pricing,
        }
    )


@login_required
@require_POST
@csrf_protect
def stripe_finalize_cart_booking(request):
    profile = getattr(request.user, "userprofile", None)
    if profile is None:
        return JsonResponse({"error": "User profile is required to finalize the booking."}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    payment_intent_id = payload.get("payment_intent_id")
    cart_id = payload.get("cart_id")

    if not payment_intent_id:
        return JsonResponse({"error": "payment_intent_id is required."}, status=400)

    try:
        intent = _fetch_intent({"id": payment_intent_id})
    except ImproperlyConfigured as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except stripe.error.StripeError as exc:
        logger.exception("Failed to retrieve intent %s during cart finalization.", payment_intent_id)
        return JsonResponse({"error": getattr(exc, "user_message", str(exc))}, status=502)

    metadata = dict(getattr(intent, "metadata", {}) or {})
    metadata["user_id"] = str(profile.pk)
    if cart_id:
        metadata["cart_id"] = str(cart_id)

    appointment = _ensure_appointment_from_metadata(metadata)
    already_finalized = appointment is not None

    if appointment and appointment.client_id != profile.id:
        return JsonResponse(
            {"error": "This appointment belongs to another user."},
            status=403,
        )

    if appointment is None:
        appointment, _pricing = _ensure_appointment_from_cart(profile, metadata)
        if appointment is None:
            return JsonResponse(
                {"error": "Unable to create an appointment from the current cart."},
                status=404,
            )

    metadata["appointment_id"] = str(appointment.pk)

    try:
        stripe.PaymentIntent.modify(payment_intent_id, metadata=metadata)
    except stripe.error.StripeError as exc:
        logger.warning(
            "Failed to update metadata for payment intent %s: %s",
            payment_intent_id,
            exc,
        )

    summary = _serialize_appointment_brief(appointment)
    return JsonResponse(
        {
            "ok": True,
            "appointment": summary,
            "already_finalized": already_finalized,
        }
    )


@login_required
@require_GET
def stripe_list_cards(request):
    profile = request.user.userprofile
    cards = (
        ClientCard.objects.filter(client=profile)
        .order_by("-is_default", "-created_at")
    )
    return JsonResponse(
        {
            "cards": [
                {
                    "id": str(card.pk),
                    "label": card.label(),
                    "is_default": card.is_default,
                    "brand": card.brand,
                    "funding": card.funding,
                }
                for card in cards
            ]
        }
    )


@login_required
@require_POST
@csrf_protect
def stripe_set_default_card(request):
    profile = request.user.userprofile
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)
    card_id = payload.get("client_card_id")
    if not card_id:
        return JsonResponse({"error": "client_card_id is required."}, status=400)

    card = get_object_or_404(ClientCard, pk=card_id, client=profile)
    customer_id = card.stripe_customer_id

    with transaction.atomic():
        ClientCard.objects.filter(client=profile).update(is_default=False)
        card.is_default = True
        card.save(update_fields=["is_default", "updated_at"])
        _store_profile_customer_id(profile, customer_id)

    try:
        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": card.stripe_payment_method_id},
        )
    except stripe.error.StripeError as exc:
        logger.exception("Failed to set default payment method for customer %s", customer_id)
        return JsonResponse({"error": getattr(exc, "user_message", str(exc))}, status=502)

    return JsonResponse({"ok": True})


@staff_member_required
@require_POST
@csrf_protect
def stripe_no_show_charge(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)
    appointment_id = payload.get("appointment_id")
    if not appointment_id:
        return JsonResponse({"error": "appointment_id is required."}, status=400)

    appointment = get_object_or_404(
        Appointment.objects.select_related("client__user"),
        pk=appointment_id,
    )
    profile = appointment.client
    if not profile:
        return JsonResponse({"error": "Appointment has no associated client."}, status=400)

    card = (
        ClientCard.objects.filter(client=profile, is_default=True)
        .order_by("-updated_at")
        .first()
    )
    if not card:
        card = (
            ClientCard.objects.filter(client=profile)
            .order_by("-updated_at")
            .first()
        )
    if not card:
        return JsonResponse({"error": "Client has no saved cards."}, status=400)

    if appointment.final_price is None:
        appointment.recompute_totals(save=True)
    total = appointment.final_price or Decimal("0.00")
    amount = (total * Decimal("0.5")).quantize(Decimal("0.01"))
    if amount <= Decimal("0.00"):
        return JsonResponse({"error": "Appointment has no outstanding balance."}, status=400)

    try:
        _require_stripe_config()
        intent = stripe.PaymentIntent.create(
            amount=_to_minor_units(amount),
            currency=_default_currency(),
            customer=card.stripe_customer_id,
            payment_method=card.stripe_payment_method_id,
            off_session=True,
            confirm=True,
            error_on_requires_action=True,
            metadata={
                "reason": "no_show",
                "appointment_id": str(appointment.pk),
                "user_id": str(profile.pk),
            },
        )
    except stripe.error.CardError as exc:
        logger.warning("Card error during no-show charge for appointment %s: %s", appointment.pk, exc)
        return JsonResponse({"error": getattr(exc, "user_message", str(exc))}, status=402)
    except stripe.error.StripeError as exc:
        logger.exception("Stripe error during no-show charge for appointment %s", appointment.pk)
        return JsonResponse({"error": getattr(exc, "user_message", str(exc))}, status=502)

    payment_method_id, payment_method_data = _retrieve_payment_method(intent.payment_method)
    payment = _upsert_payment_from_intent(intent, appointment, payment_method_id, payment_method_data)
    _sync_client_card(profile, card.stripe_customer_id, payment_method_id, payment_method_data)
    _update_appointment_payment_status(appointment, succeeded=intent.status == "succeeded")

    return JsonResponse(
        {
            "ok": True,
            "payment_id": str(payment.pk),
            "status": payment.status,
            "amount": str(payment.amount_received or amount),
            "receipt_url": payment.receipt_url,
        }
    )

@csrf_exempt
@require_POST
def stripe_webhook(request):
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    payload = request.body
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook secret is not configured")
        return HttpResponse(status=503)
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        logger.warning("Invalid Stripe webhook signature")
        return HttpResponse(status=400)

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object")

    try:
        if event_type == "payment_intent.succeeded":
            _handle_payment_intent_succeeded(data_object)
        elif event_type in {"payment_intent.payment_failed", "payment_intent.canceled"}:
            _handle_payment_intent_failed(data_object)
        elif event_type == "charge.failed":
            intent_id = data_object.get("payment_intent") if data_object else None
            if intent_id:
                intent = _fetch_intent({"id": intent_id})
                _handle_payment_intent_failed(intent)
        elif event_type == "payment_method.attached":
            _handle_payment_method_attached(data_object)
        else:
            logger.debug("Unhandled Stripe event %s", event_type)
    except Exception:  # pragma: no cover - ensure webhook ack and log
        logger.exception("Error processing Stripe webhook (%s)", event_type)
        return HttpResponse(status=500)

    return HttpResponse(status=200)

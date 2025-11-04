# core/views.py
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.forms import inlineformset_factory
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Prefetch, Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
import logging
from datetime import datetime
from decimal import Decimal
from django.core.exceptions import ImproperlyConfigured, ValidationError, PermissionDenied
from django.db import transaction
import json
import stripe

from core.models import (
    Appointment, ServiceCategory, Service, PromoCode,
    AppointmentStatusHistory, AppointmentItemStatusHistory, MasterProfile, UserProfile, CancellationReason,
    AppointmentItem, BookingCart, BookingCartItem, Payment, ClientIntakeForm, ServiceMaster, ProductSale,
)
from core.services.booking import (
    get_available_slots,
    get_service_masters,
    get_or_create_status,
    get_default_payment_status,
    _tz_aware,
    create_appointment_from_cart_items,
)
from core.services.item_status import record_item_status
from accounts.utils import build_autofill_defaults
from core.services import payments as payment_services
from core.services.pricing import (
    compute_cart_pricing,
    compute_appointment_pricing,
    get_available_prepayment_percents,
    PricingComputationError,
)
from core.services.refunds import RefundService, RefundError

logger = logging.getLogger(__name__)
from core.utils.fees import card_processing_fee
from core.tasks import send_item_cancellation_email, send_item_confirmation_email
from core.forms import PaymentRefundForm

def _build_catalog_context(request):
    """Общий конструктор контекста каталога."""
    q = (request.GET.get("q") or "").strip()
    cat = request.GET.get("cat") or ""

    today = timezone.now().date()
    discount_window = Q(discounts__start_date__lte=today, discounts__end_date__gte=today)

    services_qs = (
        Service.objects.filter(is_active=True)
        .select_related("category")
        .prefetch_related(
            Prefetch(
                "pre_appointment_forms",
                queryset=ClientIntakeForm.objects.filter(is_active=True),
            )
        )
        .order_by("name")
    )
    if q:
        services_qs = services_qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

    discounted_services_qs = services_qs.filter(discount_window).distinct()

    selected_category = None
    if cat:
        selected_category = ServiceCategory.objects.filter(pk=cat).first()
        if selected_category:
            if selected_category.only_discounted_services:
                services_qs = discounted_services_qs
            else:
                services_qs = services_qs.filter(category=selected_category)
                discounted_services_qs = services_qs.filter(discount_window).distinct()

    categories_qs = ServiceCategory.objects.for_catalog().prefetch_related(
        Prefetch("service_set", queryset=services_qs)
    )
    categories = []
    discounted_services = None
    for category in categories_qs:
        if category.only_discounted_services:
            if selected_category and not getattr(selected_category, "only_discounted_services", False):
                category.catalog_services = []
                categories.append(category)
                continue
            if discounted_services is None:
                discounted_services = list(discounted_services_qs)
            category.catalog_services = discounted_services
        else:
            if selected_category and getattr(selected_category, "only_discounted_services", False):
                category.catalog_services = []
            else:
                category.catalog_services = list(category.service_set.all())
        categories.append(category)

    return {
        "categories": categories,
        "filter_categories": ServiceCategory.objects.for_catalog(),
        "q": q,
        "active_category": str(cat),
        "search_results": services_qs if q else None,
        "has_any_services": services_qs.exists(),
        "uncategorized": services_qs.filter(category__isnull=True),
    }

def public_mainmenu(request):
    """
    Публичная главная страница (каталог). Доступна всем.
    Если пользователь авторизован — дополнительно подставим профиль и его записи.
    """
    ctx = _build_catalog_context(request)

    if request.user.is_authenticated:
        user = request.user
        ctx["profile"] = getattr(user, "userprofile", None)
        items_prefetch = Prefetch(
            "items",
            queryset=AppointmentItem.objects.select_related("service", "master__user").order_by("start_time"),
        )
        ctx["appointments"] = (
            Appointment.objects
            .filter(client=user.userprofile)
            .prefetch_related(items_prefetch)
            .order_by("-start_time")
        )
    else:
        # чтобы шаблон не спотыкался, если где-то используешь эти ключи
        ctx.setdefault("profile", None)
        ctx.setdefault("appointments", [])

    ctx["stripe_public_key"] = settings.STRIPE_PUBLIC_KEY
    ctx["autofill_defaults"] = build_autofill_defaults(request.user)
    options = get_available_prepayment_percents()
    ctx["prepayment_options"] = options
    ctx["prepayment_choices"] = [
        {"percent": value, "remaining": max(0, 100 - int(value))}
        for value in options
    ]
    ctx["default_prepayment_percent"] = options[0] if options else 100

    return render(request, "client/mainmenu.html", ctx)

# ===== API (оставляем только для авторизованных) =====

@login_required
@require_GET
def api_availability(request):
    service_id = request.GET.get("service")
    date_str = request.GET.get("date")
    master_id = request.GET.get("master")
    if not service_id or not date_str:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("service and date required")

    service = get_object_or_404(Service.objects.select_related("category"), pk=service_id)
    if not service.is_active:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("service is inactive")
    day = parse_date(date_str)
    if not day:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("invalid date")

    day_dt = _tz_aware(datetime(day.year, day.month, day.day, 12, 0))
    master_obj = get_object_or_404(MasterProfile, pk=master_id) if master_id else None
    slots_map = get_available_slots(service, day_dt, master=master_obj)

    resp = {
        "service": {"id": str(service.pk), "name": service.name, "duration": service.duration_min},
        "date": date_str,
    }

    if master_obj:
        resp["slots"] = [s.isoformat() for s in slots_map.get(master_obj.id, [])]
    else:
        masters_qs = list(get_service_masters(service))
        resp["masters"] = [
            {
                "id": m.id,
                "name": m.user.get_full_name() or m.user.username,
                "slots": [s.isoformat() for s in slots_map.get(m.id, [])],
            }
            for m in masters_qs
        ]
    from django.http import JsonResponse
    return JsonResponse(resp)

@login_required
@require_POST
@csrf_protect
def api_book(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("invalid json")

    service_id = payload.get("service")
    master_id  = payload.get("master")
    start_iso  = payload.get("start_time")

    if not service_id or not master_id or not start_iso:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("service, master, start_time required")

    service = get_object_or_404(Service, pk=service_id)
    if not service.is_active:
        return JsonResponse({"error": "service is inactive"}, status=400)
    master  = get_object_or_404(MasterProfile, pk=master_id)

    if not get_service_masters(service).filter(pk=master.pk).exists():
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("master can't perform this service")

    try:
        start_dt = parse_datetime(start_iso) or _tz_aware(datetime.fromisoformat(start_iso))
        if not timezone.is_aware(start_dt):
            start_dt = _tz_aware(start_dt)
    except Exception:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("invalid start_time")

    try:
        with transaction.atomic():
            pay_status = get_default_payment_status()
            appt = Appointment(
                client=request.user.userprofile,
                start_time=start_dt,
                payment_status=pay_status if pay_status else None,
            )
            appt.full_clean()
            appt.save()

            item = AppointmentItem(
                appointment=appt,
                service=service,
                master=master,
                start_time=start_dt,
            )
            item.full_clean()
            item.save()

            appt.sync_start_time_from_items(save=True)
            appt.recompute_totals(save=True)

            initial_status = get_or_create_status("Confirmed")
            AppointmentStatusHistory.objects.create(
                appointment=appt,
                status=initial_status,
                set_by=request.user.userprofile
            )
    except ValidationError as exc:
        messages = []
        if hasattr(exc, "message_dict"):
            for vals in exc.message_dict.values():
                if isinstance(vals, (list, tuple)):
                    messages.extend(vals)
                else:
                    messages.append(str(vals))
        else:
            messages.extend(getattr(exc, "messages", [str(exc)]))
        return JsonResponse({"error": messages[0] if messages else "Invalid data"}, status=400)

    return JsonResponse({
        "ok": True,
        "appointment": {
            "id": str(appt.pk),
            "service": service.name,
            "master": master.user.get_full_name() or master.user.username,
            "start_time": appt.start_time.isoformat(),
        }
    }, status=201)


# ===== CART API =====

def _ensure_profile(user):
    profile = getattr(user, "userprofile", None)
    if profile is None:
        profile = UserProfile.objects.create(user=user)
    return profile

@login_required
@require_GET
def api_cart_summary(request):
    profile = _ensure_profile(request.user)
    cart = BookingCart.for_user(profile)
    pricing = compute_cart_pricing(profile, cart=cart)
    return JsonResponse(pricing)


@login_required
@require_POST
@csrf_protect
def api_cart_add(request):
    profile = _ensure_profile(request.user)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "invalid json"}, status=400)

    service_id = payload.get("service")
    master_id = payload.get("master")
    start_iso = payload.get("start_time")

    if not service_id or not master_id or not start_iso:
        return JsonResponse({"error": "service, master and start_time required"}, status=400)

    service = get_object_or_404(Service, pk=service_id)
    if not service.is_active:
        return JsonResponse({"error": "service is inactive"}, status=400)
    master = get_object_or_404(MasterProfile, pk=master_id)

    if not get_service_masters(service).filter(pk=master.pk).exists():
        return JsonResponse({"error": "master can't perform this service"}, status=400)

    try:
        start_dt = parse_datetime(start_iso) or _tz_aware(datetime.fromisoformat(start_iso))
        if not timezone.is_aware(start_dt):
            start_dt = _tz_aware(start_dt)
    except Exception:
        return JsonResponse({"error": "invalid start_time"}, status=400)

    # Validate that the chosen slot is actually available for this service/master/date
    day_key = start_dt.date().isoformat()
    slots_map = get_available_slots(service, _tz_aware(datetime(start_dt.year, start_dt.month, start_dt.day, 12, 0)), master=master)
    allowed = set(s.isoformat() for s in slots_map.get(master.id, []))
    if start_dt.isoformat() not in allowed:
        return JsonResponse({"error": "Selected slot is no longer available."}, status=400)

    cart = BookingCart.for_user(profile)

    # Check overlap against existing cart items for the same master
    def _duration_min(svc: Service) -> int:
        return int((svc.duration_min or 0) + (svc.extra_time_min or 0))

    new_start = start_dt
    new_end = start_dt + timezone.timedelta(minutes=_duration_min(service))
    for it in cart.items.select_related("service", "master").all():
        if it.master_id != master.id:
            continue
        it_start = it.start_time
        it_end = it.start_time + timezone.timedelta(minutes=_duration_min(it.service))
        if new_start < it_end and new_end > it_start:
            return JsonResponse({"error": "Selected slot overlaps with another item in your cart."}, status=400)

    item = BookingCartItem(cart=cart, service=service, master=master, start_time=start_dt)
    try:
        item.full_clean()
        item.save()
    except ValidationError as exc:
        messages = []
        if hasattr(exc, "message_dict"):
            for vals in exc.message_dict.values():
                if isinstance(vals, (list, tuple)):
                    messages.extend(vals)
                else:
                    messages.append(str(vals))
        else:
            messages.extend(getattr(exc, "messages", [str(exc)]))
        return JsonResponse({"error": messages[0] if messages else "Invalid data"}, status=400)

    pricing = compute_cart_pricing(profile, cart=cart)
    return JsonResponse(
        {"ok": True, "item_id": str(item.pk), "cart": pricing},
        status=201,
    )


@login_required
@require_POST
@csrf_protect
def api_cart_remove(request, item_id):
    profile = _ensure_profile(request.user)
    cart = BookingCart.for_user(profile)
    item = cart.items.filter(pk=item_id).first()
    if not item:
        return JsonResponse({"error": "item not found"}, status=404)
    item.delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
@csrf_protect
def api_payment_verify(request, appt_id):
    appt = get_object_or_404(
        Appointment.objects.select_related("client", "payment_status").prefetch_related("payments"),
        pk=appt_id,
    )

    profile = getattr(request.user, "userprofile", None)
    if not (request.user.is_staff or (profile and appt.client_id == profile.id)):
        return JsonResponse({"error": "not allowed"}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "invalid json"}, status=400)

    intent_id = payload.get("payment_intent_id")
    if not intent_id:
        return JsonResponse({"error": "payment_intent_id required"}, status=400)

    try:
        payment = payment_services.sync_payment_from_intent(intent_id)
    except Payment.DoesNotExist:
        return JsonResponse({"error": "payment not found"}, status=404)
    except ImproperlyConfigured as cfg_err:
        return JsonResponse({"error": str(cfg_err)}, status=500)
    except stripe.error.StripeError as err:
        return JsonResponse({"error": getattr(err, "user_message", str(err))}, status=502)

    appt.refresh_from_db(fields=["payment_status"])

    return JsonResponse({
        "ok": True,
        "payment": {
            "id": str(payment.id),
            "status": payment.status,
            "amount": str(payment.amount),
            "amount_received": str(payment.amount_received),
            "amount_refunded": str(payment.amount_refunded),
            "currency": payment.currency,
            "receipt_url": payment.receipt_url,
        },
        "appointment": {
            "id": str(appt.pk),
            "payment_status": getattr(appt.payment_status, "name", ""),
        },
    })


@csrf_exempt
@staff_member_required
@require_POST
def terminal_connection_token(request):
    secret_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not secret_key:
        return JsonResponse({"error": "Stripe is not configured"}, status=500)

    stripe.api_key = secret_key
    api_version = getattr(settings, "STRIPE_API_VERSION", None)
    if api_version:
        stripe.api_version = api_version
    try:
        token = stripe.terminal.ConnectionToken.create()
    except stripe.error.StripeError as err:
        return JsonResponse({"error": getattr(err, "user_message", str(err))}, status=502)
    return JsonResponse({"secret": token.secret})


@staff_member_required
@require_POST
@csrf_protect
def api_terminal_start(request, appt_id):
    appt = get_object_or_404(
        Appointment.objects.select_related("client"),
        pk=appt_id,
    )

    # Ensure base totals are current before applying the card-present surcharge.
    appt.recompute_totals(save=True)
    paid_total = payment_services.get_total_received_for_appointment(appt)
    existing_fee = Decimal(getattr(appt, "card_processing_fee", Decimal("0.00")) or Decimal("0.00"))
    pre_fee_total = Decimal(appt.final_price or Decimal("0.00")) - existing_fee
    if pre_fee_total < Decimal("0.00"):
        pre_fee_total = Decimal("0.00")
    outstanding_due = (Decimal(appt.final_price or Decimal("0.00")) - paid_total).quantize(Decimal("0.01"))
    if outstanding_due <= Decimal("0.00"):
        return JsonResponse({"ok": False, "error": "Appointment has no outstanding balance."}, status=400)

    card_fee = card_processing_fee(outstanding_due)
    total_fee = (existing_fee + card_fee).quantize(Decimal("0.01"))
    appt.apply_card_processing_fee = True
    appt.card_processing_fee = total_fee
    appt.final_price = (pre_fee_total + total_fee).quantize(Decimal("0.01"))
    appt.save(update_fields=["apply_card_processing_fee", "card_processing_fee", "final_price"])

    outstanding_total = payment_services.get_outstanding_amount(appt)
    if outstanding_total <= Decimal("0.00"):
        return JsonResponse({"ok": False, "error": "Appointment has no outstanding balance."}, status=400)

    amount_to_charge = outstanding_total

    try:
        bundle = payment_services.create_or_update_terminal_intent(appt, amount=amount_to_charge)
    except stripe.error.StripeError as err:
        return JsonResponse({"ok": False, "error": getattr(err, "user_message", str(err))}, status=502)
    except ImproperlyConfigured as cfg_err:
        return JsonResponse({"ok": False, "error": str(cfg_err)}, status=500)

    intent = getattr(bundle, "intent", None)
    if not intent:
        return JsonResponse({"ok": False, "error": "PaymentIntent not created"}, status=500)

    return JsonResponse(
        {
            "ok": True,
            "payment_intent_id": intent.id,
            "client_secret": intent.client_secret,
            "amount": str(bundle.payment.amount),
            "currency": bundle.payment.currency,
            "outstanding": str(outstanding_total),
        }
    )



# --- API: отмена/перенос записи ---
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponse, Http404
from django.shortcuts import get_object_or_404

from core.models import (
    Appointment, AppointmentStatus, AppointmentStatusHistory,
    CustomUserDisplay, ServiceMaster, AppointmentItem
)

def _status(name: str) -> AppointmentStatus:
    obj, _ = AppointmentStatus.objects.get_or_create(name=name)
    return obj



def _fetch_admin_item(item_id):
    return (
        AppointmentItem.objects.select_related(
            "appointment__client__user",
            "appointment__payment_status",
            "service",
            "status",
        )
        .prefetch_related(
            Prefetch(
                "status_history",
                queryset=AppointmentItemStatusHistory.objects.select_related(
                    "status", "set_by"
                ).order_by("-set_at", "-id"),
                to_attr="_export_status_history",
            )
        )
        .filter(pk=item_id)
        .first()
    )


@staff_member_required
@require_POST
@csrf_protect
def admin_item_status_update(request, item_id):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    status_value = payload.get("status") or payload.get("code") or ""
    status_code = str(status_value).upper().strip()
    if not status_code:
        return JsonResponse({"error": "Status code required"}, status=400)
    allowed_codes = {"BOOKED", "CONFIRMED", "CANCELLED", "COMPLETED"}
    if status_code not in allowed_codes:
        return JsonResponse({"error": f"Unsupported status '{status_code}'"}, status=400)

    item = _fetch_admin_item(item_id)
    if not item:
        return JsonResponse({"error": "Item not found"}, status=404)

    note = payload.get("note")
    reason = payload.get("reason")
    notify = payload.get("notify", True)
    set_by_id = getattr(request.user, "id", None)

    result = record_item_status(
        item,
        status_code,
        set_by_user_id=set_by_id,
        note=note,
    )

    item.refresh_from_db(fields=["status"])

    appointment = (
        Appointment.objects.with_aggregated_status()
        .filter(pk=item.appointment_id)
        .only("pk")
        .first()
    )

    status_obj = getattr(item, "status", None) or getattr(result, "status", None)
    status_label = getattr(status_obj, "name", "") or status_code.title()
    status_code_resolved = getattr(status_obj, "code", "") or status_code

    if status_code == "CANCELLED" and notify:
        send_item_cancellation_email.delay(str(item.pk), reason=reason)
    elif status_code == "CONFIRMED" and payload.get("trigger_confirmation", False):
        send_item_confirmation_email.delay(str(item.pk))

    return JsonResponse({
        "ok": True,
        "item": {
            "id": str(item.pk),
            "status": {
                "code": status_code_resolved,
                "label": status_label,
            },
        },
        "appointment": {
            "id": str(item.appointment_id),
            "aggregated_status": {
                "code": getattr(appointment, "aggregated_status_code", ""),
                "label": getattr(appointment, "aggregated_status", ""),
            },
        },
    })


@staff_member_required
@require_POST
@csrf_protect
def admin_item_reschedule(request, item_id):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON payload"}, status=400)

    start_iso = payload.get("start_time")
    if not start_iso:
        return JsonResponse({"error": "start_time required"}, status=400)

    try:
        new_start = parse_datetime(start_iso) or _tz_aware(datetime.fromisoformat(start_iso))
        if not timezone.is_aware(new_start):
            new_start = _tz_aware(new_start)
    except Exception:
        return JsonResponse({"error": "invalid start_time"}, status=400)

    item = _fetch_admin_item(item_id)
    if not item:
        return JsonResponse({"error": "Item not found"}, status=404)

    master_id = payload.get("master")
    if master_id:
        new_master = get_object_or_404(MasterProfile, pk=master_id)
        if not ServiceMaster.objects.filter(service=item.service, master=new_master).exists():
            return JsonResponse({"error": "master can't perform this service"}, status=400)
        item.master = new_master

    item.start_time = new_start

    try:
        item.full_clean()
    except ValidationError as exc:
        return JsonResponse({"error": exc.message_dict}, status=400)

    with transaction.atomic():
        update_fields = {"start_time", "end_time", "room"}
        if master_id:
            update_fields.add("master")
        item.save(update_fields=sorted(update_fields))
        appointment = item.appointment
        appointment.sync_start_time_from_items(save=True)
        appointment.recompute_totals(save=True)
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            status=_status("Rescheduled"),
            set_by=request.user.userprofile,
        )

    appointment = (
        Appointment.objects.with_aggregated_status()
        .filter(pk=item.appointment_id)
        .only("pk", "start_time")
        .first()
    )

    def _master_display(appt):
        master_obj = getattr(appt, "master", None)
        if not master_obj:
            return ""
        profile = getattr(master_obj, "user", None)
        user_obj = getattr(profile, "user", None) or profile
        if not user_obj:
            return ""
        full_name = getattr(user_obj, "get_full_name", lambda: "")()
        username = getattr(user_obj, "username", "")
        return full_name or username or ""

    item.refresh_from_db()

    return JsonResponse({
        "ok": True,
        "item": {
            "id": str(item.pk),
            "start_time": item.start_time.isoformat(),
            "master_id": str(item.master_id) if item.master_id else "",
        },
        "appointment": {
            "id": str(item.appointment_id),
            "start_time": appointment.start_time.isoformat() if appointment else "",
            "master": _master_display(appointment) if appointment else "",
            "aggregated_status": {
                "code": getattr(appointment, "aggregated_status_code", ""),
                "label": getattr(appointment, "aggregated_status", ""),
            },
        },
    })

@login_required
@require_POST
@csrf_protect
def api_appointment_cancel(request, appt_id):
    appt = get_object_or_404(
        Appointment.objects.select_related("client").prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related("service", "master__user").order_by("start_time"),
            )
        ),
        pk=appt_id,
    )
    # Legacy clients can call this endpoint; staff always allowed.
    if not (request.user.is_staff or appt.client_id == request.user.userprofile.id):
        return HttpResponseForbidden("not allowed")

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        payload = {}

    item_id = payload.get("item_id")
    reason_text = payload.get("reason") or payload.get("note")
    reason_id = payload.get("reason_id")
    reason_obj = CancellationReason.objects.filter(pk=reason_id).first() if reason_id else None
    set_by_user_id = getattr(request.user, "id", None)

    def _aggregated_payload() -> dict[str, str]:
        row = (
            Appointment.objects.with_aggregated_status()
            .filter(pk=appt.pk)
            .values("_aggregated_status_code", "_aggregated_status_label")
            .first()
        )
        if not row:
            return {"code": "", "label": ""}
        return {"code": row["_aggregated_status_code"], "label": row["_aggregated_status_label"]}

    if item_id:
        item = (
            appt.items.select_related("service", "master", "status")
            .filter(pk=item_id)
            .first()
        )
        if not item:
            return JsonResponse({"error": "item not found"}, status=404)
        result = record_item_status(
            item,
            "CANCELLED",
            set_by_user_id=set_by_user_id,
            note=reason_text,
        )
        send_item_cancellation_email.delay(str(item.pk), reason=reason_text)
        aggregated_status = _aggregated_payload()
        item_status = {"code": result.status.code, "label": result.status.name}
        return JsonResponse(
            {
                "ok": True,
                "appointment_id": str(appt.pk),
                "item_id": str(item.pk),
                "item_status": item_status,
                "appointment_aggregated_status": aggregated_status,
            }
        )

    # DEPRECATED: appointment-level cancellation path. Applies to all active items.
    cancellable_items = list(
        appt.items.with_current_status().select_related("service", "status")
    )
    updated_items: list[str] = []
    for candidate in cancellable_items:
        current_code = (
            (candidate.current_status_code or "")
            or (getattr(getattr(candidate, "status", None), "code", ""))
        ).upper()
        if current_code == "CANCELLED":
            continue
        record_item_status(
            candidate,
            "CANCELLED",
            set_by_user_id=set_by_user_id,
            note=reason_text,
        )
        updated_items.append(str(candidate.pk))
        send_item_cancellation_email.delay(str(candidate.pk), reason=reason_text)

    if updated_items:
        with transaction.atomic():
            AppointmentStatusHistory.objects.create(
                appointment=appt,
                status=_status("Cancelled"),
                set_by=request.user.userprofile,
                cancellation_reason=reason_obj,
            )

    aggregated_status = _aggregated_payload()
    return JsonResponse(
        {
            "ok": True,
            "appointment_id": str(appt.pk),
            "item_ids": updated_items,
            "item_status": {"code": "CANCELLED", "label": "Cancelled"},
            "appointment_aggregated_status": aggregated_status,
            "deprecated": True,
        }
    )

@login_required
@require_POST
@csrf_protect
def api_appointment_reschedule(request, appt_id):
    """
    JSON: { "start_time": "<ISO8601>", "master": <user_id optional>, "item_id": <uuid optional> }
    """
    appt = get_object_or_404(
        Appointment.objects.select_related("client").prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related("service", "master__user").order_by("start_time"),
            )
        ),
        pk=appt_id,
    )
    if not (request.user.is_staff or appt.client_id == request.user.userprofile.id):
        return HttpResponseForbidden("not allowed")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("invalid json")

    start_iso = payload.get("start_time")
    if not start_iso:
        return HttpResponseBadRequest("start_time required")

    try:
        new_start = parse_datetime(start_iso) or _tz_aware(datetime.fromisoformat(start_iso))
        if not timezone.is_aware(new_start):
            new_start = _tz_aware(new_start)
    except Exception:
        return HttpResponseBadRequest("invalid start_time")

    item_id = payload.get("item_id")
    legacy_mode = False
    if item_id:
        item = (
            appt.items.select_related("service", "master")
            .filter(pk=item_id)
            .first()
        )
        if not item:
            return JsonResponse({"error": "item not found"}, status=404)
    else:
        # DEPRECATED: fallback to the primary appointment item.
        item = appt.primary_item
        if not item:
            return HttpResponseBadRequest("appointment has no items")
        legacy_mode = True

    master_id = payload.get("master")
    if master_id:
        new_master = get_object_or_404(MasterProfile, pk=master_id)
        if not ServiceMaster.objects.filter(service=item.service, master=new_master).exists():
            return HttpResponseBadRequest("master can't perform this service")
        item.master = new_master

    item.start_time = new_start
    computed_end = getattr(item, "compute_end_time", None)
    if callable(computed_end):
        end_val = computed_end()
        if end_val is not None:
            item.end_time = end_val

    item.full_clean()
    with transaction.atomic():
        item.save()
        appt.sync_start_time_from_items(save=True)
        appt.recompute_totals(save=True)
        AppointmentStatusHistory.objects.create(
            appointment=appt,
            status=_status("Rescheduled"),
            set_by=request.user.userprofile,
        )

    def _aggregated_payload() -> dict[str, str]:
        row = (
            Appointment.objects.with_aggregated_status()
            .filter(pk=appt.pk)
            .values("_aggregated_status_code", "_aggregated_status_label", "start_time")
            .first()
        )
        if not row:
            return {"code": "", "label": ""}
        appt.__dict__["start_time"] = row.get("start_time") or appt.start_time
        return {"code": row["_aggregated_status_code"], "label": row["_aggregated_status_label"]}

    item.refresh_from_db()

    status_obj = getattr(item, "status", None)
    status_code = (getattr(status_obj, "code", "") or "").upper() or "BOOKED"
    status_label = getattr(status_obj, "name", None) or status_code.title()
    item_status = {"code": status_code, "label": status_label}
    aggregated_status = _aggregated_payload()

    appt_master = getattr(appt, "master", None)
    master_display = ""
    if appt_master:
        profile = getattr(appt_master, "user", None)
        user_obj = getattr(profile, "user", None) or profile
        if user_obj:
            full_name = getattr(user_obj, "get_full_name", lambda: "")()
            username = getattr(user_obj, "username", "")
            master_display = full_name or username or ""

    return JsonResponse({
        "ok": True,
        "appointment_id": str(appt.pk),
        "item_id": str(item.pk),
        "item": {
            "id": str(item.pk),
            "start_time": item.start_time.isoformat(),
            "master_id": str(item.master_id) if item.master_id else "",
        },
        "item_status": item_status,
        "appointment": {
            "id": str(appt.pk),
            "start_time": appt.start_time.isoformat() if appt.start_time else "",
            "master": master_display,
            "aggregated_status": {
                "code": aggregated_status["code"],
                "label": aggregated_status["label"],
            },
        },
        "appointment_aggregated_status": aggregated_status,
        "deprecated": legacy_mode,
    })

@require_GET
def service_search(request):
    q = (request.GET.get('q') or '').strip()
    cat = request.GET.get('cat') or ''
    qs = (
        Service.objects.filter(is_active=True)
        .select_related('category')
        .prefetch_related(
            Prefetch(
                "pre_appointment_forms",
                queryset=ClientIntakeForm.objects.filter(is_active=True),
            )
        )
    )

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if cat:
        qs = qs.filter(category_id=cat)

    qs = qs.order_by('name')[:60]  # ограничим выдачу

    results = []
    for s in qs:
        disc = s.get_active_discount()
        price = str(s.get_discounted_price()) if disc else str(s.base_price)
        image_url = s.card_image_url
        if image_url:
            image_url = request.build_absolute_uri(image_url)
        results.append({
            "id": str(s.id),
            "name": s.name,
            "category": s.category.name if s.category_id else "",
            "description": (s.description or "")[:280],
            "base_price": str(s.base_price),
            "price": price,
            "discount_percent": disc.discount_percent if disc else None,
            "duration_min": s.duration_min,
            "image": image_url,
            "image_alt": s.card_image_alt,
            "forms": [
                {
                    "id": str(form.id),
                    "name": form.name,
                    "slug": form.slug,
                    "description": form.description,
                }
                for form in s.active_forms()
            ],
        })
    return JsonResponse({"results": results})

@require_GET
@staff_member_required
def service_price(request, pk):
    # pk — UUID (строка)
    try:
        s = Service.objects.get(pk=pk)
    except Service.DoesNotExist:
        raise Http404
    return JsonResponse({"id": str(s.pk), "base_price": str(s.base_price)})

@staff_member_required
def service_promocodes_api(request, service_id: str):
    if request.method != "GET":
        raise Http404()

    now = timezone.now().date()
    qs = PromoCode.objects.filter(
        applicable_services__id=service_id,
        active=True,
        start_date__lte=now,
        end_date__gte=now,
    ).distinct().order_by("code")

    data = [
        {
            "id": str(pc.pk),
            "code": pc.code,
            "discount_percent": pc.discount_percent,
        }
        for pc in qs
    ]
    return JsonResponse(data, safe=False)


@staff_member_required
@csrf_protect
def payment_refund_view(request, pk):
    """
    Render and process the admin refund workflow for a specific payment.
    """
    if not request.user.has_perm("core.change_payment"):
        raise PermissionDenied

    payment = get_object_or_404(
        Payment.objects.select_related("appointment", "method"),
        pk=pk,
    )

    if not payment.appointment_id:
        messages.error(request, "This payment is not linked to an appointment.")
        return redirect("admin:core_payment_change", payment.pk)

    items_qs = AppointmentItem.objects.select_related("service", "master__user").order_by("start_time")
    product_sales_qs = ProductSale.objects.select_related("product").order_by("sold_at")
    succeeded_payments_qs = (
        Payment.objects.filter(status__iexact="succeeded")
        .select_related("method")
        .order_by("created_at")
    )
    appointment = (
        Appointment.objects.filter(pk=payment.appointment_id)
        .select_related("client__user")
        .prefetch_related(
            Prefetch("items", queryset=items_qs),
            Prefetch("product_sales", queryset=product_sales_qs),
            Prefetch("payments", queryset=succeeded_payments_qs),
        )
        .first()
    )
    if not appointment:
        messages.error(request, "Appointment not found for this payment.")
        return redirect("admin:core_payment_change", payment.pk)

    payment.appointment = appointment

    def _quantize(amount: Decimal | None) -> Decimal:
        if amount is None:
            return Decimal("0.00")
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        return amount.quantize(Decimal("0.01"))

    try:
        pricing = compute_appointment_pricing(appointment)
    except PricingComputationError:
        pricing = None

    default_currency = (getattr(settings, "STRIPE_CURRENCY", "cad") or "cad").lower()
    fallback_symbol = "CA$" if default_currency == "cad" else f"{default_currency.upper()} "
    currency_symbol = pricing.get("currency_symbol") if pricing else None
    if not currency_symbol:
        currency_symbol = fallback_symbol

    items_data: list[dict[str, object]] = []
    if pricing:
        for entry in pricing.get("items", []):
            amount = _quantize(entry.get("total_with_tax"))
            amount_minor = RefundService._to_minor_units(amount)
            master_label = entry.get("master") or ""
            items_data.append(
                {
                    "id": str(entry.get("id") or ""),
                    "name": entry.get("name") or "",
                    "master": master_label,
                    "amount": amount,
                    "amount_minor": amount_minor,
                    "display": f"{currency_symbol}{amount:.2f}",
                }
            )
    else:
        for item in appointment.items.all():
            total = _quantize(
                (item.final_price or Decimal("0.00")) + (item.tax_amount or Decimal("0.00"))
            )
            amount_minor = RefundService._to_minor_units(total)
            master = getattr(item, "master", None)
            master_name = ""
            if master:
                master_name = getattr(master, "display_name", "") or ""
                if not master_name:
                    user = getattr(master, "user", None)
                    if user:
                        master_name = user.get_full_name() or user.username
            items_data.append(
                {
                    "id": str(item.pk),
                    "name": getattr(getattr(item, "service", None), "name", ""),
                    "master": master_name,
                    "amount": total,
                    "amount_minor": amount_minor,
                    "display": f"{currency_symbol}{total:.2f}",
                }
            )

    products_data: list[dict[str, object]] = []
    if pricing:
        for entry in pricing.get("product_sales", []):
            product_total = _quantize(entry.get("total_amount"))
            tax_amount = _quantize(entry.get("tax_amount"))
            combined = _quantize(product_total + tax_amount)
            amount_minor = RefundService._to_minor_units(combined)
            products_data.append(
                {
                    "id": str(entry.get("id") or ""),
                    "name": entry.get("name") or "",
                    "quantity": entry.get("quantity") or 0,
                    "amount": combined,
                    "amount_minor": amount_minor,
                    "display": f"{currency_symbol}{combined:.2f}",
                }
            )
    else:
        for sale in appointment.product_sales.all():
            combined = _quantize(
                (sale.total_amount or Decimal("0.00")) + (sale.tax_amount or Decimal("0.00"))
            )
            amount_minor = RefundService._to_minor_units(combined)
            products_data.append(
                {
                    "id": str(sale.pk),
                    "name": getattr(getattr(sale, "product", None), "name", ""),
                    "quantity": getattr(sale, "quantity", 0),
                    "amount": combined,
                    "amount_minor": amount_minor,
                    "display": f"{currency_symbol}{combined:.2f}",
                }
            )

    item_choices = [(entry["id"], entry["id"]) for entry in items_data if entry["id"]]
    product_choices = [(entry["id"], entry["id"]) for entry in products_data if entry["id"]]

    succeeded_payments = list(appointment.payments.all())
    total_paid_decimal = payment_services.get_total_received_for_appointment(appointment)
    already_refunded_decimal = sum(
        (_quantize(p.amount_refunded) for p in succeeded_payments),
        Decimal("0.00"),
    )
    already_refunded_decimal = _quantize(already_refunded_decimal)
    available_decimal = total_paid_decimal - already_refunded_decimal
    if available_decimal < Decimal("0.00"):
        available_decimal = Decimal("0.00")

    totals_section = (pricing or {}).get("totals") if pricing else None
    if totals_section:
        grand_total = _quantize(totals_section.get("grand_total"))
    else:
        grand_total = _quantize(getattr(appointment, "total_with_tax", Decimal("0.00")))

    max_refund_minor = RefundService._to_minor_units(available_decimal)

    form_kwargs = {
        "max_refund_minor": max_refund_minor,
        "item_choices": item_choices,
        "product_choices": product_choices,
    }

    if request.method == "POST":
        form = PaymentRefundForm(request.POST, **form_kwargs)
        selected_item_ids = set(request.POST.getlist("item_ids"))
        selected_product_ids = set(request.POST.getlist("product_ids"))
        if form.is_valid():
            requested_minor = form.cleaned_data["amount_minor"]
            try:
                # CHANGED: log refund workflow steps instead of printing to stdout.
                logger.debug(
                    "Initiating refund %s",
                    {
                        "payment_id": str(payment.pk),
                        "appointment_id": str(appointment.pk),
                        "requested_minor": requested_minor,
                        "selected_items": list(selected_item_ids),
                        "selected_products": list(selected_product_ids),
                    },
                )
                allocations = RefundService.allocate_refund_for_appointment(
                    appointment,
                    requested_minor,
                )
                logger.debug(
                    "Refund allocations resolved %s",
                    [
                        {
                            "payment_id": str(allocation.payment.pk),
                            "available_minor": RefundService._available_minor(allocation.payment),
                            "allocated_minor": allocation.amount_minor,
                        }
                        for allocation in allocations
                    ],
                )
                stripe_ids = RefundService.perform_refund(allocations, actor=request.user)
            except RefundError as exc:
                logger.debug("RefundError encountered %s", exc, exc_info=exc)
                form.add_error(None, str(exc))
            else:
                amount = form.cleaned_data["amount_to_refund"]
                payment_url = reverse("admin:core_payment_change", args=[payment.pk])
                appointment_url = reverse("admin:core_appointment_change", args=[appointment.pk])
                links_html = format_html(
                    '<a href="{}">Payment</a> · <a href="{}">Appointment</a>',
                    payment_url,
                    appointment_url,
                )
                if stripe_ids:
                    stripe_html = format_html(" Stripe refund ID(s): {}", ", ".join(stripe_ids))
                else:
                    stripe_html = ""
                amount_display = format_html(
                    "{}{}",
                    currency_symbol,
                    f"{amount:.2f}",
                )
                messages.success(
                    request,
                    format_html(
                        "Refund of {} initiated. {}{}",
                        amount_display,
                        links_html,
                        stripe_html,
                    ),
                )
                logger.debug(
                    "Refund complete %s",
                    {
                        "payment_id": str(payment.pk),
                        "appointment_id": str(appointment.pk),
                        "refunded_minor": requested_minor,
                        "stripe_refunds": stripe_ids,
                    },
                )
                return redirect("admin-payment-refund", pk=payment.pk)
    else:
        form = PaymentRefundForm(
            initial={"amount_to_refund": Decimal("0.00")},
            **form_kwargs,
        )
        selected_item_ids = set()
        selected_product_ids = set()

    context = {
        "form": form,
        "payment": payment,
        "appointment": appointment,
        "items": items_data,
        "products": products_data,
        "currency_symbol": currency_symbol,
        "summary": {
            "grand_total": grand_total,
            "total_paid": total_paid_decimal,
            "already_refunded": already_refunded_decimal,
            "available": available_decimal,
        },
        "selected_item_ids": selected_item_ids,
        "selected_product_ids": selected_product_ids,
        "max_refund_minor": max_refund_minor,
    }
    return render(request, "admin/payment_refund.html", context)

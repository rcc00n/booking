# core/views.py
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.forms import inlineformset_factory
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Prefetch, Q
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
import json
import stripe

from core.models import (
    Appointment, ServiceCategory, Service, PromoCode,
    AppointmentStatusHistory, MasterProfile, UserProfile, CancellationReason,
    AppointmentItem, BookingCart, BookingCartItem, Payment, ClientIntakeForm,
)
from core.services.booking import (
    get_available_slots,
    get_service_masters,
    get_or_create_status,
    get_default_payment_status,
    _tz_aware,
    create_appointment_from_cart_items,
)
from accounts.utils import build_autofill_defaults
from core.services import payments as payment_services
from core.services.pricing import compute_cart_pricing
from core.utils.fees import card_processing_fee

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

    masters_qs = [master_obj] if master_obj else list(get_service_masters(service))
    resp = {
        "service": {"id": str(service.pk), "name": service.name, "duration": service.duration_min},
        "date": date_str,
        "masters": []
    }
    for m in masters_qs:
        resp["masters"].append({
            "id": m.id,
            "name": m.user.get_full_name() or m.user.username,
            "slots": [s.isoformat() for s in slots_map.get(m.id, [])]
        })
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
    pre_fee_total = Decimal(appt.final_price or Decimal("0.00")) - Decimal(
        appt.card_processing_fee or Decimal("0.00")
    )
    if pre_fee_total < Decimal("0.00"):
        pre_fee_total = Decimal("0.00")
    else:
        pre_fee_total = pre_fee_total.quantize(Decimal("0.01"))

    card_fee = card_processing_fee(pre_fee_total)
    appt.apply_card_processing_fee = True
    appt.card_processing_fee = card_fee
    appt.final_price = (pre_fee_total + card_fee).quantize(Decimal("0.01"))
    appt.save(update_fields=["apply_card_processing_fee", "card_processing_fee", "final_price"])

    try:
        bundle = payment_services.create_or_update_terminal_intent(appt)
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
    # только владелец или staff

    if not (request.user.is_staff or appt.client_id == request.user.userprofile.id):
        return HttpResponseForbidden("not allowed")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        payload = {}

    reason_id = payload.get("reason_id")
    reason_obj = None
    if reason_id:
        reason_obj = CancellationReason.objects.filter(pk=reason_id).first()

    cancelled = _status("Cancelled")
    # уже отменена?
    if appt.appointmentstatushistory_set.filter(status=cancelled).exists():
        return JsonResponse({"ok": True, "already": True})

    with transaction.atomic():
        AppointmentStatusHistory.objects.create(
            appointment=appt,
            status=cancelled,
            set_by=request.user.userprofile,
            cancellation_reason=reason_obj,
        )
    return JsonResponse({"ok": True})

@login_required
@require_POST
@csrf_protect
def api_appointment_reschedule(request, appt_id):
    """
    JSON: { "start_time": "<ISO8601>", "master": <user_id optional> }
    Меняет время (и по желанию мастера) с валидацией Appointment.clean().
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

    # разбираем дату/время
    try:
        new_start = parse_datetime(start_iso) or _tz_aware(datetime.fromisoformat(start_iso))
        if not timezone.is_aware(new_start):
            new_start = _tz_aware(new_start)
    except Exception:
        return HttpResponseBadRequest("invalid start_time")

    # смена мастера (опционально)
    master_id = payload.get("master")
    primary_item = appt.primary_item
    if not primary_item:
        return HttpResponseBadRequest("appointment has no items")

    if master_id:
        new_master = get_object_or_404(MasterProfile, pk=master_id)
        # мастер должен уметь услугу
        if not ServiceMaster.objects.filter(service=primary_item.service, master=new_master).exists():
            return HttpResponseBadRequest("master can't perform this service")
        primary_item.master = new_master

    primary_item.start_time = new_start

    # валидация пересечений/комнат/отпусков
    primary_item.full_clean()
    with transaction.atomic():
        primary_item.save()
        appt.sync_start_time_from_items(save=True)
        appt.recompute_totals(save=True)
        # история статусов
        AppointmentStatusHistory.objects.create(
            appointment=appt,
            status=_status("Rescheduled"),
            set_by=request.user.userprofile,
        )

    return JsonResponse({"ok": True, "appointment": {
        "id": str(appt.pk),
        "start_time": appt.start_time.isoformat(),
        "master": appt.master.user.get_full_name() or appt.master.user.username if appt.master else ""
    }})



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

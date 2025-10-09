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
    get_available_slots, get_service_masters,
    get_or_create_status, get_default_payment_status, _tz_aware,
    create_appointment_from_cart_items,
)
from core.services import payments as payment_services

def _build_catalog_context(request):
    """Общий конструктор контекста каталога."""
    q = (request.GET.get("q") or "").strip()
    cat = request.GET.get("cat") or ""

    services_qs = (
        Service.objects
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
    if cat:
        services_qs = services_qs.filter(category__id=cat)

    categories_qs = (
        ServiceCategory.objects.order_by("name")
        .prefetch_related(Prefetch("service_set", queryset=services_qs))
    )

    return {
        "categories": categories_qs,
        "filter_categories": ServiceCategory.objects.order_by("name"),
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


def _master_display(master: MasterProfile) -> str:
    if not master:
        return ""
    profile = getattr(master, "user", None)
    name = ""
    if profile and hasattr(profile, "get_full_name"):
        name = profile.get_full_name() or ""
    if not name:
        linked_user = getattr(profile, "user", None)
        if linked_user:
            name = linked_user.get_full_name() or linked_user.username
    return name


def _cart_payload(item: BookingCartItem) -> dict:
    master_label = _master_display(item.master)
    return {
        "id": item.id,
        "service": {
            "id": item.service.id,
            "name": item.service.name,
            "duration_min": item.service.duration_min,
            "extra_time_min": item.service.extra_time_min,
            "price": str(item.service.base_price),
        },
        "master": {
            "id": item.master.id,
            "name": master_label,
        } if item.master else None,
        "start_time": item.start_time.isoformat() if item.start_time else None,
    }


@login_required
@require_GET
def api_cart_summary(request):
    profile = _ensure_profile(request.user)
    cart = BookingCart.for_user(profile)
    items = list(cart.items.select_related("service", "master__user"))

    total_price = sum((it.service.base_price or 0) for it in items)
    total_duration = sum(((it.service.duration_min or 0) + (it.service.extra_time_min or 0)) for it in items)

    return JsonResponse({
        "items": [_cart_payload(it) for it in items],
        "count": len(items),
        "total_price": str(total_price),
        "total_duration_min": total_duration,
    })


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

    return JsonResponse({"ok": True, "item": _cart_payload(item)}, status=201)


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
def api_cart_checkout(request):
    profile = _ensure_profile(request.user)
    cart = BookingCart.for_user(profile)
    items = list(cart.items.select_related("service", "master__user"))

    if not items:
        return JsonResponse({"error": "cart is empty"}, status=400)

    try:
        appt = create_appointment_from_cart_items(profile=profile, items=items)
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

    try:
        bundle = payment_services.create_or_update_payment_intent(appt)
    except ImproperlyConfigured as cfg_err:
        return JsonResponse({"error": str(cfg_err)}, status=500)
    except stripe.error.StripeError as err:
        return JsonResponse({"error": getattr(err, "user_message", str(err))}, status=502)

    cart.clear()

    payment_payload = {
        "id": str(bundle.payment.id),
        "status": bundle.payment.status,
        "amount": str(bundle.payment.amount),
        "amount_received": str(bundle.payment.amount_received),
        "currency": bundle.payment.currency,
        "livemode": bundle.payment.livemode,
        "client_secret": getattr(bundle.intent, "client_secret", None) if bundle.intent else None,
        "payment_intent_id": getattr(bundle.intent, "id", None) if bundle.intent else bundle.payment.stripe_payment_intent_id,
        "publishable_key": settings.STRIPE_PUBLIC_KEY,
    }

    return JsonResponse({
        "ok": True,
        "appointment": {
            "id": str(appt.pk),
            "start_time": appt.start_time.isoformat() if appt.start_time else None,
            "items": [
                {
                    "service": it.service.name,
                    "master": _master_display(it.master),
                    "start_time": it.start_time.isoformat() if it.start_time else None,
                }
                for it in appt.items.select_related("service", "master__user")
            ],
        },
        "payment": payment_payload,
    }, status=201)


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
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=503)

    if not sig_header:
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    try:
        payment_services.handle_webhook_event(event)
    except (Payment.DoesNotExist, ValueError):
        return HttpResponse(status=202)

    return HttpResponse(status=200)
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
        Service.objects
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
        results.append({
            "id": str(s.id),
            "name": s.name,
            "category": s.category.name if s.category_id else "",
            "description": (s.description or "")[:280],
            "base_price": str(s.base_price),
            "price": price,
            "discount_percent": disc.discount_percent if disc else None,
            "duration_min": s.duration_min,
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

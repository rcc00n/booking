# core/views.py
from django.contrib.admin.views.decorators import staff_member_required
from django.forms import inlineformset_factory
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Prefetch, Q
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_protect
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from datetime import datetime
from django.core.exceptions import ValidationError
from django.db import transaction
import json

from core.models import (
    Appointment, ServiceCategory, Service, PromoCode,
    AppointmentStatusHistory, MasterProfile, UserProfile, CancellationReason,AppointmentItem
)
from core.services.booking import (
    get_available_slots, get_service_masters,
    get_or_create_status, get_default_payment_status, _tz_aware
)

def _build_catalog_context(request):
    """Общий конструктор контекста каталога."""
    q = (request.GET.get("q") or "").strip()
    cat = request.GET.get("cat") or ""

    services_qs = Service.objects.select_related("category").order_by("name")
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

# --- API: отмена/перенос записи ---
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, Http404
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
    qs = Service.objects.select_related('category')

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

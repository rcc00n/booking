# core/services/booking.py
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.db.models import Q, OuterRef, Subquery
from django.utils import timezone
from django.utils.timezone import make_aware, get_current_timezone

from core.models import (
    Service, ServiceMaster, CustomUserDisplay, Appointment,
    AppointmentItem,
    MasterAvailability, AppointmentStatus, AppointmentStatusHistory,
    PaymentStatus, MasterProfile,
)
from core.validators import validate_service_is_active
from django.db import transaction

Slot = Tuple[datetime, datetime]

def _tz_aware(dt: datetime) -> datetime:
    if timezone.is_aware(dt):
        return dt
    return make_aware(dt, get_current_timezone())

def _intervals_subtract(avail: Slot, blocks: List[Slot]) -> List[Slot]:
    """
    Вычитает блокировки (blocks) из доступного интервала avail,
    возвращает список свободных интервалов.
    """
    free = [avail]
    for b_start, b_end in sorted(blocks, key=lambda x: x[0]):
        next_free: List[Slot] = []
        for f_start, f_end in free:
            # нет пересечения
            if b_end <= f_start or b_start >= f_end:
                next_free.append((f_start, f_end))
                continue
            # обрезаем слева
            if b_start > f_start:
                next_free.append((f_start, b_start))
            # обрезаем справа
            if b_end < f_end:
                next_free.append((b_end, f_end))
        free = next_free
    return [(s, e) for s, e in free if e > s]

def _gen_slots_in_intervals(free_intervals: List[Slot], total_minutes: int, step_minutes: int = 15) -> List[datetime]:
    """
    Разбиваем свободные интервалы на слоты с шагом step_minutes так,
    чтобы целиком помещался отрезок длиной total_minutes.
    Возвращаем список стартов слотов (tz-aware).
    """
    out: List[datetime] = []
    step = timedelta(minutes=step_minutes)
    dur = timedelta(minutes=total_minutes)
    for s, e in free_intervals:
        start = s
        # выравниваем к ближайшему шагу
        if start.minute % step_minutes:
            align = step_minutes - (start.minute % step_minutes)
            start = start.replace(second=0, microsecond=0) + timedelta(minutes=align)
        while start + dur <= e:
            out.append(start)
            start += step
    return out

def _master_day_work_window(mp: MasterProfile, day: datetime) -> Slot:
    """
    Рабочее окно мастера на день (без учёта отпусков), tz-aware.
    """
    weekday = day.weekday()
    workday = mp.workdays.filter(weekday=weekday).first()
    if not workday or not workday.start_time or not workday.end_time:
        return None, None  # в этот день мастер не работает / расписание пустое

    ws = _tz_aware(datetime(day.year, day.month, day.day,
                            workday.start_time.hour, workday.start_time.minute))
    we = _tz_aware(datetime(day.year, day.month, day.day,
                            workday.end_time.hour, workday.end_time.minute))
    return ws, we

def _appointment_intervals(master: MasterProfile, day: datetime) -> List[Slot]:
    """
    Интервалы занятости по существующим записям мастера на указанную дату.
    Исключаем отменённые.
    """
    start_day = _tz_aware(datetime(day.year, day.month, day.day, 0, 0)) - timedelta(hours=3)
    end_day = start_day + timedelta(days=1, hours=3)

    # Последний статус записи для фильтра отменённых
    cancelled = AppointmentStatus.objects.filter(name__iexact="Cancelled").first()
    last_status_sq = (
        AppointmentStatusHistory.objects
        .filter(appointment_id=OuterRef("appointment_id"))
        .order_by("-set_at")
        .values("status_id")[:1]
    )

    qs = (
        AppointmentItem.objects
        .select_related("appointment", "service")
        .annotate(last_status=Subquery(last_status_sq))
        .filter(
            master=master,
            appointment__start_time__gte=start_day,
            appointment__start_time__lt=end_day,
        )
    )
    if cancelled:
        qs = qs.exclude(last_status=cancelled.id)

    blocks: List[Slot] = []
    for item in qs:
        base_start = item.start_time or getattr(item.appointment, "start_time", None)
        if not base_start:
            continue
        duration_min = int(getattr(item, "duration_min", 0) or 0)
        if not duration_min:
            duration_min = (item.service.duration_min or 0) + (item.service.extra_time_min or 0)
        dur = timedelta(minutes=duration_min)
        blocks.append((base_start, base_start + dur))
    return blocks


def _room_busy_intervals(room_ids: List[int], day: datetime) -> Dict[int, List[Slot]]:
    """
    Построить карту занятых интервалов по комнатам для указанной даты.
    """
    if not room_ids:
        return {}

    window_start = _tz_aware(datetime(day.year, day.month, day.day, 0, 0)) - timedelta(hours=3)
    window_end = window_start + timedelta(days=1, hours=3)

    latest_appt_status_sq = (
        AppointmentStatusHistory.objects.filter(appointment_id=OuterRef("appointment_id"))
        .order_by("-set_at", "-id")
        .values("status__name")[:1]
    )

    qs = (
        AppointmentItem.objects.with_current_status()
        .select_related("appointment", "service")
        .filter(
            room_id__in=room_ids,
            start_time__lt=window_end,
            start_time__gt=window_start - timedelta(hours=24),
        )
        .annotate(_latest_appt_status=Subquery(latest_appt_status_sq))
        .exclude(current_status_code__iexact="CANCELLED")
        .exclude(_latest_appt_status__iexact="Cancelled")
    )

    busy: Dict[int, List[Slot]] = {room_id: [] for room_id in room_ids}
    for item in qs:
        if item.room_id is None:
            continue
        base_start = item.start_time or getattr(item.appointment, "start_time", None)
        if not base_start:
            continue
        duration_min = int(getattr(item, "duration_min", 0) or 0)
        if not duration_min:
            service = getattr(item, "service", None)
            duration_min = int(
                (getattr(service, "duration_min", 0) or 0) + (getattr(service, "extra_time_min", 0) or 0)
            )
        busy_end = base_start + timedelta(minutes=duration_min)
        if busy_end <= window_start or base_start >= window_end:
            continue
        busy.setdefault(item.room_id, []).append((base_start, busy_end))

    for entries in busy.values():
        entries.sort(key=lambda slot: slot[0])
    return busy


def _room_has_capacity(room_blocks: Dict[int, List[Slot]], room_ids: List[int], start: datetime, end: datetime) -> bool:
    """
    Проверяем, достаточно ли свободных комнат для интервала [start, end).
    """
    for room_id in room_ids:
        overlaps = False
        for busy_start, busy_end in room_blocks.get(room_id, []):
            if start < busy_end and end > busy_start:
                overlaps = True
                break
        if not overlaps:
            return True
    return False

def _timeoff_intervals(master: MasterProfile, day: datetime) -> List[Slot]:
    """
    Интервалы отпусков/перерывов мастера на дату.
    """
    start_day = _tz_aware(datetime(day.year, day.month, day.day, 0, 0))
    end_day = start_day + timedelta(days=1)
    qs = MasterAvailability.objects.filter(
        master=master,
        start_time__lt=end_day,
        end_time__gt=start_day
    )
    return [(p.start_time, p.end_time) for p in qs]

def get_service_masters(service: Service):
    """
    Список мастеров, которые умеют выполнять услугу.
    """

    master_ids = ServiceMaster.objects.filter(service=service).values_list("master_id", flat=True)

    return MasterProfile.objects.filter(id__in=master_ids).select_related("user")

def get_available_slots(
    service: Service,
    day: datetime,
    master: Optional[MasterProfile] = None,
    step_minutes: int = 15
) -> Dict[int, List[datetime]]:
    """
    Возвращает словарь {master_id: [datetime слот-старты]} на дату day.
    Учитывает рабочее окно, существующие записи и периоды недоступности.
    """
    total_minutes = (service.duration_min or 0) + (service.extra_time_min or 0)

    day = day.astimezone(get_current_timezone())
    masters = [master] if master else list(get_service_masters(service))
    if not masters:
        return {}

    allowed_room_ids = list(dict.fromkeys(service.allowed_rooms.values_list("pk", flat=True)))
    result: Dict[int, List[datetime]] = {m.id: [] for m in masters}
    if not allowed_room_ids:
        return result
    if total_minutes <= 0:
        return result

    requires_room_check = bool(allowed_room_ids)
    room_blocks = _room_busy_intervals(allowed_room_ids, day) if requires_room_check else {}
    duration_delta = timedelta(minutes=total_minutes)

    for m in masters:
    #TODO change master work_s work_e accordingly to each day. It is the same for all days now. Needs to be changed to each day separately

        work_s, work_e = _master_day_work_window(m, day)
        if not work_s or not work_e or work_s >= work_e:
            continue

        blocks = _appointment_intervals(m, day) + _timeoff_intervals(m, day)

        free = _intervals_subtract((work_s, work_e), blocks)
        raw_slots = _gen_slots_in_intervals(free, total_minutes=total_minutes, step_minutes=step_minutes)

        filtered_slots: List[datetime] = []
        for start in raw_slots:
            end = start + duration_delta
            if not requires_room_check or _room_has_capacity(room_blocks, allowed_room_ids, start, end):
                filtered_slots.append(start)

        result[m.id] = filtered_slots
    return result

def get_or_create_status(name: str) -> AppointmentStatus:
    # Multiple legacy statuses can share the same label; reuse the oldest match.
    status = (
        AppointmentStatus.objects.filter(name__iexact=name)
        .order_by("pk")
        .first()
    )
    if status:
        return status
    return AppointmentStatus.objects.create(name=name)

def get_default_payment_status() -> Optional[PaymentStatus]:
    return (
        PaymentStatus.objects.filter(name__iexact="Pending").first()
        or PaymentStatus.objects.first()
    )


def create_appointment_from_cart_items(
    *,
    profile,
    items,
) -> Appointment:
    """
    Build a multi-service appointment from cart items.
    """
    items = list(items)
    if not items:
        raise ValueError("Cart is empty")
    for cart_item in items:
        service = getattr(cart_item, "service", None)
        if service is None and getattr(cart_item, "service_id", None):
            service = Service.objects.filter(pk=cart_item.service_id).only("is_active").first()
        validate_service_is_active(service)

    starts = [it.start_time for it in items if it.start_time]
    primary_start = min(starts) if starts else None

    pay_status = get_default_payment_status()

    with transaction.atomic():
        appt = Appointment(
            client=profile,
            start_time=primary_start,
            payment_status=pay_status if pay_status else None,
        )
        appt.full_clean()
        appt.save()

        # Client-side appointments (cart checkout) should include card fees.
        appt.apply_card_processing_fee = True
        appt.card_processing_fee = Decimal("0.00")

        now_ts = timezone.now()
        user = getattr(profile, "user", None)
        user_id = getattr(user, "id", None)

        for cart_item in items:
            item = AppointmentItem(
                appointment=appt,
                service=cart_item.service,
                master=cart_item.master,
                start_time=cart_item.start_time,
            )
            item._initial_status_code = "CONFIRMED"
            item._initial_status_user_id = user_id
            item._initial_status_timestamp = now_ts
            item._initial_status_note = "checkout-confirmed"
            item.full_clean()
            item.save()

        appt.sync_start_time_from_items(save=True)
        appt.recompute_totals(save=True)

        initial_status = get_or_create_status("Confirmed")
        AppointmentStatusHistory.objects.create(
            appointment=appt,
            status=initial_status,
            set_by=profile,
        )

    return appt

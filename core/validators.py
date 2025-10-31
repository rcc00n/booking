# core/validators.py
import re
from typing import Optional

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.apps import apps
from .models import *

PHONE_RE = re.compile(r"^\+?\d{10,15}$")      # «+» необязателен, 10-15 цифр
_CANADA_PC_PART = r"[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]"
ALBERTA_POSTAL_RE = re.compile(rf"^T\d{_CANADA_PC_PART[1:]}[ ]?\d[ABCEGHJ-NPRSTV-Z]\d$", re.IGNORECASE)

def clean_phone(value):
    """Проверяет, что телефон соответствует международному формату."""
    if not PHONE_RE.fullmatch(value):
        raise ValidationError("Введите телефон в формате +79991234567")
    return value


def clean_ab_postal_code(value: str) -> str:
    if not value:
        return ""
    raw = value.strip().upper().replace(" ", "")
    # допустим только 6 символов и первая — T
    if len(raw) != 6 or raw[0] != "T":
        raise ValidationError("Enter a valid Alberta postal code (e.g. T2X1A1).")
    # строгая проверка канадского формата
    if not re.match(r"^[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]\d$", raw):
        raise ValidationError("Enter a valid Alberta postal code (e.g. T2X1A1).")
    return raw


# ──────────────────────────────────────────────────────────────────────────────
# Полезные валидаторы для Item
# ──────────────────────────────────────────────────────────────────────────────

def validate_service_is_active(service) -> None:
    if not service:
        return
    if hasattr(service, "is_active") and not service.is_active:
        raise ValidationError(_("Selected service is inactive."))


def validate_quantity_positive(qty: Optional[int]) -> None:
    if qty is None:
        return
    if qty <= 0:
        raise ValidationError(_("Количество должно быть положительным."))


def validate_master_can_provide_service(master, service) -> None:
    if not master or not service or ServiceMaster is None:
        return
    if not ServiceMaster.objects.filter(master=master, service=service).exists():
        raise ValidationError(_("Выбранный мастер не оказывает эту услугу."))


def validate_discount_vs_promocode_rule(service_discount, promocode, *, allow_override: bool) -> None:
    """
    В одной позиции можно выбрать ИЛИ скидку услуги, ИЛИ промокод.
    Одновременное применение допустимо только при allow_override=True (админ).
    """
    if service_discount and promocode and not allow_override:
        raise ValidationError(_("Нельзя одновременно применять скидку услуги и промокод для одной позиции."))


# ──────────────────────────────────────────────────────────────────────────────
# Комплексные проверки Appointment
# ──────────────────────────────────────────────────────────────────────────────

def _items_manager(appt):
    return getattr(appt, "appointmentitem_set", None) or getattr(appt, "items", None)

def validate_appointment_has_items_on_save(appt) -> None:
    mgr = _items_manager(appt)
    count = mgr.count() if mgr is not None else 0
    if count == 0:
        raise ValidationError(_("У приёма должна быть хотя бы одна позиция услуги."))


def validate_no_duplicate_services_in_items(appt) -> None:
    """
    Оставьте, если дубли услуг нежелательны. Иначе — удалите.
    """
    mgr = _items_manager(appt)
    if not mgr:
        return
    ids = list(mgr.values_list("service_id", flat=True))
    if len(ids) != len(set(ids)):
        raise ValidationError(_("В приёме обнаружены дублирующиеся услуги. Объедините их количеством."))


def validate_items_prices_nonnegative(appt) -> None:
    mgr = _items_manager(appt)
    if not mgr:
        return
    if mgr.filter(final_price__lt=Decimal("0")).exists():
        raise ValidationError(_("Обнаружена позиция с отрицательной итоговой ценой."))


def validate_no_time_overlap_for_same_master(appt) -> None:
    """
    Нет пересечений по времени у одного и того же мастера в рамках одного Appointment.
    Параллельные услуги у разных мастеров — допустимы.
    Требует у позиций полей: start_time и service.duration_min (переименуйте при нужде).
    """
    from datetime import timedelta

    mgr = _items_manager(appt)
    if not mgr:
        return

    # Собираем интервалы по мастерам
    per_master = {}
    for it in mgr.all():
        if hasattr(it, "validation_enabled") and not getattr(it, "validation_enabled", True):
            continue
        master_id = getattr(it.master, "pk", None)
        start = getattr(it, "start_time", None)
        dur_min = getattr(getattr(it, "service", None), "duration_min", None)
        if not (master_id and start and dur_min):
            # если не можем посчитать — пропускаем строгую проверку
            # (позиции без времени/длительности будут валидироваться позже, когда данные полные)
            continue
        end = start + timedelta(minutes=int(dur_min))
        per_master.setdefault(master_id, []).append((start, end))

    # Проверка пересечений внутри каждого мастера
    for master_id, intervals in per_master.items():
        intervals.sort(key=lambda x: x[0])
        prev_start, prev_end = intervals[0]
        for cur_start, cur_end in intervals[1:]:
            if cur_start < prev_end:
                raise ValidationError(_("Найдены пересечения по времени у одного мастера внутри приёма."))
            prev_start, prev_end = cur_start, cur_end


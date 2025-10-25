# core/signals.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Any, List, Tuple
import logging
from decimal import Decimal

from .utils.sms import send_sms
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import pre_save, post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.timezone import localtime
from .tasks import send_cancellation_email
from .models import (
    Appointment,
    AppointmentStatusHistory,
    Notification,
    AppointmentItem,
    AppointmentItemPromoCode,
    UserProfile,
    PaymentStatus,
    Payment,
    ClientIntakeForm,
)
from core.tasks import generate_payment_receipt_task, email_payment_receipt_task
from core.services.payments import get_total_received_for_appointment
from core.services.intake_assignments import (
    ensure_universal_assignments_for_form,
    ensure_universal_assignments_for_profile,
)
from django.db import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Email utility (локальная, чтобы избежать циклических импортов)
# ──────────────────────────────────────────────────────────────────────────────

def _send_email(to_email: str, subject: str, text: str, html: str, *, tag: str | None = None):
    if not to_email:
        return
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    msg.attach_alternative(html, "text/html")
    try:
        if tag:
            msg.tags = [tag]   # поддерживает Anymail/Sendgrid, если есть
    except Exception:
        pass
    try:
        msg.send()
    except Exception as exc:  # noqa: BLE001 - failing email must not block business flow
        logger.warning("Failed to send transactional email (tag=%s, to=%s): %s", tag, to_email, exc, exc_info=exc)


def _notify_once(appointment_id, user_profile, *, channel="email", message: str):
    """
    Не плодим дубликаты из‑за ограничений:
        UniqueConstraint(fields=["appointment", "kind", "channel"], name="uniq_notification_per_kind_channel")
    Делаем единственную запись kind="other" на appointment+channel и обновляем/перезаписываем message.
    """
    # Для null‑safe фильтрации используем id:
    notif, created = Notification.objects.get_or_create(
        appointment_id=appointment_id,
        kind=Notification.OTHER,
        channel=channel,
        defaults={
            "user": user_profile,
            "message": message,
        },
    )
    if not created:
        # Перезаписываем сообщение и помечаем «послано сейчас» для читабельных логов
        notif.message = message
        notif.sent_at = timezone.now()
        notif.user = user_profile or notif.user
        notif.save(update_fields=["message", "sent_at", "user"])


def _safe_assignments_call(func, *args, **kwargs):
    """
    Guard assignment helpers so migrations do not fail when tables are missing.
    """
    try:
        return func(*args, **kwargs)
    except (OperationalError, ProgrammingError):
        logger.debug("Skipping intake assignment sync; tables not ready yet.")
        return 0

# 4) Хелпер: список позиций (услуга + мастер + время)
def _items_summary_lines(appt: Appointment) -> list[str]:
    lines = []
    qs = appt.items.select_related("service", "master__user").order_by("start_time")
    for it in qs:
        s = localtime(it.start_time).strftime("%d %b %Y, %H:%M")
        master_name = it.master.user.get_full_name() or it.master.user.user.username
        lines.append(f"• {it.service.name} with {master_name} at {s}")
    return lines

def _short_labels(appt: Appointment) -> tuple[str, str]:
    """Для тем/смс: если 1 позиция — точные названия, иначе агрегированные."""
    items = list(appt.items.select_related("service", "master__user"))
    if not items:
        return "", ""
    if len(items) == 1:
        it = items[0]
        s_name = it.service.name
        master_profile = getattr(it.master, "user", None)
        auth_user = getattr(master_profile, "user", None) if master_profile else None
        name_candidates = []
        if master_profile and hasattr(master_profile, "get_full_name"):
            name_candidates.append(master_profile.get_full_name())
        if auth_user and hasattr(auth_user, "get_full_name"):
            name_candidates.append(auth_user.get_full_name())
        if auth_user:
            name_candidates.extend([getattr(auth_user, "username", ""), getattr(auth_user, "email", "")])
        name_candidates.append(str(master_profile) if master_profile is not None else "")
        m_name = next((n for n in name_candidates if n), "")
        return s_name, m_name
    return f"{len(items)} services", "multiple masters"

# ──────────────────────────────────────────────────────────────────────────────
# Снимок полей перед сохранением и дифф после сохранения
# ──────────────────────────────────────────────────────────────────────────────

TRACK_FIELDS = (
    "client_id",
    "start_time",
    "payment_status_id",
    "final_price",
    "discount_source",
)

@dataclass
class Snapshot:
    values: Dict[str, Any]

def _take_snapshot(instance: Appointment) -> Snapshot:
    data = {}
    for f in TRACK_FIELDS:
        data[f] = getattr(instance, f, None)
    return Snapshot(values=data)

def _calc_diff(old: Snapshot, new: Snapshot) -> List[Tuple[str, Any, Any]]:
    diffs: List[Tuple[str, Any, Any]] = []
    for f in TRACK_FIELDS:
        if old.values.get(f) != new.values.get(f):
            diffs.append((f, old.values.get(f), new.values.get(f)))
    return diffs

def _diff_snapshot(instance: Appointment) -> List[Tuple[str, Any, Any]]:
    """
    Возвращает список изменений [(field, was, now), ...] для отслеживаемых полей.
    Использует снапшот из pre_save; если его нет — аккуратно деградирует.
    """
    old_snap = getattr(instance, "_old_snapshot", None)
    new_snap = _take_snapshot(instance)

    if old_snap is None:
        # нет старого состояния (создание или первый сейв) — diff пустой
        return []
    return _calc_diff(old_snap, new_snap)

def _humanize_diff(instance: Appointment, diffs: List[Tuple[str, Any, Any]]) -> str:
    """
    Красиво формируем список изменений для письма.
    """
    # Подготовим «человеческие» подписи
    name_map = {
        "client_id": "Client",
        "start_time": "Start time",
        "payment_status_id": "Payment status",
        "final_price": "Final price",
        "discount_source": "Discount source",
    }

    def label_fk(field: str, value):
        if value is None:
            return "—"
        try:
            if field == "client_id":
                # UserProfile
                obj = UserProfile.objects.filter(pk=value).select_related("user").first()
                return obj.get_full_name() if obj else f"#{value}"
            if field == "payment_status_id":
                obj = PaymentStatus.objects.filter(pk=value).first()
                return obj.name if obj else f"#{value}"
        except Exception:
            pass
        return str(value)

    lines = []
    for field, was, now in diffs:
        title = name_map.get(field, field)
        if field.endswith("_id"):
            was_h = label_fk(field, was)
            now_h = label_fk(field, now)
        elif field == "start_time":
            from django.utils.timezone import localtime
            was_h = localtime(was).strftime("%d %b %Y, %H:%M") if was else "—"
            now_h = localtime(now).strftime("%d %b %Y, %H:%M") if now else "—"
        elif field == "final_price":
            was_h = f"${was}" if was is not None else "—"
            now_h = f"${now}" if now is not None else "—"
        else:
            was_h = was or "—"
            now_h = now or "—"
        lines.append(f"• {title}: {was_h} → {now_h}")
    return "\n".join(lines)

@receiver(post_save, sender=AppointmentItemPromoCode)
def _recalc_after_promocode_add(sender, instance, created, **kwargs):
    appt = instance.appointment
    if not appt:
        return
    # Подавим «updated»-письмо для служебного пересчёта
    appt._skip_update_email = True
    appt.save(update_fields=["final_price", "discount_source"])

@receiver(post_delete, sender=AppointmentItemPromoCode)
def _recalc_after_promocode_remove(sender, instance, **kwargs):
    appt = instance.appointment
    if not appt:
        return
    appt._skip_update_email = True
    appt.save(update_fields=["final_price", "discount_source"])

# ──────────────────────────────────────────────────────────────────────────────
# pre_save: снимем «старые» значения, чтобы в post_save посчитать дифф
# ──────────────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Appointment)
def appointment_pre_save(sender, instance: Appointment, **kwargs):
    if not instance.pk:
        # Новая запись — дифф не нужен (создание отловим в post_save)
        instance._old_snapshot = None
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        instance._old_snapshot = _take_snapshot(old)
    except sender.DoesNotExist:
        instance._old_snapshot = None

@receiver(post_save, sender=AppointmentItem)
@receiver(post_delete, sender=AppointmentItem)
def _recompute_on_item_change(sender, instance: AppointmentItem, **kwargs):
    appt = instance.appointment
    # подавляем «updated» у визита
    appt._skip_update_email = True
    # appt.recompute_totals(save=True)

@receiver(post_save, sender=AppointmentItemPromoCode)
@receiver(post_delete, sender=AppointmentItemPromoCode)
def _recompute_on_promocode_change(sender, instance: AppointmentItemPromoCode, **kwargs):
    item = instance.item
    try:
        item.save()  # пересчёт позиционной цены (service/promocode)
    except Exception:
        pass
    appt = item.appointment
    appt._skip_update_email = True

# ──────────────────────────────────────────────────────────────────────────────
# post_save: рассылка «создано» и «изменено»
# ──────────────────────────────────────────────────────────────────────────────

# 5) appointment_post_save — ПОЛНОСТЬЮ ЗАМЕНИ

def _send_created_email(appt: Appointment) -> None:
    """Отправляет e-mail/SMS о создании визита, если его ещё не отправляли и есть позиции."""
    if Notification.objects.filter(appointment=appt, kind=Notification.CREATED, channel="email").exists():
        return  # уже отослано

    client = appt.client
    email = (client.user.email or "").strip()
    if not email or not appt.items.exists():
        return  # нет адреса или нет позиций — не шлём «пустое» письмо

    # красивый текст по позициям (service/master/time)
    from django.utils.timezone import localtime
    items_text = "\n".join(_items_summary_lines(appt)).strip()
    if not items_text:
        return

    # метки для SMS
    service_label, master_label = _short_labels(appt)
    # берём якорь из appointment.start_time (он синкается сигналом по айтемам),
    # а на всякий случай подстрахуемся start_time первого айтема
    first_item = appt.items.order_by("start_time").first()
    start_dt = appt.start_time or (first_item.start_time if first_item else None)
    start_local = localtime(start_dt).strftime("%d %b %Y, %H:%M") if start_dt else ""

    subject = "Your appointment is booked"
    text = (
        f"Hello, {client.user.get_full_name() or client.user.username}!\n\n"
        f"{items_text}\n"
    )
    html = (
        f"<!doctype html><html><body>"
        f"<h2>Your appointment is booked</h2>"
        f"<pre style='font:inherit'>{items_text}</pre>"
        f"</body></html>"
    )

    _send_email(email, subject, text, html, tag="appointment-created")
    Notification.objects.update_or_create(
        user=client,
        appointment=appt,
        channel="email",
        kind=Notification.CREATED,
        defaults={"message": text, "status": "sent"},
    )

    # SMS — один раз, если ещё не слали
    if not Notification.objects.filter(appointment=appt, kind=Notification.CREATED, channel="sms").exists():
        sms_body = f"Booked: {service_label} with {master_label} on {start_local}".strip()
        sid = send_sms(client.phone, sms_body)
        Notification.objects.update_or_create(
            user=client,
            appointment=appt,
            channel="sms",
            kind=Notification.CREATED,
            defaults={
                "message": sms_body,
                "provider": "twilio",
                "provider_message_id": sid or "",
                "status": "sent" if sid else "failed",
                "error": "" if sid else "twilio returned no SID",
            },
        )

@receiver(post_save, sender=Appointment)
def appointment_post_save(sender, instance: Appointment, created: bool, **kwargs):
    client = instance.client
    email = (client.user.email or "").strip()

    # якорное время визита уже хранится в appointment.start_time (min по позициям)
    start_local = localtime(instance.start_time).strftime("%d %b %Y, %H:%M")
    service_label, master_label = _short_labels(instance)
    items_text = "\n".join(_items_summary_lines(instance)) or "—"

        # если позиции уже есть (например, создали в одной транзакции) — шлём сейчас,
        # иначе дождёмся первого AppointmentItem

    diffs = _diff_snapshot(instance)
    if not diffs:
        return
    # если менялись только финансы сразу после создания (30 сек) — не спамим
    created_recently = (timezone.now() - instance.created_at) <= timedelta(seconds=30)

    if created_recently:
        if instance.items.exists():
            _send_created_email(instance)
        return

    diff_text = _humanize_diff(instance, diffs)
    subject = "Your appointment was updated"
    text = (
        f"Hello, {client.user.get_full_name() or client.user.username}!\n\n"
        f"Changes:\n{diff_text}\n\nCurrent services:\n{items_text}\n"
    )
    html = (
        f"<!doctype html><html><body>"
        f"<h2>Your appointment was updated</h2>"
        f"<p>{'<br>'.join(diff_text.splitlines())}</p>"
        f"<h3>Current services</h3>"
        f"<pre style='font:inherit'>{items_text}</pre>"
        f"</body></html>"
    )
    _send_email(email, subject, text, html, tag="appointment-updated")
    _notify_once(instance.id, client, message=f"[UPDATED]\n{text}")

    sms_body = f"Updated: {service_label} with {master_label} on {start_local}"
    sid = send_sms(client.phone, sms_body)
    Notification.objects.update_or_create(
        user=client,
        appointment=instance,
        channel="sms",
        kind=Notification.UPDATED,
        defaults={
            "message": sms_body,
            "provider": "twilio",
            "provider_message_id": sid or "",
            "status": "sent" if sid else "failed",
            "error": "" if sid else "twilio returned no SID",
        },
    )





# @receiver(post_save, sender=AppointmentItem)
# def send_created_when_first_item(sender, instance: AppointmentItem, created: bool, **kwargs):
#     if not created:
#         return
#     appt = instance.appointment
#     if Notification.objects.filter(appointment=appt, kind=Notification.CREATED, channel="email").exists():
#         return  # уже слали
#     # На сохранении айтемов мы и так делаем recompute_totals со скипом апдейт-писем.
#     # Здесь только отправим «created», когда появилась хотя бы 1 позиция.
#     _send_created_email(appt)


def _is_cancelled_status(status_obj) -> bool:
    """
    Универсальная проверка: имя/код/slug содержит 'cancel'.
    Поддерживает варианты 'Cancelled'/'Canceled'/'Cancel'.
    """
    if not status_obj:
        return False
    name = (getattr(status_obj, "name", "") or "").lower()
    code = (getattr(status_obj, "code", "") or "").lower()
    slug = (getattr(status_obj, "slug", "") or "").lower()
    return ("cancel" in name) or (code in {"cancel", "canceled", "cancelled"}) or (slug in {"cancel", "canceled", "cancelled"})


@receiver(post_save, sender=AppointmentStatusHistory)
def on_status_history_created(sender, instance: AppointmentStatusHistory, created, **kwargs):
    """
    Отправляем e-mail клиенту, когда создаётся запись истории со статусом 'cancelled'.
    Защищаемся от повторных отправок через Notification (если у вас такая модель есть).
    """
    if not created:
        return

    if not _is_cancelled_status(getattr(instance, "status", None)):
        return

    appt_id = instance.appointment_id

    # Антидублирование, если у вас заведена таблица уведомлений
    if Notification.objects.filter(appointment_id=appt_id, kind=Notification.CANCELLED, channel="email").exists():
        return

    # Отправка (Celery task)
    send_cancellation_email.delay(appointment_id=appt_id)
    user = getattr(instance.appointment, "client", None)
    # Опционально: помечаем, что уведомление отправлено (если у вас так принято)
    Notification.objects.create(
        user=user,
        appointment_id=appt_id,
        kind=Notification.CANCELLED,
        channel="email",
        message="Appointment cancelled email queued",
        provider="sendgrid",   # если у вас есть это поле
        status="sent",
    )


# (Необязательно, но полезно)
# Если в проекте статус меняется напрямую у Appointment, а не всегда через History:
@receiver(pre_save, sender=Appointment)
def on_appointment_status_changing(sender, instance: Appointment, **kwargs):
    """
    Если статус у Appointment меняется напрямую, отлавливаем смену на cancelled.
    (Работает только когда объект уже существует)
    """
    if not instance.pk:
        return

    try:
        prev = Appointment.objects.get(pk=instance.pk)
    except Appointment.DoesNotExist:
        return

    old_status = getattr(prev, "status", None)
    new_status = getattr(instance, "status", None)

    if new_status and (new_status != old_status) and _is_cancelled_status(new_status):
        # Отправляем только если ещё не отправляли (через Notification)
        if not Notification.objects.filter(appointment_id=instance.id, kind=Notification.CANCELLED, channel="email").exists():
            send_cancellation_email.delay(appointment_id=instance.id, kind="cancelled")
            Notification.objects.create(
                appointment=instance,
                kind=Notification.CANCELLED,
                channel="email",
                message="Appointment cancelled email queued (direct status change)",
            )


@receiver(post_save, sender=UserProfile)
def ensure_profile_universal_assignments(sender, instance: UserProfile, **kwargs):
    """
    Guarantee universal forms stay assigned whenever the profile is saved.
    """
    _safe_assignments_call(ensure_universal_assignments_for_profile, instance)


@receiver(pre_save, sender=ClientIntakeForm)
def snapshot_client_intake_form(sender, instance: ClientIntakeForm, **kwargs):
    """
    Remember prior universal flag to detect transitions in post_save.
    """
    if not instance.pk:
        instance._previous_is_universal = False
        return
    previous = (
        ClientIntakeForm.objects.filter(pk=instance.pk)
        .values_list("is_universal", flat=True)
        .first()
    )
    instance._previous_is_universal = bool(previous)


@receiver(post_save, sender=ClientIntakeForm)
def ensure_universal_assignments(sender, instance: ClientIntakeForm, created: bool, **kwargs):
    """
    When a form is created or toggled to be universal, auto-assign it to clients.
    """
    if not instance.is_universal:
        return
    was_universal = getattr(instance, "_previous_is_universal", False)
    if not created and was_universal:
        return
    _safe_assignments_call(ensure_universal_assignments_for_form, instance)

from django.apps import apps
from django.db import transaction

def ensure_payment_statuses(sender, **kwargs):
    PaymentStatus = apps.get_model("core", "PaymentStatus")
    Appointment = apps.get_model("core", "Appointment")
    defaults = ["Not Paid", "Pending", "Partially paid", "Paid", "Failed"]
    with transaction.atomic():
        for name in defaults:
            existing = PaymentStatus.objects.filter(name=name).order_by("id")
            if existing.exists():
                primary = existing.first()
                duplicates = list(existing[1:])
                if duplicates:
                    duplicate_ids = [dup.pk for dup in duplicates]
                    Appointment.objects.filter(payment_status_id__in=duplicate_ids).update(payment_status=primary)
                    PaymentStatus.objects.filter(pk__in=duplicate_ids).delete()
            else:
                PaymentStatus.objects.create(name=name)

    PaymentMethod = apps.get_model("core", "PaymentMethod")
    with transaction.atomic():
        for name in ("Stripe", "Cash", "Manual", "Credit card", "Debit card"):
            PaymentMethod.objects.get_or_create(name=name)

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save

def ensure_user_profile(sender, instance, created, **kwargs):
    UserProfile = apps.get_model('core', 'UserProfile')
    if created:
        UserProfile.objects.get_or_create(user=instance)

post_save.connect(ensure_user_profile, sender=get_user_model())

# core/signals.py
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save

def ensure_user_profile(sender, instance, created, **kwargs):
    UserProfile = apps.get_model('core', 'UserProfile')
    if created:
        UserProfile.objects.get_or_create(user=instance, defaults={"phone": None})

post_save.connect(ensure_user_profile, sender=get_user_model())


def _payment_method_name(payment: Payment) -> str:
    method = getattr(payment, "method", None)
    name = getattr(method, "name", "") if method else ""
    return (name or "").strip().lower()


def _normalize_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        try:
            return value.quantize(Decimal("0.01"))
        except Exception:
            return Decimal("0.00")
    if value in (None, "", "null"):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _ensure_amount_received(payment: Payment) -> None:
    if _normalize_decimal(getattr(payment, "amount_received", None)) > Decimal("0.00"):
        return

    previous_flag = getattr(payment, "_skip_receipt_signal", False)
    payment._skip_receipt_signal = True
    try:
        payment.amount_received = _normalize_decimal(getattr(payment, "amount", None))
        payment.save(update_fields=["amount_received"])
    finally:
        payment._skip_receipt_signal = previous_flag


def _appointment_grand_total(appointment) -> Decimal:
    if not appointment:
        return Decimal("0.00")
    try:
        from core.services.pricing import get_appointment_grand_total  # noqa

        return get_appointment_grand_total(appointment)
    except Exception:
        fallback = getattr(appointment, "total_with_tax", None)
        if fallback is None:
            fallback = getattr(appointment, "final_price", None)
        return _normalize_decimal(fallback)


def _update_payment_status(appointment, total_received: Decimal, grand_total: Decimal) -> None:
    if not appointment:
        return
    target_name = "Paid" if total_received >= grand_total else "Partially paid"
    status_obj, _ = PaymentStatus.objects.get_or_create(name=target_name)
    if appointment.payment_status_id != status_obj.id:
        appointment.payment_status = status_obj
        appointment.save(update_fields=["payment_status"])


@receiver(pre_save, sender=Payment)
def cache_previous_payment_state(sender, instance: Payment, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        instance._previous_receipt_sent_at = None
        return

    previous = (
        sender.objects.filter(pk=instance.pk)
        .values_list("status", "receipt_sent_at")
        .first()
    )
    if previous:
        instance._previous_status = previous[0]
        instance._previous_receipt_sent_at = previous[1]
    else:
        instance._previous_status = None
        instance._previous_receipt_sent_at = None


@receiver(post_save, sender=Payment)
def trigger_receipt_pipeline(sender, instance: Payment, created: bool, **kwargs):
    if kwargs.get("raw"):
        return

    if getattr(instance, "_skip_receipt_signal", False):
        return

    status = (instance.status or "").lower()
    if status != "succeeded":
        return

    previous_status = getattr(instance, "_previous_status", None)
    method_name = _payment_method_name(instance)
    appointment = getattr(instance, "appointment", None)

    if method_name != "stripe":
        _ensure_amount_received(instance)
        grand_total = _appointment_grand_total(appointment)
        total_received = get_total_received_for_appointment(appointment)
        _update_payment_status(appointment, total_received, grand_total)

    if created and getattr(instance, "stripe_payment_intent_id", None):
        return

    if not created and previous_status == "succeeded":
        return

    if instance.receipt_sent_at:
        return

    if not appointment:
        return

    payment_id = str(instance.pk)
    generate_payment_receipt_task.delay(payment_id)
    email_payment_receipt_task.delay(payment_id)

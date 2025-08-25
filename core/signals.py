# core/signals.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Any, List, Tuple

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.timezone import localtime

from .models import (
    Appointment,
    AppointmentStatusHistory,
    Notification,
    AppointmentPromoCode
)

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
    msg.send()


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


# ──────────────────────────────────────────────────────────────────────────────
# Снимок полей перед сохранением и дифф после сохранения
# ──────────────────────────────────────────────────────────────────────────────

TRACK_FIELDS = (
    "client_id",
    "master_id",
    "service_id",
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

def _humanize_diff(instance: Appointment, diffs: List[Tuple[str, Any, Any]]) -> str:
    """
    Красиво формируем список изменений для письма.
    """
    # Подготовим «человеческие» подписи
    name_map = {
        "client_id": "Client",
        "master_id": "Master",
        "service_id": "Service",
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
                from .models import UserProfile
                obj = UserProfile.objects.filter(pk=value).select_related("user").first()
                return obj.get_full_name() if obj else f"#{value}"
            if field == "master_id":
                from .models import MasterProfile
                obj = MasterProfile.objects.filter(pk=value).select_related("user").first()
                return obj.user.get_full_name() if obj else f"#{value}"
            if field == "service_id":
                from .models import Service
                obj = Service.objects.filter(pk=value).first()
                return obj.name if obj else f"#{value}"
            if field == "payment_status_id":
                from .models import PaymentStatus
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

@receiver(post_save, sender=AppointmentPromoCode)
def _recalc_after_promocode_add(sender, instance, created, **kwargs):
    appt = instance.appointment
    if not appt:
        return
    # Подавим «updated»-письмо для служебного пересчёта
    appt._skip_update_email = True
    appt.save(update_fields=["final_price", "discount_source"])

@receiver(post_delete, sender=AppointmentPromoCode)
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


# ──────────────────────────────────────────────────────────────────────────────
# post_save: рассылка «создано» и «изменено»
# ──────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=Appointment)
def appointment_post_save(sender, instance: Appointment, created: bool, **kwargs):
    client = instance.client
    email = (client.user.email or "").strip()
    # Приведём дату к локальному для текста
    start_local = localtime(instance.start_time).strftime("%d %b %Y, %H:%M")
    master_name = instance.master.user.get_full_name() or instance.master.user.username
    service_name = instance.service.name

    if getattr(instance, "_skip_update_email", False):
        return
    if created:
        # Только одно письмо «запись создана», БЕЗ доп. письма про «скидка изменилась»
        subject = "Your appointment is booked"
        text = (
            f"Hello, {client.user.get_full_name() or client.user.username}!\n\n"
            f"Service: {service_name}\n"
            f"Master: {master_name}\n"
            f"When: {start_local}\n"
        )
        html = (
            f"<!doctype html><html><body>"
            f"<h2>Your appointment is booked</h2>"
            f"<p>Service: <b>{service_name}</b><br>"
            f"Master: <b>{master_name}</b><br>"
            f"When: <b>{start_local}</b></p>"
            f"</body></html>"
        )
        _send_email(email, subject, text, html, tag="appointment-created")
        _notify_once(instance.id, client, message=f"[CREATED] {text}")
        return

    # Обновление: сравним снапшот
    old_snapshot: Snapshot | None = getattr(instance, "_old_snapshot", None)
    if not old_snapshot:
        return

    new_snapshot = _take_snapshot(instance)
    diffs = _calc_diff(old_snapshot, new_snapshot)
    if not diffs:
        return

    # Не отправляем «изменения» если они произошли одновременно с созданием — этот кейс уже отфильтрован выше.
    # Доп. фильтр: если изменился только discount_source (шум на первом сохранении) — не шлём.
    created_recently = (timezone.now() - instance.created_at) <= timedelta(seconds=30)
    changed_fields = {f for f, _, _ in diffs}
    if created_recently and changed_fields.issubset({"final_price", "discount_source"}):
        return

    diff_text = _humanize_diff(instance, diffs)
    subject = "Your appointment was updated"
    text = (
        f"Hello, {client.user.get_full_name() or client.user.username}!\n\n"
        f"Your appointment changes:\n{diff_text}\n"
    )
    html_lines = "<br>".join(line for line in diff_text.splitlines())
    html = (
        f"<!doctype html><html><body>"
        f"<h2>Your appointment was updated</h2>"
        f"<p>{html_lines}</p>"
        f"</body></html>"
    )
    _send_email(email, subject, text, html, tag="appointment-updated")
    _notify_once(instance.id, client, message=f"[UPDATED]\n{text}")


# ──────────────────────────────────────────────────────────────────────────────
# post_delete: рассылка «удалено»
# ──────────────────────────────────────────────────────────────────────────────

# @receiver(post_delete, sender=Appointment)
# def appointment_post_delete(sender, instance: Appointment, **kwargs):
#     """
#     Используем post_delete (а не pre_delete), чтобы у объекта был валидный pk и доступ к связям.
#     """
#     client = instance.client
#     email = (client.user.email or "").strip()
#     from django.utils.timezone import localtime
#     start_local = localtime(instance.start_time).strftime("%d %b %Y, %H:%M")
#     master_name = instance.master.user.get_full_name() or instance.master.user.username
#     service_name = instance.service.name
#
#     subject = "Your appointment was deleted"
#     text = (
#         f"Hello, {client.user.get_full_name() or client.user.username}!\n\n"
#         f"The appointment was deleted:\n"
#         f"Service: {service_name}\nMaster: {master_name}\nWhen: {start_local}\n"
#     )
#     html = (
#         f"<!doctype html><html><body>"
#         f"<h2>Your appointment was deleted</h2>"
#         f"<p>Service: <b>{service_name}</b><br>"
#         f"Master: <b>{master_name}</b><br>"
#         f"When: <b>{start_local}</b></p>"
#         f"</body></html>"
#     )
#
#     _send_email(email, subject, text, html, tag="appointment-deleted")
#     # Важно: работаем по appointment_id, чтобы не передавать «несохранённый» объект в фильтры
#     _notify_once(instance.id, client, message=f"[DELETED] {text}")

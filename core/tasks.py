from __future__ import annotations
from datetime import timedelta
from typing import Iterable

from celery import shared_task
from django.template.loader import render_to_string
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.db.models import OuterRef, Subquery

from core.models import Appointment, AppointmentStatusHistory, AppointmentStatus, Notification, UserProfile


# Насколько «широким» делаем окно, чтобы крон/бьёт не промахнулся
WINDOW_MINUTES = 15

def _base_queryset_for_window(target_start, target_end):
    """
    Берем записи, у которых start_time попадает в окно.
    Исключаем отменённые по последнему статусу.
    """
    # Последний статус по записи
    last_status_subq = (AppointmentStatusHistory.objects
                        .filter(appointment_id=OuterRef("pk"))
                        .order_by("-set_at")
                        .values("status__name")[:1])

    cancelled_name = (AppointmentStatus.objects
                      .filter(name__iexact="Cancelled")
                      .values_list("name", flat=True)
                      .first())

    qs = (Appointment.objects
          .select_related("client__user", "master__user", "service")
          .annotate(last_status_name=Subquery(last_status_subq))
          .filter(start_time__gte=target_start, start_time__lt=target_end))

    if cancelled_name:
        qs = qs.exclude(last_status_name=cancelled_name)

    return qs


def _render_subject_and_bodies(kind: str, ctx: dict[str, str]) -> tuple[str, str, str]:
    """
    kind: '48h' | '3h'
    Возвращает subject, text, html
    """
    if kind == "48h":
        subject = "Напоминание о визите"
        template = "email/appointment_reminder_48h.html"
    else:
        subject = "Скоро ваш визит"
        template = "email/appointment_reminder_3h.html"

    html = render_to_string(template, ctx)
    text = (
        f"Здравствуйте, {ctx['client_name']}!\n\n"
        f"Услуга: {ctx['service_name']}\n"
        f"Мастер: {ctx['master_name']}\n"
        f"Когда: {ctx['start_local']}\n"
    )
    return subject, text, html


def _already_sent(appt: Appointment, kind: str) -> bool:
    """
    Простая идемпотентность без миграций: проверяем, не отправляли ли уже
    в последние 7 дней уведомление с этим маркером в тексте и каналом email.
    """
    marker = f"[REM-{kind.upper()}]"
    week_ago = timezone.now() - timedelta(days=7)
    return Notification.objects.filter(
        appointment=appt, channel="email", message__startswith=marker, sent_at__gte=week_ago
    ).exists()


def _record_notification(appt: Appointment, client: UserProfile, kind: str, text_body: str):
    """Сохраняем запись о факте отправки (чтобы не дублировать в будущем)."""
    marker = f"[REM-{kind.upper()}]"
    Notification.objects.create(
        user=client,
        appointment=appt,
        channel="email",
        message=f"{marker} {text_body}",
    )


def _send_email(to_email: str, subject: str, text: str, html: str):
    """Отправка через Anymail backend (SendGrid)."""
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.attach_alternative(html, "text/html")
    # (опционально) можно добавить SendGrid-теги:
    try:
        msg.tags = ["appointment-reminder"]
    except Exception:
        pass
    msg.send()


@shared_task(name="core.tasks.send_appointment_reminders")
def send_appointment_reminders() -> dict:
    """
    Периодическая задача: раз в 5 минут проверяем два окна:
    - ~48 часов до старта
    - ~3 часа до старта
    И шлём письма только тем, кому ещё не слали (идемпотентность).
    """
    now = timezone.now()

    total_sent_48 = _process_window(now, ahead=timedelta(days=2), kind="48h")
    total_sent_3h = _process_window(now, ahead=timedelta(hours=3), kind="3h")

    return {"sent_48h": total_sent_48, "sent_3h": total_sent_3h}


def _process_window(now, ahead: timedelta, kind: str) -> int:
    start = now + ahead - timedelta(minutes=WINDOW_MINUTES)
    end = now + ahead + timedelta(minutes=WINDOW_MINUTES)

    qs = _base_queryset_for_window(start, end)
    sent = 0

    for appt in qs:
        client = appt.client
        email = (client.user.email or "").strip()
        if not email:
            continue

        if _already_sent(appt, kind):
            continue

        start_local = timezone.localtime(appt.start_time).strftime("%d %b %Y, %H:%M")
        ctx = {
            "client_name": client.user.get_full_name() or client.user.username,
            "service_name": appt.service.name,
            "master_name": appt.master.user.get_full_name() or appt.master.user.username,
            "start_local": start_local,
        }
        subject, text, html = _render_subject_and_bodies(kind, ctx)

        try:
            _send_email(email, subject, text, html)
            _record_notification(appt, client, kind, text)
            sent += 1
        except Exception as e:
            # Не падаем: просто пишем failed в Notification (по желанию)
            Notification.objects.create(
                user=client,
                appointment=appt,
                channel="email",
                message=f"[REM-{kind.upper()}][FAILED] {text}\n{e}",
            )

    return sent
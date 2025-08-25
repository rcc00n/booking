# core/tasks.py
from __future__ import annotations

from datetime import timedelta
from math import ceil
from typing import Optional

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import OuterRef, Subquery
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentStatus,
    AppointmentStatusHistory,
    Notification,
    UserProfile,
    ReminderSchedule,
)

# ──────────────────────────────────────────────────────────────────────────────
# Конфигурация
# ──────────────────────────────────────────────────────────────────────────────

# Допуск по времени (минут) для выборки окон при кроне
WINDOW_MINUTES = 15

# Фолбэк, если в БД нет ReminderSchedule
FALLBACK_REMINDER_OFFSETS = [
    timedelta(days=2),
    timedelta(hours=3),
]

# Необязательный шаблон ссылки на отзыв
REVIEW_URL_PATTERN: Optional[str] = getattr(settings, "REVIEW_FORM_URL", None)


# ──────────────────────────────────────────────────────────────────────────────
# Утилиты: почта/рендер/идемпотентность/база выборки
# ──────────────────────────────────────────────────────────────────────────────

def _send_email(to_email: str, subject: str, text: str, html: str, *, tag: str | None = None):
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    msg.attach_alternative(html, "text/html")
    try:
        if tag:
            msg.tags = [tag]  # если бэкенд поддерживает
    except Exception:
        pass
    msg.send()


def _safe_render(template_name: str, ctx: dict, fallback_subject: str) -> tuple[str, str]:
    """
    Пробуем отрендерить HTML‑шаблон; если его нет — делаем минимальный HTML.
    Возвращает (html, text_fоллбэк).
    """
    try:
        html = render_to_string(template_name, ctx)
    except Exception:
        html = (
            f"<!doctype html><html><body>"
            f"<h2>{fallback_subject}</h2>"
            f"<p>Hello, {ctx.get('client_name','')}!</p>"
            f"</body></html>"
        )
    text = ctx.get("text_fallback", fallback_subject)
    return html, text


def _base_queryset_for_window(target_start, target_end):
    """
    Выборка записей, которые начинаются в окне, с исключением последних статусов = Cancelled.
    """
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


def _label_for_offset(ahead: timedelta) -> str:
    """Человеко‑читаемая метка для идемпотентности: 2d/3h/30m."""
    total_sec = int(ahead.total_seconds())
    days = total_sec // 86400
    if days >= 1:
        return f"{days}d"
    hours = (total_sec % 86400) // 3600
    if hours >= 1:
        return f"{hours}h"
    minutes = (total_sec % 3600) // 60
    return f"{minutes}m"


def _kind_for_label(label: str) -> str:
    """
    Привязываем напоминания к фиксированным KIND, чтобы не конфликтовать с UniqueConstraint.
    Любые «нестандартные» слоты кладём в OTHER, но в нём пишем update_or_create.
    """
    norm = label.strip().lower()
    if norm in ("48h", "2d", "2д", "48ч"):
        return Notification.REM_D
    if norm in ("3h", "3ч"):
        return Notification.REM_H
    return Notification.OTHER


def _humanize_remaining(delta) -> tuple[str, str]:
    """Возвращает (оставшееся_время_текстом, суффикс_для_темы)."""
    total_sec = max(int(delta.total_seconds()), 0)
    hours_up = ceil(total_sec / 3600)
    if hours_up < 24:
        remaining = f"{hours_up} {'hour' if hours_up == 1 else 'hours'}"
        return remaining, f"in {remaining}"
    days_up = ceil(hours_up / 24)
    remaining = f"{days_up} {'day' if days_up == 1 else 'days'}"
    return remaining, f"in {remaining}"


def _already_sent(appt: Appointment, kind: str, marker_prefix: str | None = None) -> bool:
    """
    Идемпотентность: для напоминаний — по KIND; при желании можно дополнить префиксом.
    """
    qs = Notification.objects.filter(appointment=appt, channel="email", kind=kind)
    if marker_prefix:
        qs = qs.filter(message__startswith=marker_prefix)
    week_ago = timezone.now() - timedelta(days=7)
    return qs.filter(sent_at__gte=week_ago).exists()


def _record_notification(
        *, appt: Appointment, client: UserProfile, kind: str, message: str, marker_prefix: str | None = None
) -> None:
    """
    Безопасная запись Notification:
    - для REM_* используем get_or_create (строго одна запись на appointment/kind/channel);
    - для OTHER — update_or_create (чтобы не ловить IntegrityError).
    """
    base_kwargs = dict(
        user=client,
        appointment=appt,
        channel="email",
        kind=kind,
    )

    if kind in (Notification.REM_D, Notification.REM_H):
        Notification.objects.get_or_create(
            defaults={"message": f"{marker_prefix + ' ' if marker_prefix else ''}{message}",
                      "status": "sent"},
            **base_kwargs,
        )
    else:
        Notification.objects.update_or_create(
            defaults={"message": f"{marker_prefix + ' ' if marker_prefix else ''}{message}",
                      "status": "sent"},
            **base_kwargs,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Напоминания до визита
# ──────────────────────────────────────────────────────────────────────────────

def _render_reminder(ctx: dict[str, str]) -> tuple[str, str, str]:
    """
    Универсальный рендер напоминаний (EN).
    Шаблон: templates/email/appointment_reminder.html
    """
    subject = f"Reminder: your appointment {ctx['subject_suffix']}"
    ctx["text_fallback"] = (
        f"Hello, {ctx['client_name']}!\n\n"
        f"Service: {ctx['service_name']}\n"
        f"Master: {ctx['master_name']}\n"
        f"When: {ctx['start_local']} (starts {ctx['subject_suffix']})\n"
    )
    html, text = _safe_render("email/appointment_reminder.html", ctx, subject)
    return subject, text, html


def _process_reminder_window(now, ahead: timedelta, label: str) -> int:
    start = now + ahead - timedelta(minutes=WINDOW_MINUTES)
    end = now + ahead + timedelta(minutes=WINDOW_MINUTES)
    qs = _base_queryset_for_window(start, end)

    marker_prefix = f"[REM-{label.upper()}]"
    kind = _kind_for_label(label)
    sent = 0

    for appt in qs:
        client = appt.client
        email = (client.user.email or "").strip()
        if not email:
            continue
        if _already_sent(appt, kind=kind, marker_prefix=marker_prefix):
            continue

        start_local = timezone.localtime(appt.start_time).strftime("%d %b %Y, %H:%M")
        remaining, subj_suffix = _humanize_remaining(appt.start_time - now)
        ctx = {
            "client_name": client.user.get_full_name() or client.user.username,
            "service_name": appt.service.name,
            "master_name": appt.master.user.get_full_name() or appt.master.user.username,
            "start_local": start_local,
            "time_remaining": remaining,
            "subject_suffix": subj_suffix,
        }
        subject, text, html = _render_reminder(ctx)
        try:
            _send_email(email, subject, text, html, tag="appointment-reminder")
            _record_notification(appt=appt, client=client, kind=kind, message=text, marker_prefix=marker_prefix)
            sent += 1
        except Exception as e:
            Notification.objects.update_or_create(
                user=client, appointment=appt, channel="email", kind=kind,
                defaults={"message": f"{marker_prefix}[FAILED] {text}\n{e}", "status": "failed", "error": str(e)},
            )
    return sent


def _iter_schedules() -> list[tuple[timedelta, str]]:
    """
    Берём (offset, label) из ReminderSchedule (если есть) или из фолбэка.
    """
    result: list[tuple[timedelta, str]] = []
    if ReminderSchedule:
        try:
            for sch in ReminderSchedule.objects.filter(is_active=True):
                ahead = sch.get_timedelta()
                slug = getattr(sch, "slug", None) or _label_for_offset(ahead)
                result.append((ahead, slug))
        except Exception:
            pass
    if not result:
        for td in FALLBACK_REMINDER_OFFSETS:
            result.append((td, _label_for_offset(td)))
    return result


@shared_task(name="core.tasks.send_appointment_reminders")
def send_appointment_reminders() -> dict:
    """
    Запуск по крону: проверяет каждый конфиг и рассылает,
    не задевая уже отосланные окна.
    """
    now = timezone.now()
    counters = {}
    for ahead, label in _iter_schedules():
        counters[label] = _process_reminder_window(now, ahead=ahead, label=label)
    return counters


# ──────────────────────────────────────────────────────────────────────────────
# После визита: автозавершение + запрос отзыва
# ──────────────────────────────────────────────────────────────────────────────

def _get_status(name: str) -> Optional[AppointmentStatus]:
    return AppointmentStatus.objects.filter(name__iexact=name).first()


def _appointment_end_dt(appt: Appointment):
    dur = (appt.service.duration_min or 0) + (appt.service.extra_time_min or 0)
    return appt.start_time + timedelta(minutes=dur)


def _latest_status_name_subquery():
    return (AppointmentStatusHistory.objects
            .filter(appointment_id=OuterRef("pk"))
            .order_by("-set_at")
            .values("status__name")[:1])


def _set_completed_if_finished(now) -> int:
    """
    Ставит Completed тем визитам, что уже завершились (последние 3 дня),
    если последний статус не Cancelled/Completed.
    """
    completed = _get_status("Completed")
    cancelled_name = (AppointmentStatus.objects
                      .filter(name__iexact="Cancelled")
                      .values_list("name", flat=True)
                      .first())
    if not completed:
        return 0

    recent_from = now - timedelta(days=3)
    last_status_subq = _latest_status_name_subquery()
    qs = (Appointment.objects
          .select_related("client__user", "master__user", "service")
          .annotate(last_status_name=Subquery(last_status_subq))
          .filter(start_time__gte=recent_from, start_time__lte=now))

    updated = 0
    for appt in qs:
        last_name = (appt.last_status_name or "").lower()
        if last_name == "completed" or (cancelled_name and last_name == cancelled_name.lower()):
            continue
        if _appointment_end_dt(appt) <= now:
            profile = appt.client
            AppointmentStatusHistory.objects.create(
                appointment=appt,
                status=completed,
                set_by=profile,
            )
            updated += 1
    return updated


def _render_review_email(ctx: dict[str, str]) -> tuple[str, str, str]:
    subject = "How was your visit?"
    ctx["text_fallback"] = (
        f"Hello, {ctx['client_name']}!\n\n"
        f"We hope you enjoyed your {ctx['service_name']} with {ctx['master_name']} on {ctx['start_local']}.\n"
        f"Please share your feedback."
    )
    html, text = _safe_render("email/post_appointment_review.html", ctx, subject)
    return subject, text, html


def _send_review_requests(now) -> int:
    """
    Отправляем запросы на отзыв ~через 1 час после конца визита.
    """
    # окно вокруг «закончился ~ час назад»
    start = now - timedelta(hours=1, minutes=WINDOW_MINUTES)
    end = now - timedelta(hours=1) + timedelta(minutes=WINDOW_MINUTES)

    cancelled_name = (AppointmentStatus.objects
                      .filter(name__iexact="Cancelled")
                      .values_list("name", flat=True)
                      .first())

    last_status_subq = _latest_status_name_subquery()
    recent_from = now - timedelta(days=3)
    qs = (Appointment.objects
          .select_related("client__user", "master__user", "service")
          .annotate(last_status_name=Subquery(last_status_subq))
          .filter(start_time__gte=recent_from, start_time__lte=now))

    marker_prefix = "[REVIEW-REQ]"
    sent = 0

    for appt in qs:
        # пропускаем отменённые
        if cancelled_name and (appt.last_status_name or "").lower() == cancelled_name.lower():
            continue

        end_dt = _appointment_end_dt(appt)
        if not (start <= end_dt <= end):
            continue

        # для запросов отзыва используем kind=OTHER, но update_or_create — без дублей
        kind = Notification.OTHER

        if _already_sent(appt, kind=kind, marker_prefix=marker_prefix):
            continue

        client = appt.client
        email = (client.user.email or "").strip()
        if not email:
            continue

        start_local = timezone.localtime(appt.start_time).strftime("%d %b %Y, %H:%M")

        review_url = None
        if REVIEW_URL_PATTERN:
            try:
                review_url = REVIEW_URL_PATTERN.format(appointment_id=appt.id)
            except Exception:
                review_url = None

        ctx = {
            "client_name": client.user.get_full_name() or client.user.username,
            "service_name": appt.service.name,
            "master_name": appt.master.user.get_full_name() or appt.master.user.username,
            "start_local": start_local,
            "review_url": review_url,
        }
        subject, text, html = _render_review_email(ctx)
        try:
            _send_email(email, subject, text, html, tag="post-appointment-review")
            _record_notification(appt=appt, client=client, kind=kind, message=text, marker_prefix=marker_prefix)
            sent += 1
        except Exception as e:
            Notification.objects.update_or_create(
                user=client, appointment=appt, channel="email", kind=kind,
                defaults={"message": f"{marker_prefix}[FAILED] {text}\n{e}", "status": "failed", "error": str(e)},
            )

    return sent


@shared_task(name="core.tasks.post_appointment_status_and_reviews")
def post_appointment_status_and_reviews() -> dict:
    """
    Крон‑задача:
      1) авто‑ставит Completed, когда визит завершился;
      2) шлёт запрос на отзыв через ~1 час после окончания.
    """
    now = timezone.now()
    auto_completed = _set_completed_if_finished(now)
    review_sent = _send_review_requests(now)
    return {"auto_completed": auto_completed, "review_requests_sent": review_sent}


# ──────────────────────────────────────────────────────────────────────────────
# Единая точка входа для Celery Beat
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(name="core.tasks.run_all_schedulers")
def run_all_schedulers() -> dict:
    """
    Удобная «обёртка» для Beat: вызывает все внутренние планировщики.
    """
    res1 = send_appointment_reminders()
    res2 = post_appointment_status_and_reviews()
    return {"reminders": res1, "post_appointment": res2}


# ──────────────────────────────────────────────────────────────────────────────
# Точечные задачи (для вызова из сигналов/вьюх)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(name="core.tasks.send_cancellation_email")
def send_cancellation_email(appointment_id: str, reason: str | None = None) -> bool:
    """
    Отправить письмо клиенту об отмене записи.
    Рекомендуется вызывать из сигнала после фиксации статуса Cancelled
    (post_save AppointmentStatusHistory), а не при удалении записи.
    """
    appt = Appointment.objects.select_related("client__user", "master__user", "service").filter(id=appointment_id).first()
    if not appt:
        return False

    client = appt.client
    email = (client.user.email or "").strip()
    if not email:
        return False

    start_local = timezone.localtime(appt.start_time).strftime("%d %b %Y, %H:%M")
    subject = "Your appointment has been cancelled"
    ctx = {
        "client_name": client.user.get_full_name() or client.user.username,
        "service_name": appt.service.name,
        "master_name": appt.master.user.get_full_name() or appt.master.user.username,
        "start_local": start_local,
        "cancellation_reason": reason or "",
        "text_fallback": (
                f"Hello, {client.user.get_full_name() or client.user.username}!\n\n"
                f"Your appointment for {appt.service.name} with {appt.master.user.get_full_name() or appt.master.user.username} "
                f"on {start_local} has been cancelled."
                + (f"\nReason: {reason}" if reason else "")
        ),
    }
    html, text = _safe_render("email/appointment_cancelled.html", ctx, subject)

    # kind=OTHER, но с update_or_create — не создаём дубликаты
    kind = Notification.OTHER
    marker_prefix = "[CANCELLED]"

    if _already_sent(appt, kind=kind, marker_prefix=marker_prefix):
        return True

    try:
        _send_email(email, subject, text, html, tag="appointment-cancelled")
        _record_notification(appt=appt, client=client, kind=kind, message=text, marker_prefix=marker_prefix)
        return True
    except Exception as e:
        Notification.objects.update_or_create(
            user=client, appointment=appt, channel="email", kind=kind,
            defaults={"message": f"{marker_prefix}[FAILED] {text}\n{e}", "status": "failed", "error": str(e)},
        )
        return False

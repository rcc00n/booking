# core/tasks.py
from __future__ import annotations

from datetime import timedelta
from math import ceil
from typing import Optional
from .utils.sms import send_sms
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
    AppointmentItem
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

# 2) Хелперы для позиций
def _items_summary_lines(appt: Appointment) -> list[str]:
    qs = appt.items.select_related("service", "master__user").order_by("start_time")
    lines = []
    for it in qs:
        s = timezone.localtime(it.start_time).strftime("%d %b %Y, %H:%M")
        m = it.master.user.get_full_name() or it.master.user.username
        lines.append(f"• {it.service.name} with {m} at {s}")
    return lines

def _label_service_master(appt: Appointment) -> tuple[str, str]:
    items = list(appt.items.select_related("service", "master__user"))

    if not items:
        return "", ""
    if len(items) == 1:
        it = items[0]
        return it.service.name, (it.master.user.get_full_name() or it.master.user.user.username)
    return f"{len(items)} services", "multiple masters"


def _base_queryset_for_window(target_start, target_end):
    last_status_subq = (AppointmentStatusHistory.objects
                        .filter(appointment_id=OuterRef("pk"))
                        .order_by("-set_at")
                        .values("status__name")[:1])

    cancelled_name = (AppointmentStatus.objects
                      .filter(name__iexact="Cancelled")
                      .values_list("name", flat=True)
                      .first())

    qs = (Appointment.objects
          .select_related("client__user")
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

# 4) Рендер напоминания — теперь добавляем items_lines и агрегированные ярлыки
def _render_reminder(ctx: dict[str, str]) -> tuple[str, str, str]:
    subject = f"Reminder: your appointment {ctx['subject_suffix']}"
    # fallback-текст
    lines = ctx.get("items_lines") or []
    items_block = ("\n".join(lines)) if lines else f"Service: {ctx['service_name']}\nMaster: {ctx['master_name']}"
    ctx["text_fallback"] = (
        f"Hello, {ctx['client_name']}!\n\n"
        f"{items_block}\n"
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
        service_name, master_name = _label_service_master(appt)
        items_lines = _items_summary_lines(appt)

        ctx = {
            "client_name": client.user.get_full_name() or client.user.username,
            "service_name": service_name,
            "master_name": master_name,
            "start_local": start_local,
            "time_remaining": remaining,
            "subject_suffix": subj_suffix,
            "items_lines": items_lines,
        }
        subject, text, html = _render_reminder(ctx)
        try:
            _send_email(email, subject, text, html, tag="appointment-reminder")
            _record_notification(appt=appt, client=client, kind=kind, message=text, marker_prefix=marker_prefix)
            sid = send_sms(client.phone, text)
            Notification.objects.update_or_create(
                user=client, appointment=appt, channel="sms", kind=kind,
                defaults={
                    "message": text,
                    "provider": "twilio",
                    "provider_message_id": sid or "",
                    "status": "sent" if sid else "failed",
                    "error": "" if sid else "twilio returned no SID",
                },
            )
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
    items = list(appt.items.select_related("service"))
    if not items:
        return appt.start_time
    # предполагается, что у AppointmentItem есть свойство end_time
    return max(it.end_time for it in items)


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
          .select_related("client__user")
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
          .select_related("client__user")
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
            "start_local": start_local,
            "review_url": review_url,
            "items_lines": _items_summary_lines(appt)
        }
        subject, text, html = _render_review_email(ctx)
        try:
            _send_email(email, subject, text, html, tag="post-appointment-review")
            _record_notification(appt=appt, client=client, kind=kind, message=text, marker_prefix=marker_prefix)
            sid = send_sms(client.phone, text)
            Notification.objects.update_or_create(
                user=client, appointment=appt, channel="sms", kind=kind,
                defaults={
                    "message": text,
                    "provider": "twilio",
                    "provider_message_id": sid or "",
                    "status": "sent" if sid else "failed",
                    "error": "" if sid else "twilio returned no SID",
                },
            )
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
    appt = Appointment.objects.select_related("client__user").filter(id=appointment_id).first()
    if not appt:
        return False

    client = appt.client
    email = (client.user.email or "").strip()
    if not email:
        return False

    start_local = timezone.localtime(appt.start_time).strftime("%d %b %Y, %H:%M")
    service_name, master_name = _label_service_master(appt)
    items_lines = _items_summary_lines(appt)

    subject = "Your appointment has been cancelled"
    text_lines = [
        f"Hello, {client.user.get_full_name() or client.user.username}!",
        "",
        "Your appointment has been cancelled.",
        f"When: {start_local}",
    ]
    if reason:
        text_lines.append(f"Reason: {reason}")
    if items_lines:
        text_lines.append("")
        text_lines.extend(items_lines)
    text = "\n".join(text_lines)

    try:
        html, _ = _safe_render("email/appointment_cancelled.html", {
            "client_name": client.user.get_full_name() or client.user.username,
            "start_local": start_local,
            "reason": reason or "",
            "items_lines": items_lines,
            "service_name": service_name,  # для совместимости со старыми шаблонами
            "master_name": master_name,
            "text_fallback": text,
        }, subject)
        kind = Notification.CANCELLED
        marker_prefix = "[CANCELLED]"

        _send_email(email, subject, text, html, tag="appointment-cancelled")
        _record_notification(appt=appt, client=client, kind=kind, message=text, marker_prefix=marker_prefix)

        sid = send_sms(client.phone, text)
        Notification.objects.update_or_create(
            user=client, appointment=appt, channel="sms", kind=kind,
            defaults={
                "message": text,
                "provider": "twilio",
                "provider_message_id": sid or "",
                "status": "sent" if sid else "failed",
                "error": "" if sid else "twilio returned no SID",
            },
        )
        return True
    except Exception as e:
        Notification.objects.update_or_create(
            user=client, appointment=appt, channel="email", kind=kind,
            defaults={"message": f"{marker_prefix}[FAILED] {text}\n{e}", "status": "failed", "error": str(e)},
        )
        return False

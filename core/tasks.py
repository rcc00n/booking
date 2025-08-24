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
    ReminderSchedule
)

# ──────────────────────────────────────────────────────────────────────────────
# Optional import of custom schedules (admin-configurable). Fallback is used if
# the model doesn't exist in your project yet.
# ──────────────────────────────────────────────────────────────────────────────



# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

# Beat/cron jitter tolerance (± minutes around target time)
WINDOW_MINUTES = 15

# Fallback: static offsets if ReminderSchedule model is not available.
FALLBACK_REMINDER_OFFSETS = [
    timedelta(days=2),
    timedelta(hours=3),
]

# Optional: review link pattern; e.g., "https://your-domain.tld/review/{appointment_id}/"
REVIEW_URL_PATTERN: Optional[str] = getattr(settings, "REVIEW_FORM_URL", None)


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
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
            msg.tags = [tag]
    except Exception:
        pass
    msg.send()


def _base_queryset_for_window(target_start, target_end):
    """
    Pick appointments whose start_time lands in the window and exclude those
    whose *latest* status is Cancelled.
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
    """Generate idempotence label: e.g., 2d, 3h, 30m."""
    total_sec = int(ahead.total_seconds())
    days = total_sec // 86400
    if days >= 1:
        return f"{days}d"
    hours = (total_sec % 86400) // 3600
    if hours >= 1:
        return f"{hours}h"
    minutes = (total_sec % 3600) // 60
    return f"{minutes}m"


def _humanize_remaining(delta) -> tuple[str, str]:
    """
    Returns (remaining_text, subject_suffix).
    < 24h → show hours (ceil); otherwise → days (ceil).
    """
    total_sec = max(int(delta.total_seconds()), 0)
    hours_up = ceil(total_sec / 3600)  # 0..∞
    if hours_up < 24:
        remaining = f"{hours_up} {'hour' if hours_up == 1 else 'hours'}"
        return remaining, f"in {remaining}"
    days_up = ceil(hours_up / 24)
    remaining = f"{days_up} {'day' if days_up == 1 else 'days'}"
    return remaining, f"in {remaining}"


def _already_sent(appt: Appointment, marker_prefix: str) -> bool:
    """
    Idempotence check for Notification.message prefix — last 7 days.
    Example prefixes: "[REM-2D]", "[REM-3H]", "[REVIEW-REQ]".
    """
    week_ago = timezone.now() - timedelta(days=7)
    return Notification.objects.filter(
        appointment=appt,
        channel="email",
        message__startswith=marker_prefix,
        sent_at__gte=week_ago
    ).exists()


def _record_notification(appt: Appointment, client: UserProfile, marker_prefix: str, text_body: str):
    Notification.objects.create(
        user=client,
        appointment=appt,
        channel="email",
        message=f"{marker_prefix} {text_body}",
    )


def _safe_render(template_name: str, ctx: dict, fallback_subject: str) -> tuple[str, str]:
    """
    Try to render HTML template; if missing, fallback to a minimal HTML string.
    Returns (html, text_fallback).
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


# ──────────────────────────────────────────────────────────────────────────────
# Reminder emails (pre-appointment)
# ──────────────────────────────────────────────────────────────────────────────

def _render_reminder(ctx: dict[str, str]) -> tuple[str, str, str]:
    """
    Universal reminder renderer (English).
    Template: templates/email/appointment_reminder.html
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
    sent = 0

    for appt in qs:
        client = appt.client
        email = (client.user.email or "").strip()
        if not email:
            continue
        if _already_sent(appt, marker_prefix):
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
            _record_notification(appt, client, marker_prefix, text)
            sent += 1
        except Exception as e:
            Notification.objects.create(
                user=client, appointment=appt, channel="email",
                message=f"{marker_prefix}[FAILED] {text}\n{e}",
            )
    return sent


def _iter_schedules() -> list[tuple[timedelta, str]]:
    """
    Returns a list of (offset_timedelta, slug/label) either from ReminderSchedule
    (admin-configurable) or fallback constants.
    """
    result: list[tuple[timedelta, str]] = []
    if ReminderSchedule:
        try:
            # Expecting model API: .get_timedelta() and .slug or .label
            for sch in ReminderSchedule.objects.filter(is_active=True):
                ahead = sch.get_timedelta()
                # slug is used in idempotency marker; if absent, derive from timedelta
                slug = getattr(sch, "slug", None) or _label_for_offset(ahead)
                result.append((ahead, slug))
        except Exception:
            pass
    if not result:
        # fallback
        for td in FALLBACK_REMINDER_OFFSETS:
            result.append((td, _label_for_offset(td)))
    return result


@shared_task(name="core.tasks.send_appointment_reminders")
def send_appointment_reminders() -> dict:
    """
    Beat-friendly task: checks each schedule window and sends
    reminders to those who haven't received that offset yet.
    """
    now = timezone.now()
    counters = {}
    for ahead, label in _iter_schedules():
        counters[label] = _process_reminder_window(now, ahead=ahead, label=label)
    return counters


# ──────────────────────────────────────────────────────────────────────────────
# Post-appointment: auto-complete + review request (~1 hour after end)
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
    Mark as Completed any appointments that have ended in the last 3 days,
    whose latest status is neither Cancelled nor Completed.
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
            profile = appt.client  # who sets the status; safe default
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
    Send review requests ~1 hour after appointment end.
    Uses ±WINDOW_MINUTES to tolerate cron jitter.
    """
    # Window around "ended ~ 1 hour ago"
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
        # Skip cancelled
        if cancelled_name and (appt.last_status_name or "").lower() == cancelled_name.lower():
            continue

        end_dt = _appointment_end_dt(appt)
        if not (start <= end_dt <= end):
            continue

        if _already_sent(appt, marker_prefix):
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
            _record_notification(appt, client, marker_prefix, text)
            sent += 1
        except Exception as e:
            Notification.objects.create(
                user=client, appointment=appt, channel="email",
                message=f"{marker_prefix}[FAILED] {text}\n{e}",
            )

    return sent


@shared_task(name="core.tasks.post_appointment_status_and_reviews")
def post_appointment_status_and_reviews() -> dict:
    """
    Beat-friendly task:
      1) Auto-completes finished appointments (unless Cancelled).
      2) Sends review requests ~1 hour after end.
    """
    now = timezone.now()
    auto_completed = _set_completed_if_finished(now)
    review_sent = _send_review_requests(now)
    return {"auto_completed": auto_completed, "review_requests_sent": review_sent}


# ──────────────────────────────────────────────────────────────────────────────
# Single entry point for Celery Beat
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(name="core.tasks.run_all_schedulers")
def run_all_schedulers() -> dict:
    """
    If your Beat currently runs only one task, point it here.
    This will:
      - send pre-appointment reminders
      - auto-complete finished appointments
      - send post-appointment review requests
    """
    res1 = send_appointment_reminders()
    res2 = post_appointment_status_and_reviews()
    return {"reminders": res1, "post_appointment": res2}

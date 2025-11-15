"""Signal listeners that bridge core events with Telegram alerts."""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Appointment, Payment
from .models import TelegramBotSettings
from .services import notify_new_appointment, notify_payment_succeeded


@receiver(post_save, sender=Appointment)
def appointment_created_handler(sender, instance: Appointment, created: bool, **kwargs) -> None:
    if kwargs.get("raw") or not created:
        return

    settings_obj = TelegramBotSettings.load()
    if not (settings_obj.is_enabled and settings_obj.send_booking_alerts):
        return

    transaction.on_commit(lambda: notify_new_appointment(str(instance.pk)))


@receiver(post_save, sender=Payment)
def payment_succeeded_handler(sender, instance: Payment, created: bool, **kwargs) -> None:
    if kwargs.get("raw"):
        return

    settings_obj = TelegramBotSettings.load()
    if not (settings_obj.is_enabled and settings_obj.send_payment_alerts):
        return

    status = (instance.status or "").lower()
    if status != "succeeded":
        return

    previous_status = (getattr(instance, "_previous_status", None) or "").lower()
    if not created and previous_status == "succeeded":
        return

    transaction.on_commit(lambda: notify_payment_succeeded(str(instance.pk)))

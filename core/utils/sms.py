from __future__ import annotations

from django.conf import settings
from twilio.rest import Client

def send_sms(to_number: str, body: str) -> str | None:
    """
    Отправка SMS через Twilio. Возвращает message SID или None при ошибке.
    Ожидается формат номера E.164 (например, +17805551212).
    """
    if not to_number or not body:
        return None

    account = getattr(settings, "TWILIO_ACCOUNT_SID", None)
    token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
    from_number = getattr(settings, "TWILIO_FROM_NUMBER", None)
    if not (account and token and from_number):
        return None

    try:
        client = Client(account, token)
        msg = client.messages.create(
            body=body.strip(),
            from_=from_number,
            to=to_number.strip(),
        )
        return msg.sid
    except Exception:
        return None
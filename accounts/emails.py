import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from core.models import EmailVerification

CODE_TTL_MIN = 10
RESEND_COOLDOWN_SEC = 45
MAX_ATTEMPTS = 6


class ResendNotAllowed(Exception):
    """Raised when resend cooldown has not elapsed yet."""

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__("Resend not allowed yet.")


def _generate_code() -> str:
    """Return a cryptographically secure 6-digit verification code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def can_resend(last_sent_at) -> bool:
    if not last_sent_at:
        return True
    return (timezone.now() - last_sent_at).total_seconds() >= RESEND_COOLDOWN_SEC


def start_or_resend_verification(user, purpose: str = EmailVerification.PURPOSE_REGISTER) -> EmailVerification:
    """
    Create a new verification entry or resend an active one.

    Ensures a single active verification per user/purpose, extending expiry when resending.
    """
    email = (user.email or "").strip().lower()
    if not email:
        raise ValueError("User email required for verification.")

    now = timezone.now()
    existing = (
        EmailVerification.objects.filter(user=user, purpose=purpose, is_used=False)
        .order_by("-created_at")
        .first()
    )

    if existing and not existing.is_expired():
        if not can_resend(existing.last_sent_at):
            last_sent_at = existing.last_sent_at or now
            elapsed = (now - last_sent_at).total_seconds()
            retry_after = max(0, int(RESEND_COOLDOWN_SEC - elapsed))
            raise ResendNotAllowed(retry_after=retry_after if elapsed < RESEND_COOLDOWN_SEC else 0)
        existing.expires_at = now + timedelta(minutes=CODE_TTL_MIN)
        existing.sent_to = email
        existing.save(update_fields=["expires_at", "sent_to", "last_sent_at"])
        verification = existing
    else:
        verification = EmailVerification.objects.create(
            user=user,
            purpose=purpose,
            code=_generate_code(),
            sent_to=email,
            expires_at=now + timedelta(minutes=CODE_TTL_MIN),
        )

    _send_verification_email(email, verification.code)
    return verification


def _send_verification_email(to_email: str, code: str) -> None:
    subject = "Your verification code"
    text_body = f"Your verification code is: {code}\nThis code will expire in {CODE_TTL_MIN} minutes."
    html_body = f"""<!doctype html><html><body>
<p>Your verification code is:</p>
<h2 style="font-family:system-ui;margin:0">{code}</h2>
<p>This code will expire in {CODE_TTL_MIN} minutes.</p>
</body></html>"""

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send()

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import ValidationError

from core.forms import _normalize_phone
from core.models import UserProfile

User = get_user_model()


class EmailPhoneBackend(ModelBackend):
    """
    Authenticate users by username, email, or phone number.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or "").strip()
        if not identifier or password is None:
            return None

        user = (
            self._get_by_username(identifier)
            or self._get_by_email(identifier)
            or self._get_by_phone(identifier)
        )
        if not user:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    @staticmethod
    def _get_by_username(identifier: str):
        try:
            return User.objects.get(username=identifier)
        except User.DoesNotExist:
            return None

    @staticmethod
    def _get_by_email(identifier: str):
        try:
            return User.objects.get(email__iexact=identifier)
        except User.DoesNotExist:
            return None

    def _get_by_phone(self, identifier: str):
        normalized = self._normalize_phone(identifier)
        if not normalized:
            return None
        profile = (
            UserProfile.objects.select_related("user")
            .filter(phone=normalized)
            .first()
        )
        return getattr(profile, "user", None)

    @staticmethod
    def _normalize_phone(value: str) -> str | None:
        if not value:
            return None
        try:
            return _normalize_phone(value)
        except ValidationError:
            return None

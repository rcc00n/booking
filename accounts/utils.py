from __future__ import annotations

from typing import Any, Dict

from django.utils import timezone

def build_autofill_defaults(user) -> Dict[str, Any]:
    """
    Produce a JSON-serializable snapshot of the current user's profile data that can be reused
    across templates for client-side autofill.
    """
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    profile = getattr(user, "userprofile", None) if is_authenticated else None

    birth_date = ""
    if profile and getattr(profile, "birth_date", None):
        birth_date = profile.birth_date.isoformat()

    profile_data = {
        "first_name": getattr(user, "first_name", "") or "",
        "last_name": getattr(user, "last_name", "") or "",
        "full_name": user.get_full_name().strip() if is_authenticated else "",
        "email": getattr(user, "email", "") or "",
        "phone": getattr(profile, "phone", "") or "",
        "birth_date": birth_date,
        "address": getattr(profile, "address", "") or "",
        "postal_code": getattr(profile, "postal_code", "") or "",
        "how_heard": getattr(profile, "how_heard", "") or "",
        "email_marketing_consent": bool(getattr(profile, "email_marketing_consent", False)),
    }

    payment_data: Dict[str, Any] = {}
    if profile:
        if isinstance(getattr(profile, "billing_contact", None), dict):
            payment_data.update(profile.billing_contact or {})

        def _set_if_missing(key: str, value: Any) -> None:
            if value in (None, ""):
                return
            if not payment_data.get(key):
                payment_data[key] = value

        full_name = f"{profile_data['first_name']} {profile_data['last_name']}".strip()
        _set_if_missing("name", full_name)
        _set_if_missing("email", profile_data["email"])
        _set_if_missing("phone", profile_data["phone"])
        _set_if_missing("postal_code", profile_data["postal_code"])
        if profile_data["address"]:
            lines = str(profile_data["address"]).split("\n")
            _set_if_missing("address_line1", lines[0].strip())
            if len(lines) > 1:
                _set_if_missing("address_line2", " ".join(line.strip() for line in lines[1:]))

        updated_at = getattr(profile, "billing_contact_updated_at", None)
        if updated_at:
            payment_data["updated_at"] = timezone.localtime(updated_at).isoformat()

    return {
        "user": {
            "id": getattr(user, "pk", None) if is_authenticated else None,
            "username": user.get_username() if is_authenticated else "",
            "email": getattr(user, "email", "") or "",
            "is_authenticated": is_authenticated,
        },
        "profile": profile_data,
        "health": getattr(profile, "health_conditions", {}) or {},
        "payment": payment_data,
    }

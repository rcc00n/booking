from __future__ import annotations

from typing import Any, Dict

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

    return {
        "user": {
            "id": getattr(user, "pk", None) if is_authenticated else None,
            "username": user.get_username() if is_authenticated else "",
            "email": getattr(user, "email", "") or "",
            "is_authenticated": is_authenticated,
        },
        "profile": profile_data,
        "health": getattr(profile, "health_conditions", {}) or {},
    }

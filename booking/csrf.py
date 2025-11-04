from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import requires_csrf_token


logger = logging.getLogger(__name__)


def _wants_json(request: HttpRequest) -> bool:
    """
    Return True when the client explicitly prefers a JSON response.
    """
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept", "")
    if "application/json" in accept or "text/json" in accept:
        return True
    return False


@requires_csrf_token
def csrf_failure_view(
    request: HttpRequest,
    reason: str = "",
    template_name: str = "security/csrf_failure.html",
) -> HttpResponse:
    """
    A user-friendly CSRF failure handler.
    Returns JSON payloads for XHR clients and a minimal HTML page for others.
    """
    message = "For your security we could not validate this request. Please refresh the page and try again."
    log_extra: dict[str, Any] = {
        "path": request.get_full_path(),
        "method": request.method,
        "user_id": getattr(getattr(request, "user", None), "id", None),
    }
    logger.warning("CSRF verification failed: %s", reason or "token mismatch", extra=log_extra)

    if _wants_json(request):
        payload = {
            "ok": False,
            "code": "csrf_failure",
            "error": message,
        }
        response = JsonResponse(payload, status=403)
        response["X-CSRF-Refresh"] = "required"
        return response

    context = {
        "message": message,
        "reason": reason,
    }
    return render(request, template_name, context, status=403)

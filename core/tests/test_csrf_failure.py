from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from booking.csrf import csrf_failure_view


class CsrfFailureViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_ajax_request_receives_json_payload(self) -> None:
        request = self.factory.post(
            "/accounts/api/test/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        request.user = AnonymousUser()

        response = csrf_failure_view(request, reason="token mismatch")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["X-CSRF-Refresh"], "required")
        self.assertJSONEqual(
            response.content.decode("utf-8"),
            {
                "ok": False,
                "code": "csrf_failure",
                "error": "For your security we could not validate this request. Please refresh the page and try again.",
            },
        )

    def test_classic_request_renders_accessible_page(self) -> None:
        request = self.factory.post("/accounts/profile/update/")
        request.user = AnonymousUser()

        response = csrf_failure_view(request, reason="token mismatch")

        self.assertEqual(response.status_code, 403)
        content = response.content.decode("utf-8")
        self.assertIn("Let's refresh your session", content)
        self.assertIn("Please refresh the page and try again.", content)
        self.assertIn("token mismatch", content)

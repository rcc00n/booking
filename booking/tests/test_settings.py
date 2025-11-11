from __future__ import annotations

from django.test import SimpleTestCase

from booking.settings import _build_csrf_trusted_origins


class BuildCsrfTrustedOriginsTests(SimpleTestCase):
    def test_filters_empty_entries_and_normalizes_hosts(self) -> None:
        hosts = ["", "   ", None, "  example.com  ", "https://already.valid"]

        origins = _build_csrf_trusted_origins(hosts)  # type: ignore[arg-type]

        self.assertEqual(
            origins,
            [
                "https://example.com",
                "https://already.valid",
            ],
        )

    def test_adds_http_for_local_hosts(self) -> None:
        hosts = ["localhost", "127.0.0.1", ".internal.local"]

        origins = _build_csrf_trusted_origins(hosts)

        self.assertEqual(
            origins,
            [
                "https://localhost",
                "http://localhost",
                "https://127.0.0.1",
                "http://127.0.0.1",
                "https://internal.local",
                "http://internal.local",
            ],
        )

    def test_preserves_order_while_deduplicating(self) -> None:
        hosts = ["malva.example", "https://malva.example", "malva.example", "localhost"]

        origins = _build_csrf_trusted_origins(hosts)

        self.assertEqual(
            origins,
            [
                "https://malva.example",
                "https://localhost",
                "http://localhost",
            ],
        )

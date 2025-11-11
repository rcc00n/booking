from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase
from unittest.mock import patch

from core.utils.pdf import render_html_to_pdf


class RenderHtmlToPdfTests(SimpleTestCase):
    def test_rejects_non_string_html(self) -> None:
        with self.assertRaises(TypeError):
            render_html_to_pdf(123)  # type: ignore[arg-type]

    def test_returns_empty_bytes_for_blank_html(self) -> None:
        self.assertEqual(render_html_to_pdf("   "), b"")

    @patch("core.utils.pdf._render_with_xhtml2pdf")
    @patch("core.utils.pdf._render_with_weasyprint", return_value=b"PDF-WEASY")
    def test_prefers_weasyprint_when_available(self, mock_weasy, mock_xhtml) -> None:
        html = "   <p>Hello</p>   "

        result = render_html_to_pdf(html)

        self.assertEqual(result, b"PDF-WEASY")
        mock_weasy.assert_called_once_with("<p>Hello</p>", str(getattr(settings, "BASE_DIR", ".")))
        mock_xhtml.assert_not_called()

    @patch("core.utils.pdf._render_with_xhtml2pdf", return_value=b"PDF-FALLBACK")
    @patch("core.utils.pdf._render_with_weasyprint", return_value=None)
    def test_falls_back_to_xhtml2pdf(self, mock_weasy, mock_xhtml) -> None:
        result = render_html_to_pdf("<p>Hi</p>")

        self.assertEqual(result, b"PDF-FALLBACK")
        mock_weasy.assert_called_once()
        mock_xhtml.assert_called_once()

    @patch("core.utils.pdf._render_with_xhtml2pdf", return_value=None)
    @patch("core.utils.pdf._render_with_weasyprint", return_value=None)
    def test_raises_when_no_renderer_available(self, mock_weasy, mock_xhtml) -> None:
        with self.assertRaises(RuntimeError):
            render_html_to_pdf("<p>Hi</p>")

        mock_weasy.assert_called_once()
        mock_xhtml.assert_called_once()

"""
Utilities for rendering HTML templates into PDF documents.
"""
from __future__ import annotations

from io import BytesIO
from typing import Callable

from django.conf import settings


def _render_with_weasyprint(html: str, base_url: str) -> bytes | None:
    try:
        from weasyprint import HTML  # type: ignore
    except (ModuleNotFoundError, OSError):
        return None

    document = HTML(string=html, base_url=base_url)
    return document.write_pdf()


def _render_with_xhtml2pdf(html: str, base_url: str) -> bytes | None:
    try:
        from xhtml2pdf import pisa  # type: ignore
    except ModuleNotFoundError:
        return None

    # xhtml2pdf cannot resolve relative paths without an explicit link callback.
    link_callback: Callable[[str], str] | None = getattr(settings, "XHTML2PDF_LINK_CALLBACK", None)

    output = BytesIO()
    result = pisa.CreatePDF(
        html,
        dest=output,
        encoding="utf-8",
        link_callback=link_callback,
        default_css=None,
        path=base_url,
    )
    if result.err:
        raise RuntimeError("Failed to render PDF via xhtml2pdf")
    return output.getvalue()


def render_html_to_pdf(html: str) -> bytes:
    """
    Render HTML markup to a PDF document.

    Prefers WeasyPrint when available, and falls back to xhtml2pdf.
    """
    if not isinstance(html, str):
        raise TypeError("HTML content must be a string")

    normalized_html = html.strip()
    if not normalized_html:
        return b""

    base_dir = getattr(settings, "BASE_DIR", ".")
    base_url = str(base_dir)

    rendered = _render_with_weasyprint(normalized_html, base_url)
    if rendered is None:
        rendered = _render_with_xhtml2pdf(normalized_html, base_url)

    if rendered is None:
        raise RuntimeError("Unable to render PDF - install WeasyPrint or xhtml2pdf.")

    return rendered

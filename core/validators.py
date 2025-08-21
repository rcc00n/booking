# core/validators.py
import re
from django.core.exceptions import ValidationError

PHONE_RE = re.compile(r"^\+?\d{10,15}$")      # «+» необязателен, 10-15 цифр
_CANADA_PC_PART = r"[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]"
ALBERTA_POSTAL_RE = re.compile(rf"^T\d{_CANADA_PC_PART[1:]}[ ]?\d[ABCEGHJ-NPRSTV-Z]\d$", re.IGNORECASE)

def clean_phone(value):
    """Проверяет, что телефон соответствует международному формату."""
    if not PHONE_RE.fullmatch(value):
        raise ValidationError("Введите телефон в формате +79991234567")
    return value


def clean_ab_postal_code(value: str) -> str:
    if not value:
        return ""
    raw = value.strip().upper().replace(" ", "")
    # допустим только 6 символов и первая — T
    if len(raw) != 6 or raw[0] != "T":
        raise ValidationError("Enter a valid Alberta postal code (e.g. T2X1A1).")
    # строгая проверка канадского формата
    if not re.match(r"^[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]\d$", raw):
        raise ValidationError("Enter a valid Alberta postal code (e.g. T2X1A1).")
    return raw
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Tuple

from django import forms
from django.core.validators import RegexValidator


def _as_decimal(value: Any) -> Decimal | None:
    if value in (None, "", [], ()):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _default_schema() -> Dict[str, Any]:
    return {"sections": [], "meta": {}}


def _build_choices(raw: Iterable[dict]) -> List[Tuple[str, str]]:
    choices: List[Tuple[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        label = item.get("label")
        if value in (None, "") or label in (None, ""):
            continue
        choices.append((str(value), str(label)))
    return choices


def _resolve_initial(field_cfg: dict, provided_initial: dict | None) -> Any:
    key = field_cfg.get("key")
    provided_val = (provided_initial or {}).get(key)
    if provided_val not in (None, ""):
        return provided_val

    default = field_cfg.get("default", None)
    if default not in (None, ""):
        return default

    # For checkbox widgets, default to False if nothing specified
    if field_cfg.get("type") == "boolean":
        return bool(default)
    return provided_val


def _attach_placeholder(widget, placeholder: str | None):
    if not placeholder:
        return
    if hasattr(widget, "attrs"):
        widget.attrs["placeholder"] = placeholder


def _attach_widget_width(widget, display_cfg: dict | None):
    if not display_cfg:
        return
    width = display_cfg.get("width")
    if width and hasattr(widget, "attrs"):
        widget.attrs.setdefault("data-width", width)


def _charfield(field_cfg: dict, kwargs: dict) -> forms.Field:
    settings = field_cfg.get("settings") or {}
    min_length = settings.get("min_length")
    max_length = settings.get("max_length")
    pattern = settings.get("pattern")

    if min_length is not None:
        kwargs["min_length"] = int(min_length)
    if max_length is not None:
        kwargs["max_length"] = int(max_length)

    field = forms.CharField(**kwargs)
    if pattern:
        field.validators.append(RegexValidator(pattern, message=settings.get("pattern_message") or "Invalid format."))
    return field


def _number_field(field_cfg: dict, kwargs: dict) -> forms.Field:
    settings = field_cfg.get("settings") or {}
    min_value = settings.get("min_value")
    max_value = settings.get("max_value")

    if min_value not in (None, ""):
        kwargs["min_value"] = int(min_value)
    if max_value not in (None, ""):
        kwargs["max_value"] = int(max_value)
    return forms.IntegerField(**kwargs)


def _decimal_field(field_cfg: dict, kwargs: dict) -> forms.Field:
    settings = field_cfg.get("settings") or {}
    min_value = _as_decimal(settings.get("min_value"))
    max_value = _as_decimal(settings.get("max_value"))
    decimal_places = settings.get("decimal_places", 2)
    max_digits = settings.get("max_digits", 10)

    kwargs["decimal_places"] = int(decimal_places)
    kwargs["max_digits"] = int(max_digits)
    if min_value is not None:
        kwargs["min_value"] = min_value
    if max_value is not None:
        kwargs["max_value"] = max_value
    return forms.DecimalField(**kwargs)


def _choice_field(field_cfg: dict, kwargs: dict, *, multiple: bool = False, as_radio: bool = False) -> forms.Field:
    choices = _build_choices(field_cfg.get("choices") or [])
    kwargs["choices"] = choices

    widget_cls = forms.SelectMultiple if multiple else (forms.RadioSelect if as_radio else forms.Select)
    widget = widget_cls()
    _attach_placeholder(widget, field_cfg.get("placeholder"))
    _attach_widget_width(widget, field_cfg.get("display"))

    kwargs.setdefault("widget", widget)
    if multiple:
        return forms.MultipleChoiceField(**kwargs)
    return forms.ChoiceField(**kwargs)


def build_intake_form(
    *,
    intake_form,
    data: dict | None = None,
    files=None,
    initial: dict | None = None,
    client=None,
    prefix: str | None = None,
) -> forms.Form:
    """
    Create a bound/unbound Django form instance based on the stored intake schema.
    """
    schema = intake_form.normalized_schema()
    if not schema:
        schema = _default_schema()

    provided_initial = initial.copy() if initial else {}

    fields = {}
    # Build fields in deterministic order (sections order, then fields order)
    for section in schema.get("sections", []):
        for field_cfg in section.get("fields", []):
            if not isinstance(field_cfg, dict):
                continue
            key = field_cfg.get("key")
            if not key:
                continue

            field_type = (field_cfg.get("type") or "text").lower()
            label = field_cfg.get("label") or key.replace("_", " ").title()
            help_text = field_cfg.get("help_text") or ""
            required = bool(field_cfg.get("required", False))

            field_kwargs = {
                "label": label,
                "required": required,
                "help_text": help_text,
            }

            placeholder = field_cfg.get("placeholder")
            display_cfg = field_cfg.get("display")

            if field_type in {"text", "short_text"}:
                field = _charfield(field_cfg, field_kwargs)
                _attach_placeholder(field.widget, placeholder)
                _attach_widget_width(field.widget, display_cfg)
            elif field_type in {"textarea", "long_text"}:
                field_kwargs["widget"] = forms.Textarea()
                field = _charfield(field_cfg, field_kwargs)
                _attach_placeholder(field.widget, placeholder)
                _attach_widget_width(field.widget, display_cfg)
            elif field_type in {"number", "integer"}:
                field = _number_field(field_cfg, field_kwargs)
                _attach_placeholder(field.widget, placeholder)
                _attach_widget_width(field.widget, display_cfg)
            elif field_type in {"decimal", "float"}:
                field = _decimal_field(field_cfg, field_kwargs)
                _attach_placeholder(field.widget, placeholder)
                _attach_widget_width(field.widget, display_cfg)
            elif field_type in {"boolean", "checkbox"}:
                field = forms.BooleanField(**field_kwargs)
                _attach_widget_width(field.widget, display_cfg)
            elif field_type == "email":
                field = forms.EmailField(**field_kwargs)
                _attach_placeholder(field.widget, placeholder)
                _attach_widget_width(field.widget, display_cfg)
            elif field_type in {"phone", "tel"}:
                field = forms.CharField(**field_kwargs)
                field.validators.append(
                    RegexValidator(
                        r"^\+?[0-9\-\s\(\)]+$",
                        message=field_cfg.get("settings", {}).get("pattern_message", "Enter a valid phone number."),
                    )
                )
                _attach_placeholder(field.widget, placeholder)
                _attach_widget_width(field.widget, display_cfg)
            elif field_type == "select":
                field = _choice_field(field_cfg, field_kwargs, multiple=False, as_radio=False)
            elif field_type in {"radio", "radiolist"}:
                field = _choice_field(field_cfg, field_kwargs, multiple=False, as_radio=True)
            elif field_type in {"multiselect", "multichoice"}:
                field = _choice_field(field_cfg, field_kwargs, multiple=True, as_radio=False)
            elif field_type == "date":
                widget = forms.DateInput(attrs={"type": "date"})
                field_kwargs["widget"] = widget
                field = forms.DateField(**field_kwargs)
            elif field_type == "time":
                widget = forms.TimeInput(attrs={"type": "time"})
                field_kwargs["widget"] = widget
                field = forms.TimeField(**field_kwargs)
            elif field_type in {"datetime", "datetime_local"}:
                widget = forms.DateTimeInput(attrs={"type": "datetime-local"})
                field_kwargs["widget"] = widget
                field = forms.DateTimeField(**field_kwargs)
            elif field_type == "file":
                field = forms.FileField(**field_kwargs)
            else:
                # Fallback to CharField
                field = _charfield(field_cfg, field_kwargs)
                _attach_placeholder(field.widget, placeholder)
                _attach_widget_width(field.widget, display_cfg)

            initial_value = _resolve_initial(field_cfg, provided_initial)
            if initial_value not in (None, ""):
                field.initial = initial_value

            fields[key] = field

    form_class = type(
        f"DynamicIntakeForm{intake_form.pk}",
        (forms.Form,),
        fields,
    )

    form = form_class(
        data or None,
        files=files or None,
        initial=provided_initial,
        prefix=prefix,
    )
    form.intake_schema = schema
    return form

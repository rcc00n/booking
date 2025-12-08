import hashlib
import json
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.formats import number_format
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from core.utils.admin_perms import is_master

register = template.Library()

@register.filter
def add_class(field, css):
    return field.as_widget(attrs={**field.field.widget.attrs, "class": css})

@register.filter
def getfield(form, name):
    try:
        return form[name]
    except Exception:
        return None

@register.filter
def lookup(mapping, key):
    try:
        return mapping.get(key)
    except Exception:
        return None

@register.filter
def is_master_user(user):
    return is_master(user)

@register.filter
def color_index(value, mod=8):
    """
    Дет-рандом: по значению (pk/uuid/email) считаем md5 и берём индекс 0..mod-1.
    Используй с заранее заданной палитрой цветов в CSS.
    """
    if value is None:
        value = ""
    s = str(value).encode("utf-8")
    h = hashlib.md5(s).hexdigest()
    return int(h[:8], 16) % int(mod or 8)

@register.filter
def service_duration(service):
    base = getattr(service, "duration_min", 0) or 0
    extra = getattr(service, "extra_time_min", 0) or 0
    total = base + extra
    hours, minutes = divmod(total, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}min")
    return ' '.join(parts) if parts else "0min"

@register.filter
def service_price(service):
    price = getattr(service, "base_price", None) or 0
    return number_format(price, decimal_pos=2)

@register.filter
def subtract(value, arg):
    """
    Perform safe subtraction that tolerates None and string inputs.
    """
    def _as_decimal(val):
        if val in (None, ""):
            return Decimal("0")
        if isinstance(val, Decimal):
            return val
        try:
            return Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    return _as_decimal(value) - _as_decimal(arg)

@register.simple_tag
def changelist_start(cl):
    if not getattr(cl, "result_count", 0):
        return 0
    if getattr(cl, "show_all", False):
        return 1 if cl.result_list else 0
    return (cl.list_per_page * (cl.page_num - 1)) + 1

@register.simple_tag
def changelist_end(cl):
    if not getattr(cl, "result_count", 0):
        return 0
    if getattr(cl, "show_all", False):
        return cl.result_count
    start = changelist_start(cl)
    return start + len(cl.result_list) - 1 if cl.result_list else 0

@register.simple_tag(takes_context=True)
def changelist_page_url(context, page_number):
    request = context.get("request")
    if request is None:
        return ""

    params = request.GET.copy()
    if page_number in (None, ""):
        page_number = 0
    else:
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 0

    if page_number <= 1:
        params.pop("p", None)
    else:
        params["p"] = page_number

    query_string = params.urlencode()
    if query_string:
        return f"{request.path}?{query_string}"
    return request.path


def _format_decimal(value):
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal("0.01")))
    try:
        return format(Decimal(str(value)).quantize(Decimal("0.01")))
    except (InvalidOperation, TypeError, ValueError):
        return "0"


@register.filter
def service_payload(service):
    """
    Build a serializable payload with the metadata we need on the catalog cards.
    """
    if not service:
        return {}
    try:
        discount = service.get_active_discount()
    except Exception:
        discount = None

    description = strip_tags(getattr(service, "description", "") or "").strip()
    price = service.get_discounted_price() if discount else getattr(service, "base_price", None)

    forms = []
    forms_source = []
    get_forms = getattr(service, "active_forms", None)
    if callable(get_forms):
        try:
            forms_source = list(get_forms())
        except Exception:
            forms_source = []
    if not forms_source:
        prefetched = getattr(service, "_prefetched_objects_cache", {})
        if prefetched and "pre_appointment_forms" in prefetched:
            forms_source = prefetched["pre_appointment_forms"]
        else:
            manager = getattr(service, "pre_appointment_forms", None)
            if hasattr(manager, "all"):
                forms_source = list(manager.all())
            else:
                forms_source = []

    for form in forms_source or []:
        forms.append(
            {
                "id": str(getattr(form, "id", "")),
                "name": getattr(form, "name", "") or "",
                "slug": getattr(form, "slug", "") or "",
            }
        )

    payload = {
        "id": str(getattr(service, "pk", "")),
        "name": getattr(service, "name", "") or "",
        "category": getattr(getattr(service, "category", None), "name", "") or "",
        "category_id": getattr(service, "category_id", None) or "",
        "description": description,
        "duration_min": getattr(service, "duration_min", 0) or 0,
        "extra_time_min": getattr(service, "extra_time_min", 0) or 0,
        "base_price": _format_decimal(getattr(service, "base_price", None)),
        "price": _format_decimal(price),
        "discount_percent": getattr(discount, "discount_percent", None),
        "image": getattr(service, "card_image_url", None) or "",
        "image_alt": getattr(service, "card_image_alt", None) or (getattr(service, "name", "") or ""),
        "forms": forms,
    }
    return payload


@register.filter
def as_json(value):
    """
    Serialize the provided value into JSON that is safe to embed inside <script type="application/json"> tags.
    """
    try:
        data = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        data = json.dumps(str(value), ensure_ascii=False)
    data = data.replace("</", "<\\/")
    return mark_safe(data)

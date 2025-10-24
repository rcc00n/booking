import hashlib
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.formats import number_format

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

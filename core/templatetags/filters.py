import hashlib

from django import template
from core.utils.admin_perms import is_master
register = template.Library()

@register.filter
def add_class(field, css):
    return field.as_widget(attrs={**field.field.widget.attrs, "class": css})

@register.filter
def getfield(form, name):
    try: return form[name]
    except Exception: return None

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
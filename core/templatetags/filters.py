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
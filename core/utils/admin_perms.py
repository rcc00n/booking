# core/utils/admin_perms.py
from django.contrib.auth.models import User
from core.models import MasterProfile  # подстройте импорт

def is_master(user: User) -> bool:
    try:
        userprof = getattr(user, "userprofile", None)
        return getattr(userprof, "master_profile", None) if userprof else False
    except MasterProfile.DoesNotExist:
        return False

def master_obj(user: User) -> MasterProfile | None:
    return getattr(user, "masterprofile", None) if is_master(user) else None

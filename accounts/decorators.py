from django.core.exceptions import PermissionDenied

def role_required(role_name):
    """
    Ограничивает доступ к CBV/FBV только пользователям с указанной ролью.
    Usage:
        @role_required('Client')
        def view(request): ...
    """
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            if request.user.is_authenticated and \
               request.user.userrole_set.filter(role__name=role_name).exists():
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped
    return decorator

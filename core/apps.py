# core/apps.py
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import core.signals  # noqa
        from django.db.models.signals import post_migrate
        from .signals import ensure_payment_statuses
        post_migrate.connect(ensure_payment_statuses, sender=self)




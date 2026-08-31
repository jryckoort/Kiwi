from django.apps import AppConfig


class TaxesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.taxes"

    def ready(self):
        from . import signals  # noqa: F401

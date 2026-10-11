from django.apps import AppConfig


class InvestingConfig(AppConfig):
    name = 'investing'

    def ready(self):
        from . import signals  # noqa: F401

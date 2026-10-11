from django.apps import AppConfig


class SavingsConfig(AppConfig):
    name = 'savings'

    def ready(self):
        from . import signals  # noqa: F401

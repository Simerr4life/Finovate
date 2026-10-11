import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AssistantConfig(AppConfig):
    name = "assistant"

    def ready(self):
        from django.conf import settings

        project_id = getattr(settings, "IMESSAGE_PROJECT_ID", "")
        project_secret = getattr(settings, "IMESSAGE_PROJECT_SECRET", "")
        webhook_secret = getattr(settings, "IMESSAGE_WEBHOOK_SECRET", "") or getattr(settings, "PHOTON_WEBHOOK_SECRET", "")
        if (project_id or project_secret) and not webhook_secret:
            logger.error(
                "Photon Spectrum project credentials are set but IMESSAGE_WEBHOOK_SECRET is missing. "
                "Inbound webhooks will be rejected."
            )

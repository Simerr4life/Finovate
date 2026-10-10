from django.conf import settings


def app_context(request):
    """Expose a few safe, non-secret settings to every template."""
    return {
        "FINOVATE_DEMO_MODE": settings.FINOVATE_DEMO_MODE,
    }

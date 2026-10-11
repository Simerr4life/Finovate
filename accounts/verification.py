"""Server-side Auth0 verification email resend.

The management token stays in the Django cache. It is never written to a
browser cookie, a template, or local storage.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def management_configured():
    return bool(
        settings.AUTH0_DOMAIN
        and settings.AUTH0_CLIENT_ID
        and settings.AUTH0_MGMT_CLIENT_ID
        and settings.AUTH0_MGMT_CLIENT_SECRET
    )


def resend_verification_email(auth0_sub):
    """Ask Auth0 to send another verification email. Returns sent, not_configured, or failed."""
    if not management_configured() or not auth0_sub:
        return "not_configured"
    token = _management_token()
    if not token:
        return "failed"
    body = json.dumps({"user_id": auth0_sub, "client_id": settings.AUTH0_CLIENT_ID}).encode()
    request = urllib.request.Request(
        f"https://{settings.AUTH0_DOMAIN}/api/v2/jobs/verification-email",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status in (200, 201):
                return "sent"
    except urllib.error.HTTPError:
        logger.warning("auth0 verification email resend was rejected")
    except Exception:
        logger.warning("auth0 verification email resend failed")
    return "failed"


def _management_token():
    cached = cache.get("auth0-mgmt-token")
    if cached:
        return cached
    body = json.dumps(
        {
            "grant_type": "client_credentials",
            "client_id": settings.AUTH0_MGMT_CLIENT_ID,
            "client_secret": settings.AUTH0_MGMT_CLIENT_SECRET,
            "audience": f"https://{settings.AUTH0_DOMAIN}/api/v2/",
        }
    ).encode()
    request = urllib.request.Request(
        f"https://{settings.AUTH0_DOMAIN}/oauth/token",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.warning("auth0 management token request failed")
        return ""
    token = payload.get("access_token") or ""
    if not token:
        return ""
    timeout = max(int(payload.get("expires_in") or 300) - 60, 30)
    cache.set("auth0-mgmt-token", token, timeout)
    return token

"""Auth0 email verification helpers (Management API + resend).

Finovate never marks an email verified from a client flag alone. After the
user clicks Auth0's link, Auth0 updates email_verified on the user record;
this module re-reads that authoritative value and updates Profile.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .identity import VERIFICATION_COMPLETED, VERIFICATION_PENDING

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


def fetch_auth0_user(auth0_sub: str) -> dict | None:
    """Return the Auth0 Management API user object, or None on failure."""
    if not management_configured() or not auth0_sub:
        return None
    token = _management_token()
    if not token:
        return None
    encoded = urllib.parse.quote(auth0_sub, safe="")
    request = urllib.request.Request(
        f"https://{settings.AUTH0_DOMAIN}/api/v2/users/{encoded}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        logger.warning("auth0 user fetch rejected status=%s", exc.code)
        return None
    except Exception:
        logger.warning("auth0 user fetch failed")
        return None
    if not isinstance(payload, dict) or not payload.get("user_id"):
        return None
    return payload


def apply_authoritative_verification(profile) -> str:
    """Refresh Profile.email_verified from Auth0 Management API.

    Returns one of: verified, still_pending, already_verified, unavailable.
    Never downgrades a previously confirmed verification.
    """
    if profile.email_verified:
        return "already_verified"
    auth0_sub = (profile.auth0_sub or "").strip()
    if not auth0_sub:
        return "unavailable"
    if not management_configured():
        # Without Management API credentials the email-link path needs a
        # fresh login (max_age=0). Do not claim Auth0 is unreachable.
        return "still_pending"
    remote = fetch_auth0_user(auth0_sub)
    if remote is None:
        return "unavailable"
    if remote.get("email_verified") is not True:
        return "still_pending"

    with transaction.atomic():
        locked = type(profile).objects.select_for_update().select_related("user").get(pk=profile.pk)
        if locked.email_verified:
            return "already_verified"
        locked.email_verified = True
        locked.identity_status = VERIFICATION_COMPLETED
        email = (remote.get("email") or "").strip()
        update_fields = ["email_verified", "identity_status", "updated_at"]
        if email and locked.user.email != email:
            locked.user.email = email[:254]
            locked.user.save(update_fields=["email"])
        locked.save(update_fields=update_fields)

    try:
        from .auth0_backup import enqueue_backup_sync

        enqueue_backup_sync(auth0_sub, reason="email_verified")
    except Exception:
        logger.warning("auth0 backup enqueue after verification failed")
    return "verified"


def mark_verified_from_trusted_claims(profile, claims: dict) -> bool:
    """Upgrade verification from a fresh Auth0 ID-token/userinfo claim set.

    Returns True when this call flipped the profile to verified.
    """
    if claims.get("email_verified") is not True:
        return False
    if profile.email_verified:
        return False
    with transaction.atomic():
        locked = type(profile).objects.select_for_update().get(pk=profile.pk)
        if locked.email_verified:
            return False
        locked.email_verified = True
        locked.identity_status = VERIFICATION_COMPLETED
        locked.save(update_fields=["email_verified", "identity_status", "updated_at"])
    try:
        from .auth0_backup import enqueue_backup_sync

        enqueue_backup_sync(profile.auth0_sub, reason="email_verified_claim")
    except Exception:
        logger.warning("auth0 backup enqueue after claim verification failed")
    return True


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

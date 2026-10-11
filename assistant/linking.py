"""Bind a Spectrum chat to a Finovate user with a one-time code.

The code is shown only inside an authenticated Settings session. It is
stored as a SHA-256 hash, expires quickly, and can be used once. A phone
number is never the identity key.
"""

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import Profile

from .models import MessagingLinkCode

LINK_CODE_TTL = timedelta(minutes=15)


def _hash_code(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def issue_link_code(user) -> str:
    """Replace any unused code for this user and return a new plaintext code."""
    MessagingLinkCode.objects.filter(user=user, used_at__isnull=True).delete()
    raw = secrets.token_urlsafe(9)
    MessagingLinkCode.objects.create(
        user=user,
        code_hash=_hash_code(raw),
        expires_at=timezone.now() + LINK_CODE_TTL,
    )
    return raw


def code_is_active(user, raw: str) -> bool:
    if not raw:
        return False
    return MessagingLinkCode.objects.filter(
        user=user,
        code_hash=_hash_code(raw),
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).exists()


def redeem_link_code(raw: str, chat_id: str):
    """Bind chat_id to the code's user, or return None without saying why."""
    if not raw or not chat_id or len(raw) > 80 or len(chat_id) > 120:
        return None
    now = timezone.now()
    with transaction.atomic():
        code = (
            MessagingLinkCode.objects.select_for_update()
            .filter(code_hash=_hash_code(raw), used_at__isnull=True, expires_at__gt=now)
            .select_related("user")
            .first()
        )
        if code is None:
            return None
        profile = Profile.objects.select_for_update().get(user=code.user)
        if profile.photon_chat_id and profile.photon_chat_id != chat_id:
            return None
        if Profile.objects.filter(photon_chat_id=chat_id).exclude(pk=profile.pk).exists():
            return None
        code.used_at = now
        code.save(update_fields=["used_at", "updated_at"])
        profile.photon_chat_id = chat_id
        profile.messaging_linked_at = now
        profile.save(update_fields=["photon_chat_id", "messaging_linked_at", "updated_at"])
        return code.user

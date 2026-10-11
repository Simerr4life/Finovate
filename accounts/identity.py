"""Map an Auth0 subject onto exactly one Finovate profile.

Auth0 is the identity provider. Email and phone are contact claims, never
the lookup key, and a matching email never merges two accounts.
"""

import logging
import re
from urllib.parse import urlsplit

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from .models import NotificationEvent, Profile

logger = logging.getLogger(__name__)

REGISTRATION_STARTED = "registration_started"
ACCOUNT_CREATED = "account_created"
VERIFICATION_PENDING = "verification_pending"
VERIFICATION_COMPLETED = "verification_completed"
AUTHENTICATION_SUCCESSFUL = "authentication_successful"
AUTHENTICATION_FAILED = "authentication_failed"
ACCOUNT_BLOCKED = "blocked"

_PHONE_CHARS = re.compile(r"^[0-9+().\-\s]{8,20}$")


def safe_next(value):
    """Return a same-site path, or an empty string when it could redirect off-site."""
    if not isinstance(value, str):
        return ""
    candidate = value.strip()
    if not candidate.startswith("/") or candidate.startswith("//") or candidate.startswith("/\\"):
        return ""
    if "\\" in candidate or "://" in candidate or candidate.startswith("/\\"):
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc:
        return ""
    return candidate


def normalize_phone(value):
    """Keep a typed phone number for later contact. This does not verify it."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if not _PHONE_CHARS.match(raw):
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 8 or len(digits) > 15:
        return None
    return raw


def destination_for(user, nxt=""):
    profile = getattr(user, "profile", None)
    if profile is None:
        return reverse("dashboard")
    if profile.auth0_sub and not profile.email_verified:
        return reverse("accounts:verify")
    if not profile.onboarding_completed:
        return reverse("accounts:onboarding")
    return safe_next(nxt) or reverse("dashboard")


def _username_for(sub, attempt):
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in sub)
    base = f"auth0_{cleaned}"[:140]
    if attempt:
        suffix = f"_{attempt}"
        base = base[: 150 - len(suffix)] + suffix
    return base or "auth0_user"


def _apply_name(user, claims, pending_name):
    given = (claims.get("given_name") or "").strip()
    family = (claims.get("family_name") or "").strip()
    full = (claims.get("name") or pending_name or "").strip()
    if full and not given:
        parts = full.split()
        given = parts[0]
        family = " ".join(parts[1:])
    if given:
        user.first_name = given[:150]
    if family:
        user.last_name = family[:150]


def _verified_flag(claims, key):
    return claims.get(key) is True


def access_token_expiry(result, audience):
    state = (result or {}).get("state_data") or {}
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    token_sets = state.get("token_sets") or []
    expiries = []
    for item in token_sets:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if audience and item.get("audience") != audience:
            continue
        expires_at = item.get("expires_at")
        if expires_at:
            expiries.append(int(expires_at))
    return max(expiries) if expiries else None


def claims_from_login_result(result):
    state = (result or {}).get("state_data") or {}
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    user = state.get("user") or {}
    if hasattr(user, "model_dump"):
        user = user.model_dump()
    return user


def attempt_messaging_welcome(user):
    """Best-effort welcome delivery. A provider outage must not undo the account.

    Welcome pushes still go through the Spectrum adapter when linked.
    This hook stays best-effort so a provider outage cannot undo signup.
    """
    profile = user.profile
    if not (profile.phone_verified and profile.messaging_consent and profile.photon_chat_id):
        return "skipped"
    return "not_delivered"


def _record_welcome(profile):
    if not profile.email_verified or profile.welcome_recorded_at:
        return
    with transaction.atomic():
        locked = Profile.objects.select_for_update().get(pk=profile.pk)
        if locked.welcome_recorded_at or not locked.email_verified:
            return
        NotificationEvent.objects.create(
            user=locked.user,
            event_type=NotificationEvent.EventType.WELCOME,
            message="Welcome to Finovate.",
            delivery_status="recorded",
        )
        try:
            attempt_messaging_welcome(locked.user)
        except Exception:
            logger.exception("welcome messaging provider failed")
        locked.welcome_recorded_at = timezone.now()
        locked.save(update_fields=["welcome_recorded_at", "updated_at"])


def sync_profile_from_claims(claims, pending=None):
    """Create or fetch the profile for this Auth0 subject. Safe to retry."""
    sub = (claims.get("sub") or "").strip()
    if not sub:
        raise ValueError("missing sub")
    pending = pending or {}
    email_verified = _verified_flag(claims, "email_verified")
    phone_verified = _verified_flag(claims, "phone_number_verified")
    status = VERIFICATION_COMPLETED if email_verified else VERIFICATION_PENDING
    email = (claims.get("email") or "")[:254]
    verified_phone = (claims.get("phone_number") or "").strip() if phone_verified else ""

    profile = Profile.objects.filter(auth0_sub=sub).select_related("user").first()
    created = False
    if profile is None:
        profile, created = _create_profile(
            sub, email, claims, pending, status, email_verified, phone_verified, verified_phone
        )
    if not created:
        user = profile.user
        _apply_name(user, claims, pending.get("name") or "")
        if email:
            user.email = email
        user.save()
        if phone_verified and verified_phone:
            profile.phone_number = verified_phone[:20]
            profile.phone_verified = True
        elif pending.get("phone") and not profile.phone_number:
            profile.phone_number = pending["phone"][:20]
        profile.email_verified = email_verified
        profile.identity_status = status
        profile.save()

    _record_welcome(profile)
    profile.refresh_from_db()
    return profile, created


def _create_profile(sub, email, claims, pending, status, email_verified, phone_verified, verified_phone):
    last_error = None
    for attempt in range(3):
        try:
            with transaction.atomic():
                user = User(username=_username_for(sub, attempt), email=email)
                user.set_unusable_password()
                _apply_name(user, claims, pending.get("name") or "")
                user.save()
                profile = user.profile
                profile.auth0_sub = sub
                profile.email_verified = email_verified
                profile.phone_verified = phone_verified
                profile.identity_status = status
                profile.account_created_at = timezone.now()
                if phone_verified and verified_phone:
                    profile.phone_number = verified_phone[:20]
                elif pending.get("phone"):
                    profile.phone_number = pending["phone"][:20]
                profile.save()
                NotificationEvent.objects.create(
                    user=user,
                    event_type=NotificationEvent.EventType.ACCOUNT_CREATED,
                    message="Finovate profile created for a new Auth0 identity.",
                    delivery_status="recorded",
                )
            return profile, True
        except IntegrityError as exc:
            last_error = exc
            existing = Profile.objects.filter(auth0_sub=sub).select_related("user").first()
            if existing is not None:
                return existing, False
    raise last_error

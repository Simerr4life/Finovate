"""Supabase Auth as Finovate's email-and-password sign-in.

Passwords are sent to Supabase over TLS from the server and are never
stored by Finovate. A Supabase user id maps to exactly one profile through
Profile.supabase_uid; an email address is never used to join accounts.

Accounts that predate Supabase still hold a Django password hash. That hash
cannot be imported into Supabase, so the password moves the first time the
person logs in with it (see migrate_legacy_password).
"""

import json
import logging
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Profile

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "invalid_credentials"
EMAIL_NOT_CONFIRMED = "email_not_confirmed"
WEAK_PASSWORD = "weak_password"
RATE_LIMITED = "rate_limited"
UNAVAILABLE = "unavailable"


class SupabaseAuthError(Exception):
    def __init__(self, code, message=""):
        super().__init__(code)
        self.code = code
        self.message = message


def supabase_configured() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_PUBLIC_KEY)


def admin_configured() -> bool:
    return bool(supabase_configured() and settings.SUPABASE_SERVICE_KEY)


def _request(method, path, body=None, admin=False):
    key = settings.SUPABASE_SERVICE_KEY if admin else settings.SUPABASE_PUBLIC_KEY
    request = urllib.request.Request(
        settings.SUPABASE_URL.rstrip("/") + "/auth/v1" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8") or "{}")
        except Exception:
            payload = {}
        code = str(payload.get("error_code") or payload.get("error") or "")
        if exc.code == 429:
            code = RATE_LIMITED
        elif code in ("invalid_grant",):
            code = INVALID_CREDENTIALS
        elif code not in (INVALID_CREDENTIALS, EMAIL_NOT_CONFIRMED, WEAK_PASSWORD):
            logger.warning("supabase auth request rejected status=%s code=%s", exc.code, code or "unknown")
            code = code or UNAVAILABLE
        raise SupabaseAuthError(code, str(payload.get("msg") or "")) from None
    except Exception:
        logger.warning("supabase auth request failed")
        raise SupabaseAuthError(UNAVAILABLE) from None


def sign_up(email, password, name=""):
    """Register with Supabase. Returns the Supabase user when a session was
    issued straight away, or None when the person must confirm their email
    first. No profile is linked until a real sign-in succeeds, because
    Supabase answers an already-registered email with a placeholder user.
    """
    payload = _request("POST", "/signup", {"email": email, "password": password, "data": {"name": name}})
    if payload.get("access_token") and isinstance(payload.get("user"), dict):
        return payload["user"]
    return None


def sign_in(email, password):
    payload = _request("POST", "/token?grant_type=password", {"email": email, "password": password})
    user = payload.get("user")
    if not payload.get("access_token") or not isinstance(user, dict) or not user.get("id"):
        raise SupabaseAuthError(UNAVAILABLE)
    return user


def profile_for_supabase_user(supabase_user):
    """Fetch or create the one profile for this Supabase user id."""
    uid = uuid.UUID(str(supabase_user["id"]))
    email = (supabase_user.get("email") or "")[:254]
    confirmed = bool(supabase_user.get("email_confirmed_at") or supabase_user.get("confirmed_at"))
    profile = Profile.objects.filter(supabase_uid=uid).select_related("user").first()
    if profile is None:
        name = ((supabase_user.get("user_metadata") or {}).get("name") or "").strip()
        try:
            with transaction.atomic():
                user = User(username=f"supabase_{uid.hex}", email=email)
                user.set_unusable_password()
                if name:
                    parts = name.split()
                    user.first_name = parts[0][:150]
                    user.last_name = " ".join(parts[1:])[:150]
                user.save()
                profile = user.profile
                profile.supabase_uid = uid
                profile.account_created_at = timezone.now()
        except IntegrityError:
            profile = Profile.objects.select_related("user").get(supabase_uid=uid)
    profile.email_verified = confirmed
    profile.identity_status = "verification_completed" if confirmed else "verification_pending"
    profile.save()
    return profile


def legacy_user_for(identifier, password):
    """A pre-Supabase account whose Django password matches, or None.
    Accepts the old username or the account's email."""
    identifier = (identifier or "").strip()
    if not identifier or not password:
        return None
    lookup = {"email__iexact": identifier} if "@" in identifier else {"username": identifier}
    matches = list(User.objects.filter(**lookup).select_related("profile")[:2])
    if len(matches) != 1:
        return None
    user = matches[0]
    if not user.has_usable_password() or not user.check_password(password):
        return None
    return user


def migrate_legacy_password(user, password):
    """Give a pre-Supabase account its password in Supabase. Returns True
    once the account can sign in through Supabase, at which point the
    Django copy of the password is dropped.

    The email is never marked confirmed here: Finovate did not verify it.
    Supabase sends its own confirmation email, and until the person uses
    it the old Django password keeps working and this returns False.
    Needs the server-side service key; without it nothing changes.
    """
    if not admin_configured() or not user.email:
        return False
    profile = user.profile
    try:
        if profile.supabase_uid:
            _request("PUT", f"/admin/users/{profile.supabase_uid}", {"password": password}, admin=True)
        else:
            created = _request(
                "POST",
                "/admin/users",
                {"email": user.email, "password": password, "email_confirm": False},
                admin=True,
            )
            profile.supabase_uid = uuid.UUID(str(created["id"]))
            profile.save(update_fields=["supabase_uid", "updated_at"])
            _request("POST", "/resend", {"type": "signup", "email": user.email})
        supabase_user = sign_in(user.email, password)
    except (SupabaseAuthError, KeyError, ValueError):
        logger.warning("legacy password migration did not complete")
        return False
    user.set_unusable_password()
    user.save(update_fields=["password"])
    profile_for_supabase_user(supabase_user)
    return True

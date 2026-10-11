"""Idempotent Auth0 → Supabase (Django/Postgres) signup backup sync.

Writes go through the Django ORM into the same database Supabase hosts when
DATABASE_URL/SUPABASE_DB_URL is set. Privileged credentials never leave the
server. Failures are recorded on the row and retried by process_pending_backups
or the reconcile_auth0_backups management command.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Auth0UserBackup, Profile

logger = logging.getLogger(__name__)

_METADATA_ALLOWLIST = frozenset(
    {
        "given_name",
        "family_name",
        "nickname",
        "locale",
        "picture",
        "connection",
        "identity_status",
        "source",
    }
)


def enqueue_backup_sync(auth0_user_id, reason="event", claims=None, pending=None):
    """Upsert a pending backup row and attempt an immediate sync.

    Safe to call from request paths: a sync failure leaves the row pending/failed
    for later retry and never raises to the caller.
    """
    auth0_user_id = (auth0_user_id or "").strip()
    if not auth0_user_id:
        return None
    claims = claims or {}
    pending = pending or {}
    try:
        record = _ensure_record(auth0_user_id, claims=claims, pending=pending, reason=reason)
        return process_backup_record(record.pk)
    except Exception:
        logger.warning("auth0 backup enqueue failed reason=%s", reason)
        return None


def upsert_from_auth0_event(payload: dict, source="auth0_action"):
    """Trusted Auth0 Action / webhook payload → idempotent backup upsert."""
    user = payload.get("user") if isinstance(payload.get("user"), dict) else payload
    auth0_user_id = (user.get("user_id") or user.get("sub") or "").strip()
    if not auth0_user_id:
        raise ValueError("missing auth0 user_id")
    claims = {
        "sub": auth0_user_id,
        "email": user.get("email") or "",
        "email_verified": user.get("email_verified") is True,
        "name": user.get("name") or user.get("nickname") or "",
        "given_name": user.get("given_name") or "",
        "family_name": user.get("family_name") or "",
        "nickname": user.get("nickname") or "",
        "locale": user.get("locale") or "",
        "picture": user.get("picture") or "",
        "created_at": user.get("created_at") or user.get("createdAt"),
        "connection": (user.get("identities") or [{}])[0].get("connection")
        if isinstance(user.get("identities"), list) and user.get("identities")
        else user.get("connection") or "",
    }
    record = _ensure_record(auth0_user_id, claims=claims, pending={}, reason=source)
    return process_backup_record(record.pk)


def process_backup_record(pk: int) -> Auth0UserBackup | None:
    """Attempt to mark one backup row as synced. Returns the row or None."""
    try:
        with transaction.atomic():
            record = Auth0UserBackup.objects.select_for_update().get(pk=pk)
            profile = Profile.objects.filter(auth0_sub=record.auth0_user_id).select_related("user").first()
            if profile is not None:
                _merge_from_profile(record, profile)
            record.last_synced_at = timezone.now()
            record.sync_status = Auth0UserBackup.SyncStatus.SYNCED
            record.last_sync_error = ""
            record.save(
                update_fields=[
                    "email",
                    "email_verified",
                    "display_name",
                    "signup_created_at",
                    "profile_metadata",
                    "last_synced_at",
                    "sync_status",
                    "last_sync_error",
                    "updated_at",
                ]
            )
            return record
    except Auth0UserBackup.DoesNotExist:
        return None
    except Exception as exc:
        _mark_failed(pk, exc)
        return None


def process_pending_backups(limit=100) -> dict:
    """Retry pending/failed backup rows. Returns counts for monitoring."""
    qs = Auth0UserBackup.objects.filter(
        sync_status__in=[
            Auth0UserBackup.SyncStatus.PENDING,
            Auth0UserBackup.SyncStatus.FAILED,
        ]
    ).order_by("updated_at")[:limit]
    synced = failed = 0
    for row in qs:
        result = process_backup_record(row.pk)
        if result is not None and result.sync_status == Auth0UserBackup.SyncStatus.SYNCED:
            synced += 1
        else:
            failed += 1
    return {"synced": synced, "failed": failed}


def reconcile_from_profiles(limit=500) -> dict:
    """Ensure every Auth0-linked Profile has a backup row; refresh drift."""
    created = updated = 0
    profiles = (
        Profile.objects.exclude(auth0_sub__isnull=True)
        .exclude(auth0_sub="")
        .select_related("user")
        .order_by("id")[:limit]
    )
    for profile in profiles:
        existing = Auth0UserBackup.objects.filter(auth0_user_id=profile.auth0_sub).first()
        if existing is None:
            enqueue_backup_sync(
                profile.auth0_sub,
                reason="reconcile",
                claims={
                    "sub": profile.auth0_sub,
                    "email": profile.user.email,
                    "email_verified": profile.email_verified,
                    "name": profile.user.get_full_name(),
                },
            )
            created += 1
            continue
        before_verified = existing.email_verified
        before_email = existing.email
        process_backup_record(existing.pk)
        existing.refresh_from_db()
        if existing.email_verified != before_verified or existing.email != before_email:
            updated += 1
    pending = process_pending_backups(limit=limit)
    return {"created": created, "updated": updated, **pending}


def _ensure_record(auth0_user_id, claims, pending, reason):
    email = (claims.get("email") or "")[:254]
    display = (claims.get("name") or pending.get("name") or "")[:255]
    verified = claims.get("email_verified") is True
    created_at = _parse_created(claims.get("created_at"))
    metadata = _allowlisted_metadata(claims, reason)

    with transaction.atomic():
        record, created = Auth0UserBackup.objects.select_for_update().get_or_create(
            auth0_user_id=auth0_user_id,
            defaults={
                "email": email,
                "email_verified": verified,
                "display_name": display,
                "signup_created_at": created_at or timezone.now(),
                "sync_status": Auth0UserBackup.SyncStatus.PENDING,
                "profile_metadata": metadata,
            },
        )
        if created:
            return record
        changed = False
        if email and record.email != email:
            record.email = email
            changed = True
        if display and not record.display_name:
            record.display_name = display
            changed = True
        # Monotonic verification: never overwrite True with False from stale data.
        if verified and not record.email_verified:
            record.email_verified = True
            changed = True
        if created_at and record.signup_created_at is None:
            record.signup_created_at = created_at
            changed = True
        merged_meta = dict(record.profile_metadata or {})
        merged_meta.update(metadata)
        if merged_meta != (record.profile_metadata or {}):
            record.profile_metadata = merged_meta
            changed = True
        if record.sync_status == Auth0UserBackup.SyncStatus.SYNCED and not changed:
            return record
        if record.sync_status != Auth0UserBackup.SyncStatus.PENDING:
            record.sync_status = Auth0UserBackup.SyncStatus.PENDING
            changed = True
        if changed:
            record.save()
        return record


def _merge_from_profile(record: Auth0UserBackup, profile: Profile):
    if profile.user.email:
        record.email = profile.user.email[:254]
    name = profile.user.get_full_name().strip()
    if name:
        record.display_name = name[:255]
    if profile.email_verified:
        record.email_verified = True
    if profile.account_created_at and record.signup_created_at is None:
        record.signup_created_at = profile.account_created_at
    meta = dict(record.profile_metadata or {})
    meta["identity_status"] = profile.identity_status or ""
    meta["source"] = meta.get("source") or "profile"
    record.profile_metadata = {k: v for k, v in meta.items() if k in _METADATA_ALLOWLIST and v}


def _allowlisted_metadata(claims, reason):
    meta = {"source": reason}
    for key in _METADATA_ALLOWLIST:
        value = claims.get(key)
        if value not in (None, ""):
            meta[key] = value if not isinstance(value, str) else value[:500]
    return {k: v for k, v in meta.items() if k in _METADATA_ALLOWLIST}


def _parse_created(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.utc)
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        parsed = parse_datetime(value.replace("Z", "+00:00"))
        if parsed is None:
            return None
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.utc)
        return parsed
    return None


def _mark_failed(pk, exc):
    message = type(exc).__name__
    try:
        Auth0UserBackup.objects.filter(pk=pk).update(
            sync_status=Auth0UserBackup.SyncStatus.FAILED,
            last_sync_error=message[:255],
            updated_at=timezone.now(),
        )
    except Exception:
        logger.warning("auth0 backup could not record failure state")
    logger.warning("auth0 backup sync failed error=%s", message)

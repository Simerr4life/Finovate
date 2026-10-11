"""Guard against the same form being processed twice (double click, retry)."""

from django.core.cache import cache

KEY_TTL_SECONDS = 60 * 60


def claim_submission(request, key: str | None) -> bool:
    """Return True the first time a (user, key) pair is seen, False after.

    ``cache.add`` only writes when the key is absent, so of two concurrent
    requests with the same key exactly one wins. A missing key (an older
    form, or no JavaScript) is always allowed through.
    """
    key = (key or "").strip()
    if not key:
        return True
    user_part = getattr(request.user, "pk", None) or "anon"
    return cache.add(f"submission:{user_part}:{key[:64]}", True, KEY_TTL_SECONDS)

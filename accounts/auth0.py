"""Auth0 OIDC client, built only when Auth0 is actually configured.

Deliberately not built at import time with empty settings -- that would
either crash on startup or silently misconfigure itself. Views call
get_auth0_client() and handle None by falling back to local demo auth.
"""

from django.conf import settings


def auth0_configured() -> bool:
    return bool(settings.AUTH0_DOMAIN and settings.AUTH0_CLIENT_ID and settings.AUTH0_CLIENT_SECRET)


_oauth = None


def get_auth0_client():
    """Return the registered Auth0 OAuth client, or None if unconfigured.

    Token validation (signature via JWKS, issuer, audience, expiration)
    is handled by authlib itself during authorize_access_token() -- see
    docs/architecture-auth0-supabase.md for why this isn't hand-rolled.
    """
    global _oauth
    if not auth0_configured():
        return None
    if _oauth is None:
        from authlib.integrations.django_client import OAuth

        _oauth = OAuth()
        _oauth.register(
            "auth0",
            client_id=settings.AUTH0_CLIENT_ID,
            client_secret=settings.AUTH0_CLIENT_SECRET,
            client_kwargs={"scope": "openid profile email"},
            server_metadata_url=f"https://{settings.AUTH0_DOMAIN}/.well-known/openid-configuration",
        )
    return _oauth.auth0

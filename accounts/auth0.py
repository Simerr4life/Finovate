"""Auth0 login via the official Auth0 Python server SDK.

The client is built only when Auth0 is configured. Views call
get_auth0_client() and fall back to local demo auth when it returns None.
"""

from django.conf import settings

from auth0_server_python.auth_server.server_client import ServerClient
from auth0_server_python.auth_types import StateData, TransactionData
from auth0_server_python.store.abstract import AbstractDataStore


def auth0_configured() -> bool:
    return bool(
        settings.AUTH0_DOMAIN
        and settings.AUTH0_CLIENT_ID
        and settings.AUTH0_CLIENT_SECRET
        and settings.AUTH0_SECRET
    )


def callback_url() -> str:
    return settings.APP_BASE_URL.rstrip("/") + "/callback"


def logout_return_url() -> str:
    return settings.APP_BASE_URL.rstrip("/") + "/"


class DjangoCookieStore(AbstractDataStore):
    """Encrypted-cookie store the Auth0 SDK uses for the login transaction
    and the Auth0 session. Pending writes are applied to the Django
    response by apply_auth0_cookies().
    """

    def __init__(self, secret, cookie_name, max_age, model):
        super().__init__({"secret": secret})
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.model = model

    async def set(self, identifier, state, remove_if_expires=False, options=None):
        request = (options or {})["request"]
        data = state.model_dump() if hasattr(state, "model_dump") else state
        _pending(request)[self.cookie_name] = {
            "value": self.encrypt(identifier, data),
            "max_age": self.max_age,
        }

    async def get(self, identifier, options=None):
        request = (options or {})["request"]
        encrypted = request.COOKIES.get(self.cookie_name)
        if not encrypted:
            return None
        try:
            return self.model.model_validate(self.decrypt(identifier, encrypted))
        except Exception:
            return None

    async def delete(self, identifier, options=None):
        request = (options or {})["request"]
        _pending(request)[self.cookie_name] = None


def _pending(request):
    pending = getattr(request, "_auth0_cookies", None)
    if pending is None:
        pending = {}
        request._auth0_cookies = pending
    return pending


def apply_auth0_cookies(request, response):
    secure = not settings.APP_BASE_URL.startswith("http://")
    for name, spec in getattr(request, "_auth0_cookies", {}).items():
        if spec is None:
            response.delete_cookie(name)
        else:
            response.set_cookie(
                name,
                spec["value"],
                max_age=spec["max_age"],
                httponly=True,
                samesite="Lax",
                secure=secure,
            )
    return response


_client = None
_client_key = None


def get_auth0_client():
    """Return the Auth0 server client, or None if unconfigured."""
    global _client, _client_key
    if not auth0_configured():
        return None
    key = (
        settings.AUTH0_DOMAIN,
        settings.AUTH0_CLIENT_ID,
        settings.AUTH0_CLIENT_SECRET,
        settings.AUTH0_SECRET,
        settings.APP_BASE_URL,
    )
    if _client is None or _client_key != key:
        secret = settings.AUTH0_SECRET
        _client = ServerClient(
            domain=settings.AUTH0_DOMAIN,
            client_id=settings.AUTH0_CLIENT_ID,
            client_secret=settings.AUTH0_CLIENT_SECRET,
            redirect_uri=callback_url(),
            authorization_params={"scope": "openid profile email"},
            secret=secret,
            state_store=DjangoCookieStore(secret, "_a0_session", 259200, StateData),
            transaction_store=DjangoCookieStore(secret, "_a0_tx", 300, TransactionData),
        )
        _client_key = key
    return _client

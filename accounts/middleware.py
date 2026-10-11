"""Keep an Auth0-backed Django session inside the access-token lifetime.

Page requests use the server session established after Auth0 validated the
login. When that access token is due, the server refreshes it with the
encrypted Auth0 cookie. A browser-only check is not enough: this runs
before the view.
"""

import time

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from auth0_server_python.error import AccessTokenError, SessionExpiredError

from .auth0 import apply_auth0_cookies, get_auth0_client
from .identity import safe_next

_VERIFICATION_ALLOWED = (
    "/accounts/verify",
    "/accounts/logout/",
    "/accounts/auth0/hooks/",
    "/static/",
    "/callback/",
)


class Auth0SessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if _session_needs_reauth(request):
            logout(request)
            if not request.path.startswith("/accounts/login"):
                nxt = safe_next(request.get_full_path())
                target = reverse("accounts:login")
                if nxt:
                    target = f"{target}?next={nxt}"
                return redirect(target)
        if _must_finish_verification(request):
            return redirect("accounts:verify")
        response = self.get_response(request)
        return apply_auth0_cookies(request, response)


def _session_needs_reauth(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if not request.session.get("logged_in_via_auth0"):
        return False
    expires_at = request.session.get("auth0_access_exp")
    if not expires_at:
        return True
    if int(expires_at) > int(time.time()) + 60:
        return False
    client = get_auth0_client()
    if client is None:
        return True
    try:
        async_to_sync(client.get_access_token)(
            store_options={"request": request},
            audience=settings.AUTH0_AUDIENCE or None,
        )
        session = async_to_sync(client.get_session)(store_options={"request": request}) or {}
    except (AccessTokenError, SessionExpiredError):
        return True
    except Exception:
        return True
    token_sets = session.get("token_sets") or []
    expiries = []
    for item in token_sets:
        if settings.AUTH0_AUDIENCE and item.get("audience") != settings.AUTH0_AUDIENCE:
            continue
        if item.get("expires_at"):
            expiries.append(int(item["expires_at"]))
    if not expiries:
        return True
    request.session["auth0_access_exp"] = max(expiries)
    return False


def _must_finish_verification(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if request.path.startswith("/api/"):
        return False
    if any(request.path.startswith(prefix) for prefix in _VERIFICATION_ALLOWED):
        return False
    profile = getattr(user, "profile", None)
    if profile is None or not profile.auth0_sub:
        return False
    return not profile.email_verified

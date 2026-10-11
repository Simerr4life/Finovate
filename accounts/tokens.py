"""Validate Auth0 API access tokens.

An ID token is not accepted here. The audience must be the Finovate API
identifier, not the application's client id.
"""

import json
import logging
import urllib.request

from authlib.jose import JsonWebToken
from authlib.jose.errors import JoseError
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_jwt = JsonWebToken(["RS256"])


class TokenValidationError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def validate_access_token(token):
    if not token or not isinstance(token, str) or token.count(".") != 2:
        raise TokenValidationError("invalid_token")
    domain = (settings.AUTH0_DOMAIN or "").strip()
    audience = (settings.AUTH0_AUDIENCE or "").strip()
    if not domain or not audience:
        raise TokenValidationError("not_configured")
    issuer = f"https://{domain}/"
    try:
        claims = _jwt.decode(
            token,
            _jwks(domain),
            claims_options={
                "iss": {"essential": True, "value": issuer},
                "aud": {"essential": True, "value": audience},
                "exp": {"essential": True},
                "sub": {"essential": True},
            },
        )
        claims.validate()
    except JoseError:
        raise TokenValidationError("invalid_token") from None
    except TokenValidationError:
        raise
    except Exception:
        logger.warning("access token validation failed")
        raise TokenValidationError("invalid_token") from None
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenValidationError("invalid_token")
    return {"sub": subject, "scope": claims.get("scope") or ""}


def _jwks(domain):
    cache_key = f"auth0-jwks:{domain}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    request = urllib.request.Request(
        f"https://{domain}/.well-known/jwks.json",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.warning("auth0 jwks fetch failed")
        raise TokenValidationError("invalid_token") from None
    if not isinstance(payload, dict) or not payload.get("keys"):
        raise TokenValidationError("invalid_token")
    cache.set(cache_key, payload, 600)
    return payload

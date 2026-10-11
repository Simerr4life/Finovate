"""
Django settings for finovate project.

Configuration is read from environment variables (see .env.example) so that
the app runs in a safe local/demo mode with zero external credentials, and
can be promoted to real settings later without code changes.
"""

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from a local .env file if present. This file is
# git-ignored; .env.example documents the placeholder names only.
# Auth0 onboarding writes credentials to .env.local; that file wins
# when both define the same key.
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# SECURITY WARNING: the fallback below is only for local/demo use.
# Set FINOVATE_SECRET_KEY in your environment before any real deployment.
SECRET_KEY = os.environ.get(
    "FINOVATE_SECRET_KEY",
    "django-insecure-demo-key-do-not-use-in-production",
)

ON_VERCEL = bool(os.environ.get("VERCEL"))

DEBUG = env_bool("FINOVATE_DEBUG", not ON_VERCEL)

_default_hosts = (
    ".vercel.app,finovate.biz,www.finovate.biz" if ON_VERCEL else "localhost,127.0.0.1"
)
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("FINOVATE_ALLOWED_HOSTS", _default_hosts).split(",")
    if h.strip()
]

if ON_VERCEL:
    CSRF_TRUSTED_ORIGINS = [
        "https://finovate.biz",
        "https://www.finovate.biz",
        "https://*.vercel.app",
    ]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Kept so existing environment files still parse. The product UI no longer
# shows a demo-mode banner from this flag.
FINOVATE_DEMO_MODE = env_bool("FINOVATE_DEMO_MODE", False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "accounts",
    "transactions",
    "budgets",
    "savings",
    "investing",
    "assistant",
    "imports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.Auth0SessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "finovate.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "finovate.wsgi.application"

# Database. SQLite is the local/demo default -- unchanged unless a real
# Postgres connection string is provided. DATABASE_URL (generic) or
# SUPABASE_DB_URL (Supabase's own name for the same thing) switches to
# Postgres; nothing else about the ORM/migrations/models changes, since
# Django's migrations create the same schema on either engine. See
# docs/architecture-auth0-supabase.md for the full rationale.
def _postgres_config_from_url(url: str) -> dict:
    # urlparse does NOT percent-decode the userinfo portion -- a password
    # containing "@" or ":" would arrive still percent-encoded (e.g.
    # "p%40ss") without this, which psycopg would then treat as a
    # literal wrong password rather than "p@ss".
    parsed = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": unquote(parsed.username) if parsed.username else "",
        "PASSWORD": unquote(parsed.password) if parsed.password else "",
        "HOST": parsed.hostname or "",
        "PORT": parsed.port or "",
        # Supabase's pooled connection endpoints are reached over TLS;
        # sslmode=require is safe to always set for a hosted Postgres URL.
        "OPTIONS": {"sslmode": "require"},
    }


_pg_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if _pg_url:
    DATABASES = {"default": _postgres_config_from_url(_pg_url)}
else:
    # Vercel functions can write only to /tmp, and that disk is local to
    # one instance -- demo data is recreated on cold start there, not
    # persisted. Local dev uses a real file next to the project.
    _default_db = "/tmp/finovate.sqlite3" if ON_VERCEL else str(BASE_DIR / "db.sqlite3")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("FINOVATE_DB_PATH", _default_db),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "landing"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Structured logging: console output, no payload fields that could leak
# account numbers, balances, or similar sensitive financial data. Code
# should log *that* an event happened (e.g. "transaction created"), not
# amounts or identifying financial details.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("FINOVATE_LOG_LEVEL", "INFO"),
    },
}

# --- Auth0 -------------------------------------------------------------
# Empty unless .env / .env.local sets them. Website signup and login stay
# unavailable until domain, client id, client secret, and the session
# secret are all set. AUTH0_AUDIENCE is the Finovate API identifier used
# to validate access tokens. Management credentials are optional and are
# only used on the server to resend verification email.
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET", "")
AUTH0_SECRET = os.environ.get("AUTH0_SECRET", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")
AUTH0_MGMT_CLIENT_ID = os.environ.get("AUTH0_MGMT_CLIENT_ID", "")
AUTH0_MGMT_CLIENT_SECRET = os.environ.get("AUTH0_MGMT_CLIENT_SECRET", "")
_app_base = os.environ.get("APP_BASE_URL", "").strip()
if not _app_base and ON_VERCEL:
    _app_base = "https://finovate.biz"
APP_BASE_URL = _app_base or "http://127.0.0.1:8000"

_cookie_secure = APP_BASE_URL.startswith("https://")
SESSION_COOKIE_SECURE = _cookie_secure
CSRF_COOKIE_SECURE = _cookie_secure
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8

# --- Supabase Auth (email-and-password sign-in) --------------------------
# The public key may be the publishable key or the legacy anon key. The
# service key is server-side only and is used solely to carry a pre-Supabase
# account's password across on its first login.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_PUBLIC_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

BANK_PROVIDER_API_KEY = os.environ.get("BANK_PROVIDER_API_KEY", "")
BROKERAGE_PROVIDER_API_KEY = os.environ.get("BROKERAGE_PROVIDER_API_KEY", "")
MESSAGING_PROVIDER_API_KEY = os.environ.get("MESSAGING_PROVIDER_API_KEY", "")
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

# Shared secret expected on the Photon Spectrum (iMessage) self-hosted
# webhook, if/when that mode is enabled on the Photon side. Empty by
# default -- unset means the webhook endpoint accepts any caller, which
# is only acceptable for local demo use. The exact header name Photon
# actually sends is unverified; see docs/messaging-assistant.md.
PHOTON_WEBHOOK_SECRET = os.environ.get("PHOTON_WEBHOOK_SECRET", "")
# Spectrum Cloud webhook signing secret (Stable docs). PHOTON_WEBHOOK_SECRET
# remains as a fallback name for existing environments.
IMESSAGE_WEBHOOK_SECRET = os.environ.get("IMESSAGE_WEBHOOK_SECRET", "")
IMESSAGE_PROJECT_ID = os.environ.get("IMESSAGE_PROJECT_ID", "")
IMESSAGE_PROJECT_SECRET = os.environ.get("IMESSAGE_PROJECT_SECRET", "")
# Shared secret for the Node Spectrum adapter calling /assistant/bridge/.
# Falls back to IMESSAGE_PROJECT_SECRET when unset.
ASSISTANT_BRIDGE_SECRET = os.environ.get("ASSISTANT_BRIDGE_SECRET", "")

"""
Django settings for finovate project.

Configuration is read from environment variables (see .env.example) so that
the app runs in a safe local/demo mode with zero external credentials, and
can be promoted to real settings later without code changes.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from a local .env file if present. This file is
# git-ignored; .env.example documents the placeholder names only.
load_dotenv(BASE_DIR / ".env")


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

DEBUG = env_bool("FINOVATE_DEBUG", True)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("FINOVATE_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# Demo mode is the default local experience: no external providers are
# configured, auth is a clearly-labeled local demo flow, and seed data is
# available. This flag is read by templates/views to show "Demo Mode"
# banners and gate destructive demo-data actions.
FINOVATE_DEMO_MODE = env_bool("FINOVATE_DEMO_MODE", True)

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

# Database: SQLite is used for local development per project constraints.
# Access goes through Django's ORM/migrations so swapping to Postgres later
# only requires changing this DATABASES block and the ENGINE driver.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("FINOVATE_DB_PATH", str(BASE_DIR / "db.sqlite3")),
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

# --- Integration placeholders (unconfigured) ---------------------------
# These settings exist so the codebase has one documented place to look
# for future integration config. None of them are read by any running
# code path yet; see docs/integration-readiness.md for details.
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET", "")

BANK_PROVIDER_API_KEY = os.environ.get("BANK_PROVIDER_API_KEY", "")
BROKERAGE_PROVIDER_API_KEY = os.environ.get("BROKERAGE_PROVIDER_API_KEY", "")
MESSAGING_PROVIDER_API_KEY = os.environ.get("MESSAGING_PROVIDER_API_KEY", "")

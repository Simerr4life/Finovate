# Getting started

**Last reviewed:** 2026-10-11

## Prerequisites

- Python 3.13 recommended (3.12 used successfully for local docs capture)
- Ability to install from `requirements.txt`
- Optional: Auth0, Supabase, Twelve Data, Photon Spectrum credentials

## Local setup

```bash
cd Finovate
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

### Optional seeds

```bash
python manage.py seed_peachtree_demo
python manage.py seed_excel_demo_market
python manage.py seed_market_data
```

### Admin

```bash
python manage.py createsuperuser
```

Visit `/admin/`.

## Configuration

Copy `.env.example` → `.env`. SQLite demo data works without `.env`, but **website signup/login stay unavailable until Auth0 and/or Supabase Auth are configured**.

| Variable | Purpose |
|---|---|
| `FINOVATE_SECRET_KEY` | Django secret |
| `AUTH0_*` | Auth0 web app + session encryption |
| `APP_BASE_URL` | Origin for Auth0 callback `/callback` |
| `SUPABASE_URL` + keys | Email/password auth (+ optional Postgres) |
| `DATABASE_URL` / `SUPABASE_DB_URL` | Postgres instead of SQLite |
| `TWELVE_DATA_API_KEY` | Live demo quotes/history |
| `IMESSAGE_*` / `PHOTON_WEBHOOK_SECRET` | Spectrum webhook verification |

Never commit real secret values.

## First-user journey (auth configured)

1. Landing → **Sign up**
2. Auth0 Universal Login or Supabase email form
3. Email verification gate if needed (`/accounts/verify/`)
4. Onboarding: CSV import, manual setup, or continue
5. Preferences → marks `onboarding_completed`
6. Dashboard

## Quick test

```bash
python manage.py test
```

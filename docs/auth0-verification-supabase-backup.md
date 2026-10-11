# Auth0 email verification + Supabase signup backup

## Root cause (verification bug)

Finovate stored `Profile.email_verified` from the Auth0 ID token at login and
kept that session value. After the user clicked Auth0’s verification email:

1. Auth0 correctly set `email_verified: true` on the Auth0 user record.
2. The app session still held `email_verified: false` from the original token.
3. “I’ve verified my email” only started a `max_age=0` login; there was no
   Management API re-read of the authoritative user profile.
4. `sync_profile_from_claims` could **overwrite** a confirmed `True` with a
   stale `False` on a later login that still carried an old claim.

A successful redirect alone never proved verification. The fix refreshes
trusted Auth0 state (Management API and/or a fresh ID-token claim), never
downgrades a confirmed verification, and updates the UI from that result.

## Lifecycle

```
Signup → Auth0 Action webhook / profile sync → Auth0UserBackup pending
  → Backup synced → Email pending → Auth0 verifies email
  → Management API / fresh claims → Profile + backup email_verified=true
  → Application gate lifts
```

## What was implemented in code

| Area | Change |
|---|---|
| `accounts/verification.py` | Management API user fetch; authoritative verify; resend; monotonic upgrades |
| `accounts/identity.py` | Never downgrade `email_verified`; enqueue backup on create/login |
| `accounts/views.py` | Verify page refresh; result landing; webhook; refresh then `max_age=0` |
| `accounts/models.py` | `Auth0UserBackup` table |
| `accounts/auth0_backup.py` | Idempotent upsert, retry, reconcile |
| `accounts/migrations/0008_auth0_user_backup.py` | Schema + Postgres RLS enable (no policies) |
| Management command | `python manage.py reconcile_auth0_backups` |
| Templates | Success / pending / expired / invalid / already-verified / unavailable |
| Tests | `accounts/test_verification_backup.py` |

**Auth0 remains the primary IdP.** The backup table is not a restorable copy
of Auth0 credentials or password hashes.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `AUTH0_DOMAIN` / `AUTH0_CLIENT_ID` / `AUTH0_CLIENT_SECRET` / `AUTH0_SECRET` | Yes for Auth0 login | Existing OIDC login |
| `APP_BASE_URL` | Yes | Callback origin (`/callback`, logout `/`) |
| `AUTH0_MGMT_CLIENT_ID` / `AUTH0_MGMT_CLIENT_SECRET` | Recommended | Resend verification + authoritative `email_verified` refresh |
| `AUTH0_ACTION_SECRET` | Recommended | Shared secret for Post-User-Registration webhook |
| `DATABASE_URL` or `SUPABASE_DB_URL` | Production | Hosted Postgres (Supabase) where `accounts_auth0userbackup` lives |
| `SUPABASE_URL` / keys | Optional | Email/password Supabase Auth path (unchanged); not used for backup writes |

Never put Management secrets, Action secrets, or service-role keys in browser code.

## Auth0 dashboard configuration (required outside this repo)

### 1. Application URLs

- Allowed Callback URLs: `<APP_BASE_URL>/callback`
- Allowed Logout URLs: `<APP_BASE_URL>/`
- Allowed Web Origins: `<APP_BASE_URL>`

### 2. Verification email `resultUrl`

In Auth0 → Branding → Email Templates → Verification Email, set the redirect /
result URL to:

```text
<APP_BASE_URL>/accounts/verify/result/
```

Optional query hints (`success`, `error`, `message`) are display-only. Finovate
re-checks Auth0 before unlocking the account.

### 3. Machine-to-machine (Management API)

Authorize an M2M application against the Auth0 Management API with at least:

- `read:users`
- `update:users` (or the permission required for the verification-email job)

Set `AUTH0_MGMT_CLIENT_ID` / `AUTH0_MGMT_CLIENT_SECRET` on the server.

### 4. Post-User-Registration Action

Create an Action on the **Post User Registration** trigger. Store
`FINOVATE_BACKUP_URL` and `FINOVATE_ACTION_SECRET` as Action secrets.

```javascript
exports.onExecutePostUserRegistration = async (event, api) => {
  const url = event.secrets.FINOVATE_BACKUP_URL;
  const secret = event.secrets.FINOVATE_ACTION_SECRET;
  if (!url || !secret) return;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${secret}`,
    },
    body: JSON.stringify({
      user: {
        user_id: event.user.user_id,
        email: event.user.email,
        email_verified: event.user.email_verified === true,
        name: event.user.name || event.user.nickname || "",
        given_name: event.user.given_name || "",
        family_name: event.user.family_name || "",
        nickname: event.user.nickname || "",
        created_at: event.user.created_at,
        identities: event.user.identities || [],
      },
    }),
  });

  if (!response.ok) {
    // Non-2xx lets Auth0 surface the failure for retry/ops review.
    throw new Error(`finovate_backup_${response.status}`);
  }
};
```

Deploy URL:

```text
<APP_BASE_URL>/accounts/auth0/hooks/signup/
```

Set the same value in Finovate as `AUTH0_ACTION_SECRET`.

### 5. Scheduled reconciliation

Run periodically (cron / platform scheduler):

```bash
python manage.py reconcile_auth0_backups --limit 500
```

This creates missing backup rows from `Profile.auth0_sub` and retries
`pending` / `failed` syncs.

## Security notes

- Backup writes are server-side only (ORM + authenticated webhook).
- RLS is enabled on `accounts_auth0userbackup` with **no** policies, so
  Supabase PostgREST `anon` / `authenticated` roles cannot read or write.
  Django’s table-owner connection bypasses RLS (same pattern as other tables).
- No passwords, hashes, access tokens, refresh tokens, or verification tokens
  are stored on the backup row.
- Unique key is `auth0_user_id` (Auth0 `sub`), never email alone.
- `email_verified` on the backup is monotonic: confirmed `true` is never
  overwritten by stale `false`.

## Manual end-to-end checklist

1. Sign up via Auth0 with a new email.
2. Confirm exactly one `accounts_auth0userbackup` row (`sync_status=synced`).
3. Confirm the Finovate session is gated on `/accounts/verify/`.
4. Click the Auth0 verification email link.
5. Land on `/accounts/verify/result/` or return to the app and open Verify.
6. Confirm Auth0 user shows `email_verified: true` (Dashboard or Management API).
7. Confirm Finovate `Profile.email_verified` becomes true and onboarding opens.
8. Re-deliver the Action webhook payload; confirm still one backup row.
9. Mark a backup `failed`, run `reconcile_auth0_backups`, confirm it syncs.
10. Log out / log in, password reset, and settings still behave as before.
11. As an unverified user, craft `?state=verified` — account stays gated.

## Automated tests

```bash
.venv/bin/python manage.py test accounts.test_verification_backup accounts.tests -v1
```

## Limitations

- Custom Auth0 Database connection verification scripts are **not** used by
  Finovate today (Universal Login Database connection). If you add a custom
  DB connection later, its `get user` / login scripts must return string
  `user_id`, `email`, and `email_verified`.
- Without Management API credentials, verification still works via
  “I’ve verified my email” → fresh Auth0 login (`max_age=0`) and trusted
  ID-token claims, but the email-link return path cannot refresh silently.
- A Supabase outage that also takes down Django’s database prevents durable
  local queuing; the Auth0 Action should retry on HTTP 503, and
  `reconcile_auth0_backups` repairs drift once the DB is back.

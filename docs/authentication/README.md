# Authentication

**Last reviewed:** 2026-10-11

![Login](assets/screenshots/annotated/authentication-login-annotated.png)

## Providers

| Provider | When | Password storage in Finovate |
|---|---|---|
| Auth0 | `AUTH0_DOMAIN/CLIENT_ID/CLIENT_SECRET/SECRET` set | None — profile keyed by `auth0_sub` |
| Supabase Auth | `SUPABASE_URL` + publishable/anon key | None — keyed by `supabase_uid` |

## Pages

- Signup `/accounts/signup/`
- Login `/accounts/login/`
- Verify `/accounts/verify/` (+ resend/refresh)
- Logout `/accounts/logout/`
- Callback `/callback/`

## Identity rules (verified)

- Auth0 profile lookup **by subject only**, never email merge
- Unverified Auth0 users gated by middleware
- Optional Management API for verification email resend (`AUTH0_MGMT_*`)
- Legacy Django-password users can migrate to Supabase on first email login when service role configured

Deep dive: [architecture-auth0-supabase.md](../architecture-auth0-supabase.md), [auth0-verification-supabase-backup.md](../auth0-verification-supabase-backup.md).

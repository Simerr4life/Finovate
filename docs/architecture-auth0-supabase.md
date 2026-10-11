# Architecture: Auth0 identity + Supabase data

This documents the identity model and data-connectivity architecture for
the Auth0 and Supabase integration, per the project's own requirement to
document this before implementing it.

## Why this integration is simpler than a typical Auth0+Supabase stack

Most Auth0+Supabase writeups assume a decoupled single-page app calling a
JSON API with bearer tokens, and a browser talking to Supabase directly
with row-level security enforcing per-user access. **Finovate isn't that
shape.** It's one Django app that server-renders HTML (the Figma Make
design was ported into Django templates — see `.figma-make-inspect/` for
the original reference export, `templates/` for the live version). There
is no separate frontend making authenticated API calls.

That changes both integrations:

- **Auth0** becomes an OIDC login provider for the *existing Django
  session* — not a bearer-token system every view has to validate. A user
  authenticates with Auth0 once, Django establishes a session exactly
  like it already does for local demo accounts, and every existing
  `@login_required` view and ownership check (already covered by
  `PerUserDataIsolationTests` and friends) keeps working unchanged.
- **Supabase** becomes a hosted Postgres database Django's ORM connects
  to — not a client SDK or REST layer the templates call into. Row-level
  security policies keyed on `auth.uid()` don't apply here, because there
  is no direct browser-to-Supabase connection for them to protect; Django
  holds one database credential and is the enforcement point, which the
  project's own brief explicitly allows ("if the backend uses a
  privileged credential that bypasses RLS, enforce authorization in the
  backend").

## Identity model

| Concept | Where it lives |
|---|---|
| Stable external identity | `Profile.auth0_sub` — the Auth0 `sub` claim, unique, nullable (null for local demo accounts that never used Auth0) |
| Finovate's internal identity | Django's own `User.id`, unchanged |
| Session | Django's existing session cookie — established by `django.contrib.auth.login()` either from the local password form or from the Auth0 callback |

**Mapping rule:** on a successful Auth0 callback, look up `Profile` by
`auth0_sub`. If found, log that user in. If not found, create a new
`User`/`Profile` and store the `sub` — **never** look up or merge by
email. Two different Auth0 accounts that happen to share an email never
become the same Finovate user; a user who already has a local demo
account and later logs in via Auth0 gets a **second**, separate Finovate
account unless they're explicitly linked (not built — out of scope until
there's a real need, to avoid speculative complexity).

**Token validation:** handled by Auth0's own official
`auth0-server-python` SDK (`accounts/auth0.py`'s `ServerClient`), not
hand-rolled JWT parsing — `complete_interactive_login()` performs the
code exchange and validates the ID token's signature, issuer, audience,
and expiration internally (the SDK depends on `authlib` for this). Login
state and the post-login session are kept in encrypted, httponly cookies
(`DjangoCookieStore` in `accounts/auth0.py`), applied to the response via
`apply_auth0_cookies()`.

## Fallback behavior (no Auth0 configured)

`accounts/auth0.py::auth0_configured()` requires `AUTH0_DOMAIN`,
`AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, and `AUTH0_SECRET` (the
session-cookie encryption key) to all be set. When they're not, the
website login and signup pages say sign-in is unavailable. They do not
create a Django user or accept a password. `python manage.py seed_demo`
can still insert a local fixture user for management commands; that
account is not a website registration path.

Auth0's registered callback URL must be `<APP_BASE_URL>/callback` exactly
(a top-level route in `finovate/urls.py`, not under `/accounts/`).

## Database connectivity (Supabase)

`finovate/settings.py` resolves `DATABASES['default']` in this order:

1. `DATABASE_URL` or `SUPABASE_DB_URL` env var, if set — parsed into a
   Postgres connection (via `psycopg`), used as-is.
2. Otherwise, SQLite at the existing local path — unchanged default.

This is a connection-string swap, not a schema change: Django's existing
migrations (`*/migrations/0001_initial.py` etc.) create the same tables
in Postgres that they create in SQLite. No new Supabase-specific tables,
clients, or access patterns were introduced.

## Live status (as of this session)

A real Supabase project now backs this app — not just the connectivity
code, the actual project:

- **Project:** `finovate`, ref `rhhotkojxkajsfozfrtn`, org "Simerr4life's
  Org", region `us-east-1`, free tier ($0/month, confirmed before
  creation).
- **Schema:** all 29 tables (Django's built-ins plus every app's models)
  created by running the real `python manage.py migrate` against the
  project's pooled connection — not a hand-written parallel schema. This
  is the authoritative migration history; `sqlmigrate` against a live
  Postgres target was tried first but requires an actual connection to
  generate correct dialect SQL (it hung against a fake host), so the
  owner provided the real connection string and I ran `migrate` directly.
- **Verified live**, not just "migration ran": a real INSERT/SELECT/DELETE
  round-trip via Django ORM succeeded after RLS was enabled, confirming
  the app's connection (table owner) is unaffected by RLS as expected.
- **RLS:** enabled on all 29 tables with zero policies, applied via
  Supabase's `apply_migration` after Supabase's own security advisor
  flagged all-tables-RLS-disabled as **critical** (anon/authenticated
  PostgREST access was wide open). Re-running the advisor after
  confirmed the finding dropped to informational
  ("RLS enabled, no policies" — expected and fine, since nothing uses
  PostgREST here). The Django connection (table owner) bypasses RLS, so
  authorization still lives entirely in Python, as designed above.
- **Vercel:** `DATABASE_URL` set on the `finovate` Vercel project
  (production/preview/development) as a `sensitive` (write-only) env var
  pointing at this project's transaction-pooler connection string.

**A second, pre-existing Supabase project is also connected to this
Vercel project**, via Vercel's native Supabase marketplace integration
(`POSTGRES_URL`, `POSTGRES_PRISMA_URL`, `SUPABASE_URL`,
`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, etc. — all already
populated, under a different Supabase account than the one used above).
Django reads `DATABASE_URL`/`SUPABASE_DB_URL` only, so these legacy vars
are inert today, but they're real secrets sitting unused in the project.
No tool available in this session could delete them (Vercel's env API
exposed here has no delete endpoint) — **remove them manually** via the
Vercel dashboard (Project Settings → Environment Variables) if that old
integration isn't needed, or disconnect the integration itself if you're
fully moving to the project this session set up.

**If you ever need to migrate real user data between Supabase projects**
(not needed today — this project had zero rows before the owner's own
data):

```bash
python manage.py dumpdata --natural-foreign --natural-primary \
  --exclude contenttypes --exclude auth.permission > backup.json
# point DATABASE_URL at the target, run migrate, then:
python manage.py loaddata backup.json
```

Never run `loaddata` against a database that already has independent
data in it — it does not deduplicate.

## Row-level security — enabled, no policies (by design)

RLS is enabled on every table with no policies, which means Supabase's
PostgREST API (the thing `anon`/`authenticated` roles reach through) can
read or write nothing — fully locked out, matching the fact that nothing
in this app uses that API. Django's own Postgres role owns the tables
and bypasses RLS entirely, which is why authorization must keep living
in Python (already true, already tested) rather than in RLS policies.

If a future feature ever needs direct browser-to-Supase access, a
starting ownership policy would look like:

```sql
-- Only meaningful once something other than Django's backend connects
-- directly, with a per-user JWT Postgres can verify (not built here).
create policy "owner can access own transactions"
  on transactions_transaction
  using (user_id = current_setting('app.current_user_id')::int);
```

That `current_setting('app.current_user_id')` would need the backend to
`SET` it per connection/request — not implemented, since nothing
currently needs it.

## Registration and verification

Website signup collects a name, email, and optional phone number, then
redirects to Auth0 Universal Login (`screen_hint=signup`). Auth0 creates
the database identity and sends the verification email. Finovate stores
`email_verified` only from trusted Auth0 state (fresh ID-token claim or
Management API user record) and never downgrades a confirmed verification.
See [auth0-verification-supabase-backup.md](auth0-verification-supabase-backup.md)
for the verification lifecycle and `Auth0UserBackup` signup backup table.
A phone number typed into Finovate is contact data; `phone_verified` stays
false unless Auth0 returns `phone_number_verified`.

The configured connection is email/password through Universal Login.
Passwordless SMS is not enabled on the Finovate application, so entering
a phone number does not prove ownership of that number. Messaging uses
the existing one-time chat link, and only after `phone_verified`,
messaging consent, and a linked chat are all present.

Protected JSON calls go to `GET /api/me/` with an Auth0 access token
whose audience is `AUTH0_AUDIENCE` (`https://finovate.biz/api`). An ID
token, whose audience is the client id, is rejected.

## Phone-number login

Phone login is **not enabled**. The Auth0 application named Finovate
(`regular_web`, tenant `finovate`) allows `authorization_code`,
`refresh_token`, and `client_credentials`. It does not allow the
passwordless OTP grant.

To turn phone login on later, in the Auth0 dashboard:

1. Create a Passwordless SMS connection and attach an SMS provider
   (Auth0's trial SMS or your own Twilio account). A paid Auth0 feature
   or an external SMS account may be required.
2. Enable that connection for the Finovate application.
3. Add the passwordless OTP grant if the SDK flow requires it.
4. Keep the callback at `<APP_BASE_URL>/callback` and logout return at
   `<APP_BASE_URL>/`.
5. Map the user by the Auth0 `sub` claim. Do not merge accounts by phone
   number. Set `phone_verified` only from Auth0's
   `phone_number_verified` claim.

## What this integration does NOT do

- It does not add a second login system. Supabase Auth is not used.
- It does not give the browser a Supabase client key or direct database
  access.
- It does not change any existing view's authorization logic — ownership
  checks already happen in Python (`user=request.user` on every
  queryset), unchanged by where the rows physically live.

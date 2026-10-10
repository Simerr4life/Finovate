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

**Token validation:** handled by `authlib`'s OIDC client
(`authlib.integrations.django_client.OAuth`), not hand-rolled JWT
parsing. `authorize_access_token()` fetches Auth0's JWKS via the
`.well-known/openid-configuration` metadata URL and validates the ID
token's signature, issuer, audience, and expiration as part of the
standard OIDC flow — this is deliberately not reimplemented by hand,
since hand-rolled JWT validation is a common source of real
vulnerabilities (e.g. accepting `alg: none`).

## Fallback behavior (no Auth0 configured)

`accounts/auth0.py` only builds the OAuth client when `AUTH0_DOMAIN`,
`AUTH0_CLIENT_ID`, and `AUTH0_CLIENT_SECRET` are all set. When they're
not, the "Log in with Auth0" button doesn't render (see
`core/context_processors.py`'s `AUTH0_ENABLED`), and the existing local
demo signup/login flow is the only path — exactly as before this
integration. Nothing breaks for local/demo use without credentials.

## Database connectivity (Supabase)

`finovate/settings.py` resolves `DATABASES['default']` in this order:

1. `DATABASE_URL` or `SUPABASE_DB_URL` env var, if set — parsed into a
   Postgres connection (via `psycopg`), used as-is.
2. Otherwise, SQLite at the existing local path — unchanged default.

This is a connection-string swap, not a schema change: Django's existing
migrations (`*/migrations/0001_initial.py` etc.) create the same tables
in Postgres that they create in SQLite. No new Supabase-specific tables,
clients, or access patterns were introduced.

## Migrating existing local data to Supabase (documented, not executed)

This repo's local `db.sqlite3` has no production users in it (it's a
hackathon demo project), so there's no real migration to perform. If
that changes, the safe path is:

```bash
# 1. Export everything from the current database
python manage.py dumpdata --natural-foreign --natural-primary \
  --exclude contenttypes --exclude auth.permission > backup.json

# 2. Point DATABASE_URL at the new Postgres target, run migrations
export DATABASE_URL="postgresql://..."
python manage.py migrate

# 3. Load the data into the new database
python manage.py loaddata backup.json

# 4. Spot-check row counts before cutting over traffic
python manage.py shell -c "from django.contrib.auth.models import User; print(User.objects.count())"
```

Do this against a non-production Supabase project first. Never run
`loaddata` against a database that already has independent data in it —
it does not deduplicate.

## Row-level security — documented stance, not implemented

Given the trusted-single-backend architecture above, RLS policies aren't
load-bearing here. If you want defense-in-depth anyway (e.g. in case a
future feature does add direct client access), a starting policy for the
`transactions_transaction` table would look like:

```sql
-- Optional, NOT required by this architecture. Only meaningful once
-- something other than the Django backend's single DB credential
-- connects to Supabase directly, with a per-user JWT Postgres can
-- verify (not built here).
alter table transactions_transaction enable row level security;
create policy "owner can access own transactions"
  on transactions_transaction
  using (user_id = current_setting('app.current_user_id')::int);
```

That `current_setting('app.current_user_id')` would need the backend to
`SET` it per connection/request — not implemented, since nothing
currently needs it. Documented here so it's not forgotten if the
architecture changes later.

## What this integration does NOT do

- It does not add a second login system. Supabase Auth is not used.
- It does not give the browser a Supabase client key or direct database
  access.
- It does not change any existing view's authorization logic — ownership
  checks already happen in Python (`user=request.user` on every
  queryset), unchanged by where the rows physically live.

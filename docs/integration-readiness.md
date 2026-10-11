# Integration readiness

None of the integrations below are configured, connected, or called by
any running code path today. This document describes where each one
would plug in, what it would require, and what stays simulated until
then. It is intentionally not a how-to for signing up with any provider —
that's a decision for whoever owns credentials and legal/consent review.

## 1. Identity provider — Auth0 (now implemented)

**Update:** built. Full writeup in
[docs/architecture-auth0-supabase.md](architecture-auth0-supabase.md).

- **Where it plugs in:** `accounts/auth0.py` (official
  `auth0-server-python` client), `accounts/views.py` signup, login,
  callback, logout, and verification pages. Django sessions are
  established only after Auth0 completes the code exchange. The website
  does not create a password account.
- **Token validation:** the SDK validates the OIDC login (signature,
  issuer, audience, expiration). `GET /api/me/` separately validates an
  API access token with Authlib against the tenant JWKS. An ID token is
  not accepted as that access token.
- **Identity mapping:** `Profile.auth0_sub` stores the `sub` claim,
  unique. Never matched/merged by email — two Auth0 accounts sharing an
  email become two separate Finovate users (tested). `email_verified` is
  copied only from Auth0's claim.
- **Config required to activate:** set `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`,
  `AUTH0_CLIENT_SECRET`, and `AUTH0_SECRET` in `.env`. Set
  `AUTH0_AUDIENCE` to the Finovate API identifier before `/api/me/` will
  accept tokens. In the Auth0 tenant, the Finovate Regular Web
  Application needs Allowed Callback URL `<APP_BASE_URL>/callback` and
  Allowed Logout URL `<APP_BASE_URL>/`. Until the four core values are
  set, signup and login render an unavailable state and create no user.
- **Tests:** `accounts/tests.py` — unconfigured fallback, successful
  login creates exactly one mapped user, repeat login doesn't duplicate,
  shared-email accounts aren't merged, failed token exchange creates no
  user, missing `sub` claim creates no user, federated logout redirect.

## 1b. Database — Supabase/hosted Postgres (live)

**Update:** a real Supabase project is now provisioned and migrated, not
just the connectivity code. Full writeup, including exactly what was
verified vs. assumed, in
[docs/architecture-auth0-supabase.md](architecture-auth0-supabase.md).

- **Project:** `finovate` (ref `rhhotkojxkajsfozfrtn`), free tier, region
  `us-east-1`, created and migrated this session.
- **Where it plugs in:** `finovate/settings.py::_postgres_config_from_url`.
  `DATABASE_URL` (set on Vercel now) switches `DATABASES` from local
  SQLite to this Postgres project; nothing else changes, since Django's
  existing migrations created the same 29-table schema here that they
  create in SQLite.
- **RLS:** enabled on all 29 tables with no policies (locks out
  Supabase's PostgREST API entirely; Django's connection bypasses RLS as
  table owner and remains the sole enforcement point, consistent with
  the server-rendered architecture — see the doc above). Supabase's
  security advisor confirmed this took the finding from critical to
  informational.
- **Verified live:** `python manage.py migrate` ran against the real
  project (29/29 migrations OK); a real Django ORM create/read/delete
  round-trip succeeded after RLS was enabled, confirming the app's role
  still has full access.
- **Known leftover:** a second, pre-existing Supabase project (different
  account) is also connected to the same Vercel project via Vercel's
  native marketplace integration, with its own `POSTGRES_URL`/
  `SUPABASE_*` env vars already populated. Those are inert (Django never
  reads them) but weren't removed — no delete capability was available
  for Vercel env vars in this session. Remove manually via the Vercel
  dashboard if that old integration is no longer wanted.
- **Tests:** `accounts/tests.py::PostgresUrlParsingTests` — connection
  string parsing including percent-encoded passwords (a real bug caught
  and fixed while building this: `urlparse` does not decode the
  userinfo portion, so a password containing `@` or `:` would otherwise
  reach psycopg still percent-encoded).

## 2. Bank transaction and balance provider

- **Where it plugs in:** would replace/augment manual entry in
  `transactions/services.py::record_transaction`. The idempotency
  mechanism (`external_id` + `source="imported"`, enforced by a unique
  constraint) already exists specifically so a provider's webhook or
  polling sync can call this function repeatedly without double-counting.
- **Interface needed:** an adapter module (not yet built) that translates
  a provider's transaction/balance payload into calls to
  `record_transaction`, plus a scheduled job or webhook endpoint to invoke
  it, plus handling for provider timeouts and partial sync failures.
- **Config that would eventually be required:** `BANK_PROVIDER_API_KEY`
  placeholder exists; actual required fields (client ID, item/account
  tokens, webhook secrets) depend entirely on the chosen provider and
  aren't guessed here.
- **Security/consent considerations:** explicit user consent before
  connecting an account, never storing bank credentials (only provider
  tokens, and only once a provider is chosen), and a clear disconnect
  flow. `accounts.ConnectedAccountPlaceholder` models connection *status*
  only — no credentials, by design.
- **Stays simulated until configured:** transaction/balance data stays
  manually entered. Dashboard labels (`source` field, "demo" badges)
  already distinguish manual/imported/demo so adding real imports later
  doesn't require relabeling existing data.

## 3. Brokerage/ETF provider

- **Where it plugs in:** `investing/services.py`. Today
  `sweep_pending_roundups` and the order/portfolio models are entirely
  simulated. A real integration would replace the "mark as swept, create
  a `SimulatedOrder`" logic with an actual funding + order API call, and
  would update `PortfolioSnapshot` from real position data instead of a
  same-day echo of contributions.
- **Interface needed:** an adapter boundary so budget/goal logic never
  talks to the brokerage directly — only `investing/services.py` would
  change. Order status would need to become asynchronous (pending →
  filled/rejected via webhook or polling) rather than synchronous.
- **Config that would eventually be required:** `BROKERAGE_PROVIDER_API_KEY`
  placeholder exists; real requirements (account linking, trading
  permissions, minimums) depend on the provider.
- **Security/consent considerations:** explicit, auditable authorization
  before any real order is placed (not just a settings toggle — a
  confirmation step), handling of rejected/partial fills, and never
  inferring "spare cash" is safe to invest without respecting the user's
  cash reserve (`RoundUpSettings.minimum_cash_reserve` already models this
  constraint for the simulated version).
- **Stays simulated until configured:** every number on the Investing
  page. The page's disclaimers ("no brokerage is connected... no real
  trades occur") must remain accurate and should be removed only in the
  same change that wires up a real provider.

## 4. Messaging/companion channel — Photon/Spectrum (iMessage)

**Update:** the owner explicitly asked to move forward with this (overriding
the original "don't build this yet" scope), installed `@photon-ai/cli`,
and will handle their own Photon login/project/line setup. The intent
logic and a local test channel are now built; the real Photon transport
is not, because its documented integration path is a Node.js SDK rather
than a REST webhook Django can receive directly. Full writeup:
[docs/messaging-assistant.md](messaging-assistant.md).

- **What's built:** `assistant/` app — `intents.py` (keyword/regex
  parsing, no LLM), `services.py::handle_incoming_message` (dispatches to
  the exact same `budgets.services` / `savings.services` /
  `investing.services` functions the website uses, with a
  `PendingConfirmation` gate in front of every state-changing intent),
  and `python manage.py chat_demo` for testing it today without Photon.
- **Inbound Spectrum Cloud webhooks are verified** using the Stable
  `X-Spectrum-Signature` HMAC (`v0=` + SHA-256 over
  `v0:{timestamp}:{raw body}`), a 5-minute timestamp window, and dedupe
  on `X-Spectrum-Webhook-Id` + `message.id`. See
  [docs/messaging-assistant.md](messaging-assistant.md).
- **Outbound iMessage is sent by `spectrum/` (Node Spectrum adapter).**
  It POSTs to `/assistant/bridge/` and delivers the reply with
  `message.reply`. Django webhook responses still set `delivered: false`.
- **Interface:** a thin handler parses an inbound message, maps it to one
  of a fixed set of intents, calls the relevant service function, and
  formats a reply — no duplicated budget/goal/round-up logic.
- **Supported intents today:** budget status, portfolio performance
  summary, market status (honest "no live feed" reply), report income
  (confirm), set risk comfort (confirm), change a goal's target (confirm,
  with ambiguous-name clarification), pause round-ups (immediate — safe
  direction), resume round-ups (confirm — risk direction).
- **Config:** `PHOTON_WEBHOOK_SECRET` placeholder added for an
  X-Photon-Webhook-Secret header check; exact header name Photon actually
  uses is unverified. `MESSAGING_PROVIDER_API_KEY` remains unused.
- **Still absent:** the real Photon/Spectrum wiring (account, project,
  iMessage line) — that's the owner's own setup, done through the
  `photon` CLI directly, not through this codebase.

## 5. Domain/hosting (GoDaddy was mentioned)

- **No DNS or deployment changes have been made.** The app runs on
  `localhost` only. When ready to deploy, decisions needed include: where
  it's hosted (not necessarily GoDaddy for hosting itself — GoDaddy was
  mentioned for the domain), `ALLOWED_HOSTS`/`FINOVATE_ALLOWED_HOSTS`,
  HTTPS/TLS termination, a production `SECRET_KEY` (never the local
  fallback in `settings.py`), `DEBUG=false`, and a production-grade
  database (Postgres, per the "Technical expectations" in the product
  spec) instead of SQLite.
- **Stays local until configured:** everything. This is intentional per
  the project constraints — no public deployment during this phase.

# Third-Party Services and Sponsor Integrations

**Reviewed:** 2026-10-11, from the repository at branch `claude/codebase-audit-fixes`.
**Rule followed:** a service counts as integrated only if code calls it **and** there is evidence it works. An installed SDK, a configured variable name, or a mention in a comment does not count.

**Official challenges entered (Hacker Guide, max 3):** MLH: Best Use of Auth0 · Photon: Agents in iMessage (*"Projects must integrate Spectrum, Photon's open source SDK"*) · MLH: Best Domain Name from GoDaddy Registry.

Status legend: ✅ verified · 🟡 implemented, not live-tested · 🟠 partial · 🧪 simulated · 📝 planned · ⛔ blocked.

## Summary

| Service | Role in Finovate | Code integration | Live evidence collected here | Challenge readiness |
|---|---|---|---|---|
| **Auth0** | Primary identity provider for the website and API | Deep (login, callback, logout, verification, Management API, Action webhook, API token validation) | ⛔ No tenant credentials in this environment; covered by mocked tests | 🟠 Strong code; needs one live login on record |
| **Photon Spectrum** | iMessage transport for the chat assistant | Signed webhook + bridge in Django; `spectrum-ts` adapter in `spectrum/` | ✅ Bridge and assistant exercised in-process; ⛔ no live iMessage round-trip | 🟠 Strong code; needs one live iMessage exchange on record |
| **GoDaddy Registry** | Domain `finovate.biz` (`.biz` is a GoDaddy Registry TLD) for the "Best Domain Name" challenge | Domain configured in settings; serves the live app | Live per the team; DNS not reachable from the docs build environment | ✅ Ready |
| Supabase | Optional Postgres host and optional email/password sign-in | `DATABASE_URL` parsing; Supabase Auth REST calls | Mocked tests only | n/a |
| Twelve Data | Optional live quotes and daily history | REST calls with shared quota and cache | ⛔ No API key here | n/a |
| Vercel | Hosting (live at https://finovate.biz) | `vercel.json`, Vercel-specific settings branch, boot-time migrate | Live per the team; `FINOVATE_SECRET_KEY` set (team-confirmed) | n/a |
| Google Fonts | DM Sans / Manrope web fonts | CSS `@import` | Loaded in local browser tests | n/a |
| Figma Make | Source of the UI layout | Exported layout under `.figma-make-inspect/` (not served) | n/a | n/a |

---

## 1. Auth0

**Provider:** Auth0 by Okta, identity platform.
**Intended role:** create and authenticate Finovate accounts, verify email, protect the JSON API.

### Integration points

| Step | Where | What happens |
|---|---|---|
| Client setup | `accounts/auth0.py` → `get_auth0_client()` | Builds `auth0_server_python` `ServerClient` with scopes `openid profile email offline_access` and optional `AUTH0_AUDIENCE`. Transaction and session state live in **encrypted, HTTP-only cookies** (`DjangoTransactionStore`, `DjangoStateStore`). |
| Sign-up | `accounts/views.py::signup` | Collects name/email/optional phone, then starts Universal Login with `screen_hint=signup` and `login_hint`. **No password ever reaches Finovate.** |
| Login | `login_view`, `auth0_login`, `_begin_auth0` | Starts interactive login; `next` is passed through `safe_next` to stop open redirects. |
| Callback | `/callback/` and `/accounts/auth0/callback/` → `auth0_callback` | SDK validates the code and tokens. The profile is looked up **by Auth0 `sub` only**, never by email (`accounts/identity.py::sync_profile_from_claims`). Requires an API access token when an audience is set. |
| Session refresh | `accounts/middleware.py::Auth0SessionMiddleware` | Refreshes the access token before expiry; logs out and redirects to login if refresh fails. |
| Email verification | `accounts/verification.py`, `/accounts/verify/…` | Unverified Auth0 users are held on `/accounts/verify/`. Status is upgraded only from a fresh ID-token claim or the **Management API** (`GET /api/v2/users/{id}`), never from a query string. Resend uses `POST /api/v2/jobs/verification-email`. |
| Logout | `auth0_logout` (POST only) | Clears the Django session and redirects to Auth0's federated logout with a fixed return URL. |
| Post-User-Registration Action | `POST /accounts/auth0/hooks/signup/` | Shared-secret webhook (constant-time compare) that upserts an `Auth0UserBackup` row (non-secret profile fields only). |
| API protection | `GET /api/me/` (`accounts/api.py`, `accounts/tokens.py`) | Validates an RS256 **access token** against the tenant JWKS (issuer, audience, expiry). ID tokens are rejected; unverified users get 403 with no financial data. |

**Configuration (names only):** `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_SECRET`, `AUTH0_AUDIENCE`, `AUTH0_MGMT_CLIENT_ID`, `AUTH0_MGMT_CLIENT_SECRET`, `AUTH0_ACTION_SECRET`, `APP_BASE_URL`. Callback URL: `<APP_BASE_URL>/callback`. Verification result URL: `<APP_BASE_URL>/accounts/verify/result/`.

### Evidence

- **Automated (mocked SDK/HTTP):** e.g. `test_successful_callback_creates_a_user_mapped_by_sub`, `test_two_different_auth0_accounts_sharing_an_email_are_not_merged`, `test_unverified_user_cannot_open_the_dashboard`, `test_id_token_audience_is_rejected`, `test_expired_token_is_rejected`, `test_client_cannot_force_verified_via_query_state`, `test_webhook_requires_shared_secret` (`accounts/tests.py`, `accounts/test_verification_backup.py`, `accounts/test_audit_fixes.py`). All pass.
- **Live:** ⛔ not executed. This environment has no tenant credentials and no outbound access to Auth0.
- **Without configuration:** the login page shows *"Sign-in isn't configured on this server."* ([screenshot](assets/screenshots/submission/02-login-unconfigured.png)).

**Which steps work:** every step above is implemented and unit-tested against mocks. Whether the production tenant is configured with matching callback/logout URLs, an API audience, and the Action is **not verified**.

**Remaining for the sponsor track:** record a real sign-up → verification → dashboard → logout against the tenant, and optionally a `curl` to `/api/me/` with a real access token.

## 2. Photon Spectrum (iMessage)

**Provider identity:** Photon (photon.codes), **Spectrum** messaging SDK/cloud. The repository confirms the identity: `spectrum/package.json` depends on `spectrum-ts`, imports `spectrum-ts/providers/imessage`, and the docs link `photon.codes/docs`. This is not Proton.
**Intended role:** let users ask about and safely change their finances by text message.

### Integration points

| Component | Where | Behavior |
|---|---|---|
| Assistant brain | `assistant/services.py::handle_incoming_message`, `assistant/intents.py` | Regex intent recognition (no LLM). Read-only intents answer immediately. Money-affecting intents (record income, goal target, risk level, investment proposal, resume round-ups) create a `PendingConfirmation` and act only on "yes". Pausing round-ups is immediate (the safe direction). Withdrawals are always refused. |
| Account linking | `assistant/linking.py`, Settings → *Messaging* | One-time code (SHA-256 hashed, 15-minute expiry, single use) binds a chat ID to a user. A phone number is never the identity key. |
| Webhook transport | `POST /assistant/photon-webhook/` (`assistant/views.py`, `assistant/spectrum.py`) | Verifies `X-Spectrum-Signature` = `v0=HMAC-SHA256(secret, "v0:{timestamp}:{body}")` with a 300-second replay window. Returns the reply as JSON with `delivered: false` (this path does not send). Refuses to run unconfigured outside DEBUG. |
| Bridge transport | `POST /assistant/bridge/` | Called by the adapter with `X-Finovate-Bridge-Secret`; deduplicated on `(delivery_id, message_id)` via `SpectrumDelivery`. |
| Adapter | `spectrum/src/index.ts` (Bun) | Listens with `Spectrum({ projectId, projectSecret, providers: [imessage] })`, ignores outbound/non-text messages, adds a 👍 tapback, asks the bridge, replies with `message.reply`. A `terminal` provider allows local testing without Photon credentials. |

**Configuration (names only):** Django: `IMESSAGE_WEBHOOK_SECRET` (or legacy `PHOTON_WEBHOOK_SECRET`), `IMESSAGE_PROJECT_ID`, `IMESSAGE_PROJECT_SECRET`, `ASSISTANT_BRIDGE_SECRET`. Adapter: `PROJECT_ID`, `PROJECT_SECRET`, `FINOVATE_URL`, `ASSISTANT_BRIDGE_SECRET`, `SPECTRUM_PROVIDERS`.

### Evidence

- **Executed here:** the assistant answered `help`, budget status, goal status, `I got paid $500` → confirmation → `yes` (transaction recorded), `pause round-ups`, portfolio status, investment proposal → `no` (cancelled), and refused a withdrawal (transcript in [TESTING_AND_VALIDATION.md](TESTING_AND_VALIDATION.md#t-msg-01)). The bridge returned the unlinked-chat reply, then `duplicate: true` for the same message ID. The webhook returned 503 when a signature arrived with no secret configured.
- **Automated:** 43 tests in `assistant/tests.py`, including `test_spectrum_messages_event_is_verified_and_not_marked_delivered`, `test_stale_spectrum_timestamp_is_rejected`, `test_bridge_dedupes_on_message_id`, and `test_one_time_code_links_the_chat_and_cannot_be_reused`.
- **Not executed:** the Bun adapter was not run (no Photon credentials and no outbound network), so **live iMessage delivery is unverified**.

**Remaining for the sponsor track:** run `bun start` with project credentials, link a chat from Settings, and record one round-trip (question → reply; change → "yes" → website updates).

## 3. GoDaddy Registry (domain)

**Official challenge (Hacker Guide):** *MLH: Best Domain Name from GoDaddy Registry.* The prize is for the domain name itself; the guide does not ask for an API integration.

**What the repository shows:** the production host names `finovate.biz` and `www.finovate.biz` are configured in `finovate/settings.py` (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, default `APP_BASE_URL = https://finovate.biz`), and `AUTH0_AUDIENCE` uses `https://finovate.biz/api` (`.env.example`). `.biz` is a top-level domain operated by GoDaddy Registry.

**Status:** ✅ **Live.** Per the team, `finovate.biz` is registered and serves the deployed app on Vercel (https://finovate.biz). DNS was not reachable from the docs build environment, so this was not independently checked here.

**Why the name:** *Finovate* = finance + innovate; `.biz` fits a money-management product. This is the domain judged in the challenge.

## 4. Supabase

- **Postgres:** `finovate/settings.py::_postgres_config_from_url` parses `DATABASE_URL`/`SUPABASE_DB_URL` (percent-decoding credentials, `sslmode=require`). Tests: `test_parses_a_supabase_style_connection_string`, `test_percent_encoded_special_characters_in_password_are_decoded`.
- **Auth (optional):** `accounts/supabase_auth.py` calls `/auth/v1/signup` and `/auth/v1/token?grant_type=password`. Profiles map by Supabase user ID, never email. Legacy Django passwords move across on first login using the service key. Tests in `accounts/tests.py` (mocked).
- **Live:** not exercised.

## 5. Twelve Data

`investing/live_quotes.py` fetches `/price` and `/time_series` (90 daily bars) for AAPL, AMZN, GOOGL, MSFT, and NVDA. It shares a database-backed quota of 8 credits/minute and 800/day, caches quotes for 5 minutes and history for 12 hours, and uses fetch leases to stop duplicate calls. Without `TWELVE_DATA_API_KEY`, the Explore tab, holdings valuation, demo ideas, and the price-based scenario show "not available" states ([screenshot](assets/screenshots/submission/17-investing-explore-no-feed.png)).

## 6. Vercel

`vercel.json` deploys `finovate/wsgi.py` (60 s max duration). On Vercel, settings switch to `DEBUG=False`, trust `*.vercel.app` and `finovate.biz` origins, and use `/tmp` SQLite unless a Postgres URL is set (so data does **not** persist across cold starts without Postgres). `wsgi.py` runs `migrate` at boot and seeds `demo` when `DEMO_ACCOUNT_PASSWORD` is set.

## 7. Open-source libraries

| Package | Version | Use |
|---|---|---|
| Django | 6.1.2 | Web framework, ORM, auth, admin |
| auth0-server-python | 1.0.0b19 (beta) | Auth0 login/session |
| Authlib | 1.8.0 | JWT validation (`authlib.jose`, deprecated module — see tech debt) |
| psycopg / psycopg-binary | 3.3.6 | PostgreSQL driver |
| python-dotenv | 1.2.4 | `.env` loading |
| spectrum-ts | ^12.10.1 | Photon Spectrum adapter |
| TypeScript, @types/bun | ^5 / latest | Adapter tooling |

No file in the repository grants a license for Finovate itself (no `LICENSE`).

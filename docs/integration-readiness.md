# Integration readiness

None of the integrations below are configured, connected, or called by
any running code path today. This document describes where each one
would plug in, what it would require, and what stays simulated until
then. It is intentionally not a how-to for signing up with any provider —
that's a decision for whoever owns credentials and legal/consent review.

## 1. Identity provider (e.g. Auth0)

- **Where it plugs in:** `accounts/views.py` (`signup`, and Django's
  built-in `LoginView`/`LogoutView` wired in `accounts/urls.py`).
  Today these use Django's local session auth — clearly labeled "demo
  authentication" on the signup/login templates.
- **Interface needed:** an OAuth2/OIDC flow. Concretely: a callback view
  that exchanges an authorization code for tokens, a way to map the
  provider's user ID to Django's `User` model (e.g. a `SocialAccount`-style
  table, not yet built), and a decision on whether Django sessions remain
  the source of truth post-login or whether to move to a different
  session strategy.
- **Config that would eventually be required:** `AUTH0_DOMAIN`,
  `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` — placeholders already exist in
  `.env.example` and `finovate/settings.py`, read by nothing yet.
- **Security/consent considerations:** redirect URI allowlisting, token
  storage (never log tokens), session fixation on login, and a plan for
  existing demo-mode users if/when real auth is turned on.
- **Stays simulated until configured:** who's allowed to log in and how.
  Local signup/login keeps working either way; this would be additive.

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

## 4. Messaging/companion channel (Photon was mentioned; unconfirmed)

- **Where it plugs in:** nothing today. The product spec asks for a
  provider-neutral adapter *only if it helps the architecture*; building
  one before knowing the provider's actual API would be guessing, so it
  hasn't been built. The services layer (`budgets/services.py`,
  `savings/services.py`, `investing/services.py`) is already
  request/template-free, which is what would let a future messaging
  handler call the same functions the website calls.
- **Interface it would need:** a thin handler that parses an inbound
  message, maps it to one of the documented intents below, calls the
  relevant service function, and formats a reply — without duplicating
  budget/goal/round-up logic.
- **Documented intents for later implementation** (not built):
  - "What's my budget status?" → `budgets.services.compute_budget_progress`
    for the active period.
  - "I got paid $X" → record an income transaction, but only after an
    explicit confirmation step (never silently trust a free-text amount).
  - "Move my vacation goal target to $X" → update `savings.models.Goal`,
    again behind confirmation.
  - "How's my portfolio doing?" → read the latest `PortfolioSnapshot`,
    stating the period and separating contributions from performance.
  - "Pause round-ups" → toggle `RoundUpSettings.is_paused`, which already
    exists and is exercised by the Investing page today.
  - Any money-movement or order-placing intent **must** require explicit
    confirmation before calling a mutating service function — same rule
    as the website.
- **Config:** `MESSAGING_PROVIDER_API_KEY` placeholder exists, intentionally
  unused.
- **Stays simulated/absent until configured:** the entire channel. No
  iMessage/Photon integration exists in this codebase.

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

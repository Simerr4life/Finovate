# Technical Architecture

**Describes:** the code as it exists on 2026-10-11 (branch `claude/codebase-audit-fixes`). A proposed future design is shown at the end and labeled as proposed.

## 1. System context

```mermaid
flowchart TB
  user([User in a browser])
  phone([User on iMessage])
  subgraph host["Django app (Python 3.13 / Django 6.1) — one process"]
    web[Server-rendered pages + forms]
    svc[Domain services<br/>budgets · savings · investing · imports · transactions]
    asst[Assistant brain<br/>assistant/services.py]
    api["/api/me/ JSON"]
    hooks[Webhooks<br/>/assistant/photon-webhook/<br/>/assistant/bridge/<br/>/accounts/auth0/hooks/signup/]
  end
  db[(SQLite locally<br/>Postgres via DATABASE_URL)]
  adapter[spectrum/ Bun adapter<br/>spectrum-ts]
  auth0[Auth0 tenant]
  supa[Supabase Auth — optional]
  td[Twelve Data API — optional]

  user -->|HTTPS, session cookie| web
  web --> svc
  asst --> svc
  hooks --> asst
  svc --> db
  web <-->|OIDC redirect, Management API| auth0
  api -->|JWKS| auth0
  web -.->|email/password REST| supa
  svc -.->|quotes and history| td
  phone <--> photon[Photon Spectrum cloud]
  photon <--> adapter
  adapter -->|POST + bridge secret| hooks
```

Solid lines are implemented and exercised by tests. Dotted lines are implemented but optional (off without credentials). There is **no** bank, brokerage, email, or SMS provider.

## 2. Components

| Django app | Responsibility | Key modules |
|---|---|---|
| `core` | Landing, dashboard, insights, money helpers, chart helpers, template filters, seed commands | `views.py`, `services.py` (`quantize_money`, `round_up_to_nearest`), `display.py`, `context_processors.py` |
| `accounts` | Profile, Auth0/Supabase identity, verification, onboarding, manual setup, settings, notification log, signup backup | `auth0.py`, `identity.py`, `middleware.py`, `verification.py`, `supabase_auth.py`, `auth0_backup.py`, `tokens.py`, `api.py`, `manual_setup.py` |
| `transactions` | Accounts (statement containers), categories, transactions, running balances, reconciliation | `models.py`, `services.py` |
| `budgets` | Income sources, recurring expenses, periods, category limits, plan math, transactions UI | `services.py`, `views.py`, `forms.py` |
| `savings` | Goals/pools, contributions, debts, personalized savings plan engine | `plan_engine.py`, `services.py`, `signals.py` |
| `investing` | Round-up settings and ledger, simulated orders, portfolio snapshots, demo funds/ideas, Twelve Data cache | `services.py`, `signals.py`, `live_quotes.py` |
| `imports` | CSV upload → account → review → commit | `pipeline.py`, `csv_enhanced.py`, `views.py` |
| `assistant` | Intent parsing, confirmations, chat linking, Spectrum transports | `intents.py`, `services.py`, `routing.py`, `linking.py`, `spectrum.py`, `views.py` |

The front end is Django templates (`templates/`) plus one stylesheet and small vanilla-JS files (`static/js/finovate.js`, market chart scripts). There is no SPA or build step. Browser ↔ server communication is HTML form posts with CSRF tokens, plus a few JSON endpoints: theme/name updates and live quotes.

Views stay thin and call service functions. The assistant calls the **same** services, so the website and chat cannot disagree.

## 3. Data model (core entities)

```mermaid
erDiagram
  USER ||--|| PROFILE : has
  USER ||--o{ TRANSACTION : records
  USER ||--o{ CATEGORY : defines
  USER ||--o{ ACCOUNT : imports_into
  ACCOUNT ||--o{ TRANSACTION : contains
  CATEGORY ||--o{ TRANSACTION : classifies
  USER ||--o{ INCOME_SOURCE : declares
  USER ||--o{ RECURRING_EXPENSE : declares
  USER ||--o{ BUDGET_PERIOD : plans
  BUDGET_PERIOD ||--o{ BUDGET : limits
  CATEGORY ||--o{ BUDGET : capped_by
  USER ||--o{ GOAL : saves_toward
  GOAL ||--o{ CONTRIBUTION : changes
  USER ||--o{ DEBT_OBLIGATION : owes
  USER ||--|| SAVINGS_PLAN : receives
  SAVINGS_PLAN ||--o{ SAVINGS_PLAN_REVISION : history
  USER ||--|| ROUNDUP_SETTINGS : configures
  TRANSACTION ||--o| ROUNDUP_LEDGER_ENTRY : rounds_up
  USER ||--o{ SIMULATED_ORDER : proposes
  GOAL ||--o{ SIMULATED_ORDER : pool_for
  USER ||--o{ PORTFOLIO_SNAPSHOT : tracks
  USER ||--o{ IMPORT_BATCH : uploads
  USER ||--o{ NOTIFICATION_EVENT : logs
```

31 models in total. Important constraints:

- `Transaction.amount` is always positive; `kind` (income/expense) carries the sign. Unique `(user, source, external_id)` when `external_id` is set, which makes imports idempotent.
- `RoundUpLedgerEntry.source_transaction` is one-to-one: one round-up per purchase.
- `Goal (user, system_key)` is unique for the three engine pools.
- `Profile.auth0_sub` and `Profile.supabase_uid` are unique. **Accounts are never merged by email.**
- All money is `DecimalField(max_digits=12, decimal_places=2)` and is quantized half-up to cents (`core/services.py`).

## 4. Authentication and authorization

```mermaid
sequenceDiagram
  participant B as Browser
  participant D as Django
  participant A as Auth0
  B->>D: POST /accounts/signup/ (name, email)
  D->>B: 302 to Auth0 /authorize (screen_hint=signup), encrypted _a0_tx cookie
  B->>A: Universal Login (password handled by Auth0)
  A->>B: 302 /callback?code=…
  B->>D: GET /callback
  D->>A: Exchange code (SDK validates tokens)
  D->>D: Find or create Profile by sub, record verification state
  alt email not verified
    D->>B: 302 /accounts/verify/ (Management API refresh available)
  else verified
    D->>B: 302 onboarding or dashboard (session + _a0_session cookie)
  end
```

- **Session:** Django session (8 h, HTTP-only, `SameSite=Lax`, `Secure` when the base URL is HTTPS) plus the encrypted Auth0 state cookie. `Auth0SessionMiddleware` refreshes the access token 60 s before expiry and logs the user out if refresh fails. Unverified Auth0 users are confined to `/accounts/verify…` and logout.
- **Authorization:** every view that touches user data is `@login_required`. The public endpoints are the landing page, login/signup, `/accounts/verify/result/`, the three webhook endpoints (secret- or signature-authenticated), and `/api/me/` (token-authenticated). Every query filters on `user=request.user` or uses `get_object_or_404(..., user=request.user)`. Isolation tests cover goals, manual estimates, chat, and the API.
- **API:** `/api/me/` accepts only an RS256 access token for `AUTH0_AUDIENCE` (JWKS cached 10 min); the session cookie is not accepted.
- **Supabase** (optional) signs in by REST and maps by Supabase user ID.

## 5. Money flows

### Transactions → budgets → plan

1. Transactions arrive from manual entry (`/budgets/transactions/add/`), CSV import (`imports/pipeline.py`), the assistant ("I got paid…"), or seed commands.
2. A `post_save` signal (`investing/signals.py`) creates a **pending** round-up for each new eligible expense, and updates or reverses it when the purchase is edited.
3. Changes to income sources, recurring expenses, budgets, periods, or debts trigger `refresh_savings_plan` **after the database commit** (`savings/signals.py`). Revisions and notifications are recorded only for material changes (≥ $25 or ≥ 5%, or a scenario change).

### Round-up lifecycle (simulated)

```mermaid
stateDiagram-v2
  [*] --> Pending: expense saved, round-ups enabled and not paused
  Pending --> Reversed: purchase edited to income/reversal, or amount rounds to 0
  Pending --> Swept: "Simulate a sweep now" — within cash reserve and cap
  Swept --> [*]: adds to SimulatedOrder (filled) and PortfolioSnapshot
```

Sweeps lock `RoundUpSettings` so concurrent sweeps run in series. Market value after a sweep equals contributions (no simulated drift).

### Investment proposals (simulated)

Propose → `SimulatedOrder(status=pending)` → Approve or Reject. Approval locks the order row, refuses anything not pending, then updates the pool/general `PortfolioSnapshot`. Proposals are capped at `max_surplus_proposal(user)`, so pending and filled orders use up the surplus.

## 6. Messaging

```mermaid
sequenceDiagram
  participant P as iMessage via Photon Spectrum
  participant N as spectrum/ adapter (Bun)
  participant D as Django /assistant/bridge/
  participant S as assistant services
  P->>N: inbound text
  N->>D: POST {chat_id, text, message_id} + X-Finovate-Bridge-Secret
  D->>D: dedupe on (delivery_id, message_id)
  D->>S: linked chat? → handle_incoming_message
  S-->>D: reply (or confirmation prompt)
  D-->>N: {reply}
  N->>P: message.reply(reply)
```

The alternative `/assistant/photon-webhook/` path verifies Spectrum HMAC signatures and returns the reply in JSON without sending (`delivered: false`).

## 7. Background jobs, notifications, retries

- **No scheduler or worker.** Work happens in-request or in `transaction.on_commit` callbacks. Management commands: `seed_demo`, `seed_peachtree_demo`, `seed_market_data`, `seed_excel_demo_market`, `reconcile_auth0_backups` (retries failed signup-backup rows), `chat_demo`.
- **Notifications:** `NotificationEvent` rows (account created, welcome, goal milestone, round-ups paused, savings plan, system). Shown in Settings; never sent externally.
- **Retries and idempotency:** Auth0 profile creation retries username collisions; signup backups retry via the command; Twelve Data uses leases plus a 5-minute retry delay; imports and bridge deliveries are idempotent; failed imports are marked `failed` and can be retried.

## 8. Errors, logging, monitoring

- Form errors render inline or as flash messages. Provider failures show user-safe messages (`SupabaseAuthError`, Twelve Data "not available", verification "unavailable").
- Logging is structured console output (`level=… logger=…`). The code comments forbid logging amounts or account details, and log calls record events and codes only.
- There is no external monitoring (Sentry, Datadog, etc.).

## 9. Deployment

| Aspect | Local | Vercel (`vercel.json`) |
|---|---|---|
| Entry | `manage.py runserver` | `finovate/wsgi.py` (60 s max) |
| Debug | On | Off unless `FINOVATE_DEBUG` |
| Hosts | `localhost`, `127.0.0.1` | `.vercel.app`, `finovate.biz`, `www.finovate.biz` |
| Database | `db.sqlite3` | `/tmp/finovate.sqlite3` (ephemeral) unless `DATABASE_URL` |
| Boot | — | `migrate`; seed `demo` if `DEMO_ACCOUNT_PASSWORD` set |
| Static | `runserver` serves `static/` | Vercel Django preset (not verified here) |

Production health could not be verified from this environment (see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)). Environment variables are listed in the [README](../README.md#environment-variables-names-only).

## 10. Security boundaries

Browser ↔ Django (CSRF, session), Django ↔ Auth0 (server-side secret, encrypted cookies), adapter ↔ Django (shared bridge secret, constant-time compare), Photon ↔ Django (HMAC signature, 5-minute replay window), Auth0 Action ↔ Django (shared secret). Detail and gaps: [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md).

## 11. Technical debt

- `auth0-server-python` beta; `authlib.jose` deprecated.
- `LocMemCache` for rate limits and JWKS/token caches (per process).
- Bundled market sample loaded but unused by views; redundant calculator code in `finovate.js`.
- Dashboard and context processor recompute surplus and plan on each request (fine at demo scale).
- No pagination; no scheduled jobs; signup backup stored in the same database it backs up.

## 12. Proposed (not implemented) architecture

> **Proposed only.** Nothing in this diagram beyond the existing Django app is built.

```mermaid
flowchart LR
  app[Finovate Django] --> q[Task queue / scheduler]
  q --> weekly[Weekly summary job]
  app -.read-only.-> bank[Bank data aggregator]
  app -.orders with explicit consent.-> broker[Brokerage API]
  q --> notify[Email / push / Photon outbound]
```

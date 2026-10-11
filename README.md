# Finovate

Finovate is a personal finance app: track spending, plan a budget, work
toward savings goals, and preview a simulated round-up/ETF investing
experience — all running locally with no external accounts required.

This is a working local prototype, not a finished product. Read "Known
limitations" before relying on it for anything real.

## Stack and why

- **Backend/framework:** Django 6.1 (Python). Chosen over FastAPI because
  this app is mostly CRUD + forms + per-user data + an admin UI for a
  learning-stage project — Django's built-in ORM, migrations, auth system,
  and admin give a lot of structure for free, and avoid needing a separate
  frontend build toolchain.
- **Frontend:** Django templates + Tailwind (via CDN, no Node build step)
  + Chart.js for the dashboard chart. Kept deliberately simple — no SPA
  framework, no bundler — so there's one moving part (`manage.py
  runserver`) to run locally.
- **Database:** SQLite for local development, accessed only through the
  Django ORM/migrations, so moving to Postgres later is a `DATABASES`
  setting change, not a rewrite.
- **Money:** every amount is a Python `Decimal` / Django `DecimalField`.
  Floats are never used for currency math — see `core/services.py`.

## Running locally

```bash
cd Finovate
python -m venv .venv
# Windows (Git Bash): source .venv/Scripts/activate
# macOS/Linux:        source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo          # creates user "demo" / password "demo-pass-1234"
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`. New accounts register through Auth0.
Until `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, and
`AUTH0_SECRET` are set, the login and signup pages stay unavailable and
do not create a local password user. `seed_demo` still inserts a fixture
user for management commands such as `chat_demo`; that fixture is not a
website login.

To create an admin user for `/admin/`: `python manage.py createsuperuser`.

### Configuration

Copy `.env.example` to `.env` to override any setting. **The app runs
with no `.env` file at all** — nothing is required to get started.
`python manage.py seed_demo` creates a local fixture user named `demo`
(password `demo-pass-1234` while `DEBUG` is true). That password is
refused when `DEBUG` is false unless `DEMO_ACCOUNT_PASSWORD` is set.
The website does not offer that password as a login. Auth0 is the
identity provider for accounts created from the site.

### Optional: Auth0 login and Supabase/Postgres database

Both are off by default — the app runs fully on local demo auth + SQLite
with no configuration. To turn either on, add to `.env`:

```bash
# Auth0 — required for website signup and login. Credentials live in
# .env.local (written by Auth0 onboarding). The app callback is
# <APP_BASE_URL>/callback. Run the server on that same origin, for example:
#   python manage.py runserver localhost:5000
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_CLIENT_ID=...
AUTH0_CLIENT_SECRET=...
AUTH0_SECRET=...
AUTH0_AUDIENCE=https://finovate.biz/api
APP_BASE_URL=http://localhost:5000

# Supabase/Postgres — switches off SQLite. Use the pooled connection
# string from Project Settings -> Database in your Supabase project.
DATABASE_URL=postgresql://...
```

See [docs/architecture-auth0-supabase.md](docs/architecture-auth0-supabase.md)
for how identity mapping and database connectivity work, and exactly
what's unverified until you've configured real credentials.

## Testing

```bash
python manage.py test
```

35 tests cover: round-up math (including the exact $4.35 → $0.65 example
from the spec), idempotent transaction imports (duplicate `external_id`
never double-counts), budget progress/plan calculations and
recalculation when inputs change, savings goal milestone crossing and
completion estimates, round-up sweep behavior (cash reserve and
contribution cap enforcement), and per-user data isolation on views.

## Architecture overview

Six Django apps, each owning one slice of the domain:

| App | Owns |
|---|---|
| `core` | Landing page, dashboard, shared `Decimal` money helpers |
| `accounts` | User `Profile` preferences, demo auth views, notification/audit events, connected-account placeholders |
| `transactions` | `Category`, `Transaction`, idempotent-import helper |
| `budgets` | `BudgetPeriod`, `Budget`, `IncomeSource`, `RecurringExpense`, the budget-plan calculator |
| `savings` | `Goal`, `Contribution`, milestone + completion-estimate logic |
| `investing` | Simulated `RoundUpSettings`, `RoundUpLedgerEntry`, `PortfolioSnapshot`, `SimulatedOrder` |
| `imports` | CSV bank-statement upload → review → commit pipeline, `ImportBatch` tracking. See [docs/bank-statement-import.md](docs/bank-statement-import.md) |

Each app's `services.py` holds pure business logic (no HTTP, no
templates) so it's independently testable and so a future messaging
integration could call the same functions the website calls, without
duplicating logic. Views stay thin: fetch data, call a service, render a
template.

**Per-user ownership:** every query that touches user data filters by
`user=request.user` (or goes through a `ForeignKey`/`get_object_or_404`
that includes it), so one user can never read or edit another's records.
See the isolation tests in `budgets/tests.py`.

## Demo mode and sample data

`python manage.py seed_demo` creates a local user named `demo` with
transactions, categories, a budget period with limits, income/recurring
expenses, two savings goals with contribution history, and pre-populated
round-up ledger entries (including one already swept into a simulated
portfolio snapshot). Seeded rows keep `source="demo"` / `is_demo=True` so
the data stays isolated from records a person enters. The interface does
not label those rows. Re-running the command updates the same records by
`external_id` and does not wipe them on startup.

## What's simulated vs. real

- **Real:** everything you enter yourself — transactions, categories,
  budgets, goals, contributions — persists in SQLite and survives
  restarts. Budget-plan math and round-up math run for real on your data.
  CSV bank-statement import is also real: it creates ordinary
  `Transaction` rows after a review step, with duplicate detection and no
  fabricated data. See [docs/bank-statement-import.md](docs/bank-statement-import.md)
  for supported formats and limitations.
- **Simulated, clearly labeled:** the entire Investing page. No brokerage
  is connected; "sweeping" round-ups and "filling" orders are local
  database updates, not real trades. The investing page and dashboard
  both carry explicit "simulated" labels and risk disclaimers.
  - **Sample-data explorer and demo recommendations:** database migrations
    load the supplied 109-row historical sample. Users can browse each
    stock/index history and create budget-limited simulated orders from the
    Explore page; the Investing page also offers transparent rule-based
    ideas for explicit user acceptance or decline. Refresh sample rows with
    `python manage.py seed_excel_demo_market`; see
    [docs/demo-ai-investing.md](docs/demo-ai-investing.md).
- **Identity:** Auth0 is the account provider when configured. A local
  login remains for this server.
- **Messaging:** Photon Spectrum inbound webhooks are verified. Outbound
  iMessage is sent by the Node adapter in `spectrum/`. See
  `docs/messaging-assistant.md`.
- **Not connected:** bank feeds and brokerages. See
  `docs/integration-readiness.md`.

## Known limitations

- Tailwind and Chart.js are loaded from public CDNs without Subresource
  Integrity hashes — fine for local development, but should be
  self-hosted or pinned with SRI before any real deployment.
- No pagination on the transaction list or ledger views yet; fine for
  demo-scale data, would need adding for a real account with years of
  history.
- The budget-plan "suggested savings" target is a simple heuristic
  (remaining goal amount ÷ 12 months), not a solver that balances
  multiple competing goals.
- Notification events are recorded (`accounts.NotificationEvent`) but
  nothing delivers them yet — there's no email/push/SMS sender wired up,
  by design (see integration-readiness guide).
- No CSS/JS build pipeline means no minification/tree-shaking; acceptable
  for a local prototype, not for production traffic.
- Browser-based UI testing was done by inspecting templates and running
  the Django test client against views, not a full headless-browser
  click-through of every page.

## Next steps

- Add a `BudgetPeriod` auto-rollover (new month → new period) instead of
  requiring manual creation.
- Pagination for transactions/ledger history.
- Wire `NotificationEvent` creation up to an actual delivery channel once
  one is configured (see integration-readiness guide).
- Decide on and implement the first real integration (most likely the
  identity provider, since it touches every page) when credentials are
  available.

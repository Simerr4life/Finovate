# Feature and route inventory

**Last reviewed:** 2026-10-11

## Primary navigation

| Nav label | Destination |
|---|---|
| Overview | `/dashboard/` |
| Transactions | `/budgets/transactions/` |
| Savings | `/savings/` |
| Pools | `/savings/pools/` |
| Investments | `/investing/` |
| Financial Goals | `/savings/goals/` |
| Insights | `/insights/` |
| Settings | `/accounts/settings/` |

## Route map (verified)

### Core
- `GET /` → `landing`
- `GET /dashboard/` → `dashboard` (login)
- `GET /insights/` → `insights` (login)

### Accounts
- `/accounts/signup|login|logout/`
- `/accounts/verify/`, `verify/resend/`, `verify/refresh/`
- `/accounts/onboarding/`, `onboarding/preferences/`
- `/accounts/manual-setup/`, `manual-setup/summary/`
- `/accounts/settings/`, `settings/messaging/link|unlink/`
- `/accounts/auth0/login/`, `/accounts/auth0/callback/`, root `/callback/`
- `GET /api/me/` (Bearer Auth0 access token)

### Budgets / transactions
- `/budgets/` index; periods/limits/income/expenses CRUD
- `/budgets/transactions/` list, add, edit, delete, CSV export
- `/budgets/categories/` add/delete

### Statements
- `/statements/`, `/statements/<pk>/`

### Imports
- `/imports/` history; `upload/`; `<pk>/account|preview|retry|delete/`

### Savings
- `/savings/`, `plan/` (+ refresh/status/allocations), `debts/` (+ add/edit)
- `pools/`, `goals/`, `add/`, `<pk>/`, edit, delete

### Investing
- `/investing/` portfolio tools
- demo budget add; demo-ai generate/accept/decline
- sweep; surplus propose; order approve/reject
- `market-data/`, `historical-demo/`, live-quotes JSON endpoints

### Assistant
- `POST /assistant/photon-webhook/`

### Admin
- `/admin/`

## Feature → code map

| Feature | Key files |
|---|---|
| Dashboard | `core/views.py`, `templates/core/dashboard.html` |
| Budgets | `budgets/services.py`, `budgets/views.py` |
| Transactions | `transactions/services.py`, `budgets/views.py` (UI) |
| Imports | `imports/pipeline.py`, `imports/views.py` |
| Savings plan | `savings/plan_engine.py`, `docs/savings-plan-engine.md` |
| Goals | `savings/services.py`, `savings/views.py` |
| Investing | `investing/services.py`, `investing/live_quotes.py` |
| Auth | `accounts/auth0.py`, `supabase_auth.py`, `identity.py` |
| Assistant | `assistant/services.py`, `intents.py`, `spectrum.py` |

## Incomplete / stub features

| Item | Evidence |
|---|---|
| Bank connect | Onboarding “coming soon”; `BANK_PROVIDER_API_KEY` unused |
| Real brokerage | Investing fully simulated; `BROKERAGE_PROVIDER_API_KEY` unused |
| Notification delivery | `NotificationEvent.delivery_status` stays `recorded` |
| Outbound iMessage | Webhook `delivered: false`; Spectrum Bun app is echo |
| Non-CSV imports | Only `csv` in `SOURCE_FORMAT_CHOICES` |
| Pagination | Not on transaction/ledger lists |
| Budget period rollover | Listed as next step in root README |

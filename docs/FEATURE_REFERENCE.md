# Feature Reference

Technical reference for each feature, based on the code in this repository. Status legend: ✅ verified · 🟡 implemented, not fully tested · 🟠 partial · 🧪 simulated · 📝 planned · ⛔ blocked.

## Verified feature inventory

| Area | Status | Evidence | Gap |
|---|---|---|---|
| Authentication | 🟡 implemented, mock-tested · ⛔ live tenant | `accounts/auth0.py`, `views.py`; account test modules (89 tests, mostly identity); unconfigured-state screenshot 02 | Live Auth0 run |
| Onboarding | ✅ | Screenshots 03, 03b, 04; manual-setup tests | Bank connect 📝 |
| Dashboard | ✅ | Screenshot 05; crawl + browser flows; chart tests | — |
| Budgeting | ✅ | `budgets/services.py`; 24 tests; screenshot 09; flow 1 | Warnings visual only |
| Transactions & import | ✅ | 57 import tests; flows 2–3; screenshots 07, 10, 11 | CSV only; no auto-categorization |
| Savings goals | ✅ | `savings/services.py`; flows 4–5; screenshots 14, 15, 21 | No pause/archive |
| Savings plan | ✅ | `plan_engine.py`; 12 + 16 tests; screenshot 13 | Keyword expense classification |
| Round-ups | ✅ math/lifecycle · 🧪 sweep | `test_example_from_spec`; flow 2; screenshot 16 | No posted/pending distinction |
| Investing | 🧪 simulated · ⛔ market data | `investing/services.py`; 80 tests; screenshots 16–18 | No brokerage; needs Twelve Data key |
| Reports / insights | 🟠 | `/insights/` screenshot 19 | No weekly summaries or alerts |
| Messaging | ✅ in-process/bridge · ⛔ live iMessage | 43 tests; transcript T-MSG-01; bridge dedupe T-MSG-02 | Live Photon run |
| Notifications | 🟠 recorded only | Settings → Notification history | No delivery; no budget-warning events |
| Settings | ✅ | Screenshot 20; theme/name tests | No account deletion |
| Security | ✅ core controls | [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) | HSTS/CSP, secret-key fallback |
| Mobile responsiveness | ✅ (emulated 390 px) | No-overflow check on 23 pages; screenshots 23–26 | Not tested on physical devices |

Screenshot numbers refer to [SCREENSHOT_CATALOG.md](SCREENSHOT_CATALOG.md); test and flow IDs to [TESTING_AND_VALIDATION.md](TESTING_AND_VALIDATION.md).

**Contents:** [1 Authentication](#1-authentication) · [2 Onboarding and manual setup](#2-onboarding-and-manual-setup) · [3 Dashboard](#3-dashboard) · [4 Transactions](#4-transactions) · [5 Statement import](#5-csv-statement-import) · [6 Statements and reconciliation](#6-statements-and-reconciliation) · [7 Budgeting](#7-budgeting) · [8 Savings goals and pools](#8-savings-goals-and-pools) · [9 Savings plan engine](#9-savings-plan-engine) · [10 Round-ups](#10-round-ups) · [11 Simulated investing](#11-simulated-investing) · [12 Market data](#12-market-data-twelve-data) · [13 Insights](#13-insights) · [14 Messaging assistant](#14-messaging-assistant) · [15 Notifications](#15-notifications) · [16 Settings](#16-settings) · [17 Protected API](#17-protected-api)

---

## 1. Authentication

| | |
|---|---|
| **Purpose** | Create accounts and sign in without Finovate storing passwords |
| **Entry points** | `/accounts/signup/`, `/accounts/login/`, `/accounts/auth0/login/`, `/callback/`, `POST /accounts/logout/`, `/accounts/verify/` (+ `result/`, `resend/`, `refresh/`), `POST /accounts/auth0/hooks/signup/` |
| **Code** | `accounts/views.py` (signup, login_view, auth0_callback, auth0_logout, verification_*), `accounts/auth0.py`, `accounts/identity.py`, `accounts/verification.py`, `accounts/supabase_auth.py`, `accounts/middleware.py`, `accounts/auth0_backup.py` |
| **Data** | `Profile` (`auth0_sub`, `supabase_uid`, `email_verified`, `identity_status`, `phone_number`, `phone_verified`), `Auth0UserBackup`, `NotificationEvent` |
| **External** | Auth0 (Universal Login, Management API), Supabase Auth (optional) |
| **Rules** | Lookup by provider ID only; unverified Auth0 users are confined to the verify page; verification never comes from query strings; `next` sanitized; rate limits on login/signup/resend |
| **Errors** | Provider not configured → message on the login page; blocked account → "This account is blocked or disabled."; token exchange failure → "Authentication failed." with no user created |
| **Status** | 🟡 implemented and mock-tested; ⛔ live tenant not exercised here |
| **Tests** | `accounts/tests.py`, `accounts/test_verification_backup.py`, `accounts/test_audit_fixes.py` |
| **Limits** | No local password login by design; password reset is in the provider's hosted pages |

## 2. Onboarding and manual setup

| | |
|---|---|
| **Purpose** | Get a new user to useful numbers quickly |
| **Entry points** | `/accounts/onboarding/` (choose: Import a statement · Connect a bank — *coming soon* · Enter finances manually · Skip), `/accounts/onboarding/preferences/`, `/accounts/manual-setup/`, `/accounts/manual-setup/summary/` |
| **Code** | `accounts/views.py::onboarding*`, `manual_setup*`; `accounts/manual_setup.py`; `accounts/forms.py::OnboardingForm, ManualSetupForm` |
| **Data** | `Profile` (income cadence, risk comfort, cash reserve, warning threshold, notification flags, phone, messaging consent, manual savings fields); `IncomeSource`/`RecurringExpense` rows named "… (estimate)" |
| **Rules** | Manual setup writes ordinary income/expense rows so `build_budget_plan` is the only calculation. A category breakdown replaces the lump-sum total (never both). Resubmitting updates the same rows. It never creates transactions |
| **Validation** | Amounts 0 to 10,000,000; warning threshold 1–100%; reserve ≥ 0; phone 8–15 digits |
| **Status** | ✅ (browser-verified screens; tests in `accounts/tests.py`) · bank connection 📝 |

## 3. Dashboard

| | |
|---|---|
| **Entry point** | `/dashboard/` (`?range=1W|1M|3M|6M|1Y`) |
| **Code** | `core/views.py::dashboard`, `core/display.py` |
| **Shows** | Total cash (all-time income − expenses), this month's income vs. planned income, this month's spending and remaining budget room, *Available to save* (savings plan safe-to-save), cash-balance chart, savings opportunity breakdown with *Review savings plan* modal, recent transactions, budget progress, goals, pending round-ups, latest simulated portfolio snapshot |
| **Rules** | Cash, goal allocations, pending round-ups, and simulated portfolio value are shown as separate figures. The chart uses recorded transactions only (1W and 1M daily, longer ranges monthly) |
| **Status** | ✅ ([screenshot](assets/screenshots/submission/05-dashboard.png)) |

## 4. Transactions

| | |
|---|---|
| **Entry points** | `/budgets/transactions/` (search `q`, `category`, `month`), `add/`, `<id>/edit/`, `<id>/delete/` (confirmation page), `export/` (CSV) |
| **Code** | `budgets/views.py`, `budgets/forms.py::TransactionForm`, `transactions/models.py`, `transactions/services.py::record_transaction` |
| **Data** | `Transaction` (kind, positive amount, category, account, description, date, source `manual|imported|demo`, `external_id`, `reverses`, `is_demo`) |
| **Validation** | Amount > 0; category must belong to the user and match the kind |
| **Side effects** | New expenses create pending round-ups when enabled; edits update or reverse a pending round-up |
| **Status** | ✅ (browser flows 2–3; tests) |
| **Limits** | No pagination; no automatic categorization; refunds can't be linked from the UI |

## 5. CSV statement import

| | |
|---|---|
| **Flow** | `/imports/upload/` → `/imports/<id>/account/` (pick or create an account; only the last few digits, at most six, are stored) → `/imports/<id>/preview/` (ready / duplicates / needs review) → commit → `/imports/<id>/`; history at `/imports/` with retry and delete |
| **Code** | `imports/pipeline.py` (classic parser), `imports/csv_enhanced.py` (preambles, `;`/tab delimiters, European decimals, DR/CR columns), `imports/views.py` |
| **Data** | `ImportBatch` (raw bytes ≤ 2 MB, detected mapping, counts, warnings, status draft/committed/failed) |
| **Rules** | Content-based decoding (rejects binary); automatic column detection; amount from amount/net/debit-credit, and if several are present they must agree or the row is flagged; non-USD rows flagged; `external_id` = bank reference or a fingerprint of account + date + amount + kind + description; existing IDs are skipped; identical rows within one file are flagged, never guessed; commit is atomic |
| **Status** | ✅ (57 tests) |
| **Limits** | CSV only; imported rows are uncategorized; flagged rows must be entered manually |

## 6. Statements and reconciliation

`/statements/` and `/statements/<id>/` (`transactions/views.py`, `transactions/services.py`). Running balance = opening balance + signed transactions, in date order. **Reconciliation** recomputes deposits, withdrawals, and ending balance (`ending = opening + deposits − withdrawals`) and compares each with the statement's stated totals, so a mismatch is shown rather than hidden. The fictional *Peachtree Student Banking* seed reconciles exactly. ✅ ([screenshot](assets/screenshots/submission/10-statement-reconciliation.png))

## 7. Budgeting

| | |
|---|---|
| **Entry point** | `/budgets/` (forms post to `income/add`, `expenses/add`, `categories/add`, `periods/add`, `limits/add` and their delete routes) |
| **Code** | `budgets/services.py` (`monthly_equivalent`, `compute_budget_progress`, `build_budget_plan`, `monthly_summary`), `budgets/views.py`, `budgets/forms.py` |
| **Data** | `IncomeSource`, `RecurringExpense`, `BudgetPeriod` (one active), `Budget` (limit and warning % per expense category) |
| **Formulas** | Monthly equivalent: weekly × 4.33, biweekly × 2.17, monthly/irregular × 1. **Plan:** income = Σ active income (monthly); recurring = Σ active expenses (monthly); suggested toward goals = Σ over unachieved goals of remaining ÷ 12; left over = income − recurring − suggested. **Progress:** spent = Σ expense transactions in the category within the period; remaining = limit − spent; % used = ⌊spent ÷ limit × 100⌋; warning when % ≥ threshold and < 100; over at ≥ 100 |
| **Validation** | Amounts and limits > 0; threshold 1–100; end date ≥ start date; unique category name per kind; invalid submissions explained by a flash message |
| **Side effects** | Saving or deleting income, expenses, periods, or limits recalculates the savings plan after commit |
| **Status** | ✅ |
| **Limits** | No automatic period rollover; budget warnings are visual only (no notification) |

## 8. Savings goals and pools

| | |
|---|---|
| **Entry points** | `/savings/` (overview), `/savings/goals/`, `/savings/pools/`, `/savings/add/`, `/savings/<id>/` (contributions), `<id>/edit/`, `<id>/delete/` |
| **Code** | `savings/views.py`, `savings/services.py` (`apply_contribution`, `estimate_completion_date`, `contribution_pace`), `savings/models.py::Goal.sync_achieved` |
| **Data** | `Goal` (target, current cash, target date, colour, `is_investable`, `system_key`, `achieved_at`, `highest_milestone_notified`), `Contribution` (contribution/withdrawal/adjustment) |
| **Formulas** | Progress = min(current ÷ target, 100%). Remaining = max(target − current, 0). **Pace** for a dated goal = remaining ÷ days left × 365.25, shown per year, per month (÷ 12), and per week (÷ 52). **Projected completion** = today + remaining ÷ (net contributions over the last 90 days ÷ 90), only when net progress is positive and under 50 years. Milestones at 25/50/75/100% are notified once each |
| **Validation** | Target > 0; current ≥ 0; contribution > 0; withdrawals cannot exceed the balance; contributions lock the goal row |
| **Rules** | Three engine pools (Rainy Day, Investment, Regular Savings) are created automatically and cannot be deleted. The Investment pool stays investable. Goal cash is separate from invested amounts |
| **Status** | ✅ |
| **Limits** | No pause/archive |

## 9. Savings plan engine

| | |
|---|---|
| **Entry point** | `/savings/plan/` (Recalculate, Pause / Resume / Disable / *Turn recommendations back on*, edit allocation percents), `/savings/debts/` |
| **Code** | `savings/plan_engine.py` (`analyze_finances`, `choose_scenario`, `build_recommendation`, `refresh_savings_plan`), `savings/signals.py` |
| **Data** | `SavingsPlan` (one per user), `SavingsPlanRevision`, `DebtObligation` |
| **Analysis** | Income = active sources (fallback: earned income over the last 90 days ÷ 3). Expenses split into essential/discretionary by name keywords (unknown = essential); debt minimums are added if no debt-named expense exists. Surplus = income − expenses. Buffer = cash reserve ÷ 3 + 25% of essentials (50% if income is irregular). **Safe-to-save = max(0, surplus − buffer).** Emergency starter = clamp(essentials, $500, $1,000); full target = essentials × 3 (× 6 if irregular). High-interest debt = APR ≥ 10% |
| **Scenarios** | Stabilization (expenses > income: allocate nothing) → Build reserve (80/5/15 rainy/invest/regular) → Debt focus (50% of safe-to-save to extra debt payments, remainder 20/10/20 normalized) → Strong (10/40/50) → Stable (40/20/40) |
| **Guarantees** | Allocations never exceed safe-to-save; goals that need more than safe-to-save get a realistic-timeline note; revisions and notifications only on material change; paused or disabled plans keep their status when recalculated |
| **Status** | ✅ (tests in `savings/test_plan_engine.py`, audit tests) |
| **Limits** | Keyword classification of expenses; recommendations only, never transfers |

## 10. Round-ups

| | |
|---|---|
| **Entry point** | `/investing/` → *Round-up settings*, *Round-up ledger*, *Simulate a sweep now* |
| **Code** | `core/services.py::round_up_to_nearest`, `investing/signals.py`, `investing/services.py` (`create_roundup_for_transaction`, `reverse_roundup_for_transaction`, `sweep_pending_roundups`) |
| **Data** | `RoundUpSettings` (enabled, paused, round_to, cap per period, minimum cash reserve, target investable pool), `RoundUpLedgerEntry` (eligible amount, round-up, status pending/swept/reversed) |
| **Rules** | Eligible = expense, not a reversal, round-ups enabled and not paused. Round-up = next multiple of `round_to` − amount (**$4.35 → $0.65**; exact multiples → $0, no entry). One entry per transaction. **Sweep:** limit = min(pending total, cap, cash balance − reserve); entries are taken oldest first while they fit; results in a filled `SimulatedOrder` and an updated `PortfolioSnapshot` |
| **Status** | ✅ math and lifecycle · 🧪 sweeping is simulated |
| **Limits** | No posted/pending transaction distinction; transfers are not excluded automatically |

## 11. Simulated investing

| | |
|---|---|
| **Entry point** | `/investing/` tabs *Portfolio*, *Explore*, *My investments*, *Calculator*; `/investing/historical-demo/`, `/investing/market-data/` |
| **Code** | `investing/views.py`, `investing/services.py` |
| **Data** | `SimulatedOrder` (pending/filled/rejected/cancelled; price source), `PortfolioSnapshot` (net contributions vs. market value), `DemoInvestmentFunding` (virtual top-ups), `DemoInvestmentSuggestion` |
| **Formulas** | **Investable surplus** = max(0, cash balance − minimum cash reserve − cash in unachieved goals − one month of recurring expenses). **Max proposal** = min(investable surplus, demo budget), where demo budget = surplus + investable-pool cash + virtual funds − pending/filled orders. Gain/loss = market value − net contributions. Calculator: FV = start × (1+r)^n + monthly × ((1+r/12)^(12n) − 1)/(r/12) |
| **Rules** | Proposals stay pending until *Approve*; approval locks the row and refuses non-pending orders; orders priced from old bundled samples cannot be approved |
| **Status** | 🧪 simulated throughout, clearly labeled; ✅ logic tested |
| **Limits** | No brokerage; swept/approved market value equals contributions (no drift) |

## 12. Market data (Twelve Data)

`investing/live_quotes.py`: supported symbols AAPL, AMZN, GOOGL, MSFT, NVDA. Quotes cached 5 minutes, 90-day history cached 12 hours, with a shared quota of 8 credits/minute and 800/day, fetch leases, and a 5-minute retry after failures. Live refresh only during US regular market hours for the JSON endpoints. Feeds *Explore*, *My investments* valuation, demo ideas (ranked by historical return − daily volatility, capped at $75 split across up to three ideas), and the price-based scenario. ⛔ without `TWELVE_DATA_API_KEY` (shows "not available").

## 13. Insights

`/insights/` (`core/views.py::insights`): this month vs. last month income and spending, six-month bars, top four categories (donut), biggest category decrease and increase (including categories that dropped to $0), average monthly income and spending over months with activity, savings rate = (income − spending) ÷ income this month, active recurring payments. ✅

## 14. Messaging assistant

| | |
|---|---|
| **Entry points** | `POST /assistant/bridge/`, `POST /assistant/photon-webhook/`, `python manage.py chat_demo`, Settings → link/unlink chat |
| **Code** | `assistant/intents.py`, `assistant/services.py`, `assistant/routing.py`, `assistant/linking.py`, `assistant/spectrum.py`, `spectrum/src/index.ts` |
| **Data** | `PendingConfirmation`, `ConversationMessage`, `MessagingLinkCode` (hashed), `SpectrumDelivery` (dedupe) |
| **Intents** | Immediate: help, budget status, goal status, portfolio performance, allocation, available to invest, invested this month, market status, pause round-ups, withdrawal (refused), monthly savings target (explains it isn't stored). Confirmation required: record income, set risk comfort, change a goal target, propose an investment, resume round-ups |
| **Status** | ✅ in-process and over the bridge · ⛔ live iMessage not exercised |

## 15. Notifications

`NotificationEvent` rows are created for account created, welcome, goal milestones (if enabled), round-ups paused (if budget-warning notifications are on), savings plan changes, and simulated proposals made by chat (if enabled). They are listed in Settings → Notification history, with an unread dot on the bell. 🟠 recorded only, no delivery; no budget-warning events (see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) K11–K13).

## 16. Settings

`/accounts/settings/`: display name (inline save), theme (light/dark/system, also via the header toggle, saved to the profile), income cadence, risk comfort, cash reserve, warning threshold, notification preferences, phone and messaging consent, messaging link code / unlink, connected-account placeholders, round-up summary, notification history, logout. ✅ · account deletion 📝

## 17. Protected API

`GET /api/me/` with `Authorization: Bearer <Auth0 access token>` returns `identity_status`, `email_verified`, and `transaction_count`. 401 for missing or invalid tokens; 403 without data for unverified users. ✅ rejection verified locally; 🟡 success path mock-tested.

# Finovate User Guide

For judges and first-time users. Labels below match the app's actual buttons and headings. Screens marked *(sample data)* in the screenshots use seeded demo records.

> **Everything investing-related is simulated.** No bank or brokerage is connected and no money moves.

## 1. Getting access

| Option | When to use | Steps |
|---|---|---|
| **A. Live site (recommended)** | Anytime | Open **https://finovate.biz** → **Get started** → **Continue with Auth0 (recommended)** → create the account on Auth0's page → confirm your email → you land on onboarding |
| **B. Local with Auth0 or Supabase** | You have tenant/project credentials | Set the variables listed in the [README](../README.md#environment-variables-names-only), run the server on the origin in `APP_BASE_URL`, then sign up as in A. With only Supabase set, use the email-and-password form |
| **C. Local walkthrough with sample data (no providers)** | Reviewing the code on your own machine | See below |

### Option C — local walkthrough

The website intentionally has no local password login. For a local review, Django's built-in admin login creates the same session:

```bash
python manage.py migrate
python manage.py seed_demo
python manage.py seed_peachtree_demo        # optional statement + reconciliation
python manage.py shell -c "from django.contrib.auth.models import User; u=User.objects.get(username='demo'); u.is_staff=True; u.save()"
python manage.py runserver
```

Open `http://127.0.0.1:8000/admin/`, sign in as `demo` / `demo-pass-1234` (accepted only while `DEBUG` is on), then go to `http://127.0.0.1:8000/dashboard/`.

> ⚠️ **Local development only.** Never give staff access to demo accounts on a deployed server. This works because of how Django sessions function; it is not a product feature.

**What to expect without providers:** `/accounts/login/` says *"Sign-in isn't configured on this server."* The Explore tab says Twelve Data history is not available. The assistant works through `python manage.py chat_demo --username demo`.

## 2. Onboarding

New accounts land on **Let's add some financial data** (`/accounts/onboarding/`):

- **Import a statement**: upload a bank CSV (section 5).
- **Connect a bank account — coming soon**: disabled; no bank connection exists.
- **Enter finances manually**: a one-page form (`/accounts/manual-setup/`) for take-home income, total monthly expenses *or* a category breakdown, current savings, minimum cash reserve, and monthly savings goal. Every field is optional. You'll see an estimate summary afterwards.
- **Skip for now**: go straight to preferences.

Then **preferences** (`/accounts/onboarding/preferences/`): income cadence, risk comfort, cash reserve, budget warning threshold (1–100%), notification choices, optional phone number and messaging consent. **Finish setup** completes onboarding and opens the dashboard.

## 3. Dashboard (Overview)

`/dashboard/`, *"Good morning/afternoon/evening, {name}."*

| Card | Meaning |
|---|---|
| **Total cash** | All recorded income minus all recorded expenses |
| **Monthly income** | Income recorded this month, with % of planned monthly income |
| **Monthly spending** | Expenses this month, and room left inside active budget limits |
| **Available to save** | The savings plan's monthly **safe-to-save** amount |
| **Cash & savings** chart | Balance over 1W / 1M / 3M / 6M / 1Y from recorded transactions; simulated portfolio value is stated separately |
| **Savings opportunity** | Cash balance minus bills buffer, goal allocations, and minimum reserve = **Available to consider**. **Review savings plan** opens a modal to save a *pending* simulated proposal |

### Understanding the numbers

- **Available to save** is a *monthly flow*: what your income can safely spare each month.
- **Available to consider / Investable surplus** is a *stock*: cash on hand after protecting reserves, goal money, and one month of bills.
- Neither one moves money.

## 4. Transactions

**Transactions** in the sidebar (`/budgets/transactions/`): search, filter by month or category, **Export CSV**, and **Add transaction** (Kind, Category, Amount, Description, Date). Amounts must be greater than $0, and the category must match the kind. Click a row to edit it; the edit page has **Delete this transaction**, which asks for confirmation.

If round-ups are enabled, a new expense immediately creates a *pending* round-up (section 8).

## 5. Importing a bank statement (CSV)

1. **Import a statement** (onboarding, Settings → Statement imports, or `/imports/upload/`), then choose a CSV of up to 2 MB.
2. **Choose account**: pick an existing account or create one (institution, type, *last few digits only*, opening balance).
3. **Review before importing**: *Ready to import* (tick or untick rows), *Likely duplicates — will be skipped*, *Needs review — not imported* (unreadable rows or identical rows within the file).
4. **Confirm import** → summary with counts → **Go to dashboard** (or **Continue setup** during onboarding).

Unreadable files go to a page offering another file or manual entry. Imported transactions arrive uncategorized. **Import history** (`/imports/`) shows past imports with Retry (failed) and Discard / Delete source file.

**Statements** (`/statements/`) show each account's running balance and a reconciliation of computed versus stated totals.

## 6. Budgeting

Open **Budgeting** (`/budgets/`; linked from Transactions as *Edit budgets and categories*):

1. Add **Income sources** (amount and cadence) and **Recurring expenses**.
2. Add **Categories** (name, income/expense, colour).
3. **Create period** (for example "October 2026"; making it active deactivates the old one).
4. **Add limit** per expense category. The warning % defaults to your profile threshold.

**Your budget plan** shows monthly income, recurring expenses, *Suggested toward goals* (remaining goal amounts ÷ 12), and *Left over*, with assumptions under *Assumptions behind this plan*. Invalid entries show a message explaining what to fix.

## 7. Savings goals, pools, and the savings plan

- **Financial Goals** (`/savings/goals/`): **Create a goal** with name, category, colour, target, current amount, optional target date, and whether it's an investable pool. Each card shows progress, the next milestone, the required weekly/monthly/yearly pace for dated goals, and a projected completion when there's enough recent activity.
- **Goal page** (`/savings/<id>/`): **Add a contribution** (Contribution / Withdrawal / Adjustment). Withdrawals can't exceed the balance. Milestones at 25/50/75/100% show a message and a notification record.
- **Pools** (`/savings/pools/`): includes the three automatic pools **Rainy Day**, **Investment**, and **Regular Savings**. They can be renamed or edited but not deleted.
- **Savings plan** (`/savings/plan/`): scenario, objective, explanation, safe-to-save, the split across the three pools, warnings, and per-goal notes. Actions: **Recalculate**, **Pause recommendations**, **Resume**, **Disable**, **Turn recommendations back on**, and editing the allocation % (**Save percentages**; must total 100). **Debts** (`/savings/debts/`) add balances and APRs so high-interest debt can be prioritized. *Recommendations only; nothing is transferred.*

## 8. Round-ups and investing (simulated)

Open **Investments** (`/investing/`).

**Round-up settings:** *Enable round-up investing (simulated)*, *Pause round-ups*, *Round purchases up to the nearest ($)*, optional cap, *Never sweep below this cash reserve ($)*, target pool. Click **Save settings**.

**Round-up ledger:** each purchase shows its round-up and status: **Pending** (calculated, not invested), **Swept (simulated)**, or **Reversed**. Example: a $4.35 purchase → **+$0.65 Pending**.

**Simulate a sweep now** moves pending round-ups that fit under your cap and reserve into the simulated portfolio, and tells you if nothing fits.

**Portfolio tab:** simulated portfolio value, contributions, and pending round-ups (three separate numbers); portfolio snapshot and orders; **Investable surplus** with *Propose (requires approval)*; pending orders with **Approve** / **Reject**; demo investing budget and *Add demo funds* (virtual only).

**Explore / My investments / market data / demo ideas** need the server's Twelve Data key. Without it you'll see *"Twelve Data history is not available."*

**Calculator:** enter a starting balance, monthly contribution, assumed annual return, and years for a hypothetical projection. It is not a prediction.

## 9. Insights

`/insights/`: this month versus last month, six-month income/spending bars, top categories, biggest increase and decrease, average monthly figures, savings rate, and recurring payments.

## 10. Settings

`/accounts/settings/`: **Profile** (edit display name inline), **Connected accounts** (placeholders, *not connected*), **Statement imports**, **Appearance** (theme), savings, investment, and notification preferences, **Messaging** (link a chat with a one-time code / unlink), **Notification history**, **Security & privacy**, **Log out**. The moon/sun button in the header switches light and dark mode and saves the choice to your account.

## 11. Messaging assistant

**Without Photon:** `python manage.py chat_demo --username demo`.

**With Photon Spectrum (team setup):** run the adapter in `spectrum/` (see `spectrum/README.md`), go to Settings → Messaging, generate a code, and text it from iMessage. The chat is now linked. *Live iMessage delivery was not verified while writing these docs.*

Try: `help` · `how's my budget` · `what is my emergency fund goal` · `I got paid $500` → `yes` · `set my Trip goal to $2000` → `yes` · `pause round-ups` · `resume round-ups` → `yes` · `how's my portfolio doing` · `propose investing $100` → `yes`/`no` · `withdraw $50` (always refused).

Anything that changes data asks *"Reply 'yes' to confirm or 'no' to cancel."* first.

## 12. Troubleshooting

| Problem | Cause / fix |
|---|---|
| "Sign-in isn't configured on this server." | No Auth0/Supabase variables set. Use option A, B, or C above |
| Stuck on "verify your email" | Auth0 hasn't reported the email verified yet. Use the link in Auth0's email, then **refresh** on the verify page (it re-checks Auth0) |
| Explore tab is empty | `TWELVE_DATA_API_KEY` is not set on the server |
| "Nothing swept: …" | Round-ups are disabled or paused, nothing fits under the cap, or the cash reserve leaves no headroom |
| Proposal smaller than expected, or "No investable surplus" | Pending and approved proposals already use the surplus |
| Can't delete Rainy Day / Investment / Regular Savings | Default pools are engine-managed; rename or withdraw instead |
| Import rows under "Needs review" | Unreadable values or identical rows within one file; enter those manually |
| Data disappeared on the deployed site | Without a Postgres `DATABASE_URL`, Vercel uses temporary storage that resets |

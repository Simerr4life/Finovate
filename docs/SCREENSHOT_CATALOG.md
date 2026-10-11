# Screenshot Catalog

All images in `docs/assets/screenshots/submission/` were captured on **2026-10-11** with Playwright/Chromium 141 from this codebase running locally (`runserver`, SQLite, `DEBUG` on). They are **not** mockups. The capture scripts were run from a scratch directory; the procedure is described under *Refreshing the captures*.

**Data:** the seeded `demo` user (`seed_demo` + `seed_peachtree_demo`, display name set to "Demo User") and a fresh account "New Judge" for onboarding. All financial figures are **sample data**. Investing figures are **simulated**. No Auth0/Supabase/Twelve Data/Photon credentials were configured, so provider-dependent screens show their real "not configured / not available" states.

**Viewports:** desktop 1440×900 (full-page where noted), mobile 390×844. Light theme unless stated. Captured with `prefers-reduced-motion: reduce`, so the count-up animation is off and every figure shows its final server-rendered value.

| File | Feature | Viewport | Scenario | Caption | Depicts |
|---|---|---|---|---|---|
| `01-landing.png` | Landing | Desktop, full page | Signed out | Finovate landing page with Log in / Get started | Live UI |
| `02-login-unconfigured.png` | Authentication | Desktop | No provider configured | Login page states that sign-in isn't configured; no local password form | Live UI (provider-missing state) |
| `03-onboarding-start.png` | Onboarding | Desktop, full page | New account | "Let's add some financial data": import, bank (coming soon), manual, skip | Live UI |
| `03b-onboarding-preferences.png` | Onboarding | Desktop, full page | New account | Preferences form completing onboarding | Live UI |
| `04-manual-setup.png` | Manual setup | Desktop, full page | Demo user | One-page income/expense estimate form | Live UI, sample data |
| `05-dashboard.png` | Dashboard | Desktop, full page | Demo user | Total cash, monthly income/spending, available to save, chart, savings opportunity, recent transactions | Live UI, sample data |
| `06-dashboard-review-modal.png` | Savings opportunity | Desktop | Modal open | Review proposed plan: surplus breakdown; saving creates a pending simulated order | Live UI, simulated |
| `07-transactions.png` | Transactions | Desktop | Demo user | Ledger with search, month, and category filters, CSV export | Live UI, sample data |
| `08-transaction-add.png` | Transactions | Desktop | Add form | Add a transaction | Live UI |
| `09-budgeting.png` | Budgeting | Desktop, full page | Demo user | Budget plan, income, recurring expenses, categories, periods, limits | Live UI, sample data |
| `10-statement-reconciliation.png` | Statements | Desktop, full page | Peachtree demo | Running balance and computed-vs-stated reconciliation (all match) | Live UI, fictional sample statement |
| `11-import-upload.png` | CSV import | Desktop | Upload step | Statement upload form | Live UI |
| `12-savings-overview.png` | Savings | Desktop, full page | Demo user | Savings overview with plan allocation and goals | Live UI, sample data |
| `13-savings-plan.png` | Savings plan | Desktop, full page | Demo user | Scenario, explanation, safe-to-save, pool split, controls, revisions | Live UI, sample data |
| `14-financial-goals.png` | Goals | Desktop, full page | Demo user | Goal cards with progress, milestones, pace | Live UI, sample data |
| `15-pools.png` | Pools | Desktop | Demo user | Default pools (Rainy Day, Investment, Regular Savings) and custom goals | Live UI, sample data |
| `16-investing-portfolio.png` | Investing | Desktop, full page | Demo user | Simulated portfolio value vs. contributions vs. pending round-ups; surplus; round-up settings; round-up ledger (Pending / Swept) | Live UI, **simulated** |
| `17-investing-explore-no-feed.png` | Market data | Desktop | No Twelve Data key | Explore tab showing "Twelve Data history is not available" | Live UI (provider-missing state) |
| `18-investing-calculator.png` | Calculator | Desktop | Defaults | Hypothetical projection inputs | Live UI, hypothetical |
| `19-insights.png` | Insights | Desktop, full page | Demo user | Month comparison, bars, categories, changes | Live UI, sample data |
| `20-settings.png` | Settings | Desktop, full page | Demo user | Profile, accounts, imports, appearance, preferences, messaging, notification history | Live UI, sample data |
| `21-goal-detail.png` | Goal detail | Desktop, full page | Demo user | Goal progress, milestones, contribution form, activity history | Live UI, sample data |
| `22-dashboard-dark.png` | Theme | Desktop | Dark mode | Dashboard in dark theme with sun toggle | Live UI, sample data |
| `23-mobile-dashboard.png` | Mobile | 390×844 | Demo user | Mobile dashboard with header and bottom navigation | Live UI, sample data |
| `24-mobile-savings-plan.png` | Mobile | 390×844 | Demo user | Savings plan on mobile | Live UI, sample data |
| `25-mobile-investing.png` | Mobile | 390×844 | Demo user | Investing page on mobile | Live UI, simulated |
| `26-mobile-menu.png` | Mobile navigation | 390×844 | Menu open | Expanded mobile menu | Live UI |

## Not captured (and why)

| Planned shot | Reason |
|---|---|
| Auth0 Universal Login and verification email | No tenant credentials; outbound network blocked |
| Messaging in iMessage | Photon adapter not run (no credentials). Use the `chat_demo` transcript in [TESTING_AND_VALIDATION.md](TESTING_AND_VALIDATION.md#t-msg-01) or record a live session |
| Explore with live prices / demo ideas | No Twelve Data key |
| Import preview with duplicates | Not captured in this pass; reproduce by importing the same CSV twice |
| Production site on `finovate.biz` | Deployment not reachable from this environment |

## Older captures

`docs/assets/screenshots/raw/`, `annotated/`, and `mobile/` hold an earlier set (see `docs/assets/screenshots/README.md`). Those predate this pass and the theme-toggle icon fix. Prefer the `submission/` set.

## Refreshing the captures

1. `python manage.py migrate && python manage.py seed_demo && python manage.py seed_peachtree_demo`
2. Start `runserver` on a free port and create a session for `demo` (for example via the local admin path in [USER_GUIDE.md](USER_GUIDE.md#option-c--local-walkthrough)).
3. Use Playwright (`chromium.launch`) with `viewport` 1440×900 / 390×844, set `reducedMotion: 'reduce'` (otherwise the count-up animation can be caught mid-way), and save to `docs/assets/screenshots/submission/` using the filenames above.

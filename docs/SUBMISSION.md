# Hacklanta 2026 Devpost Submission — Finovate

> **Deadline (official guide): hacking ends Sunday, October 11, 2026 at 9:00 AM EDT. All materials must be submitted on Devpost (https://hacklanta.devpost.com/) by then. No exceptions.** Then one team member submits the Google Form (Devpost link, project name, team members, track, challenges). See [HACKATHON_REQUIREMENTS.md](HACKATHON_REQUIREMENTS.md).

## Devpost checklist (from the official guide)

| Item | Ready? | Where |
|---|---|---|
| Project title and description | ✅ | Below |
| Problem and who it serves | ✅ | Write-up → Inspiration / Who it's for |
| Team roster (max 4) | ✅ Harold Aghedo (captain), Micheal White | — |
| Main track (one) | ✅ **Fintech** | — |
| Side challenges (max 3) | ✅ **MLH: Best Use of Auth0**, **Photon: Agents in iMessage**, **MLH: Best Domain Name from GoDaddy Registry** (our live domain `finovate.biz` is a GoDaddy Registry `.biz` domain) | — |
| Public GitHub repo with useful README | ✅ Public | https://github.com/Simerr4life/Finovate |
| Working demo link **or** clear run instructions | ✅ Both | https://finovate.biz · README → Run it locally |
| Demo video, 2–3 min, **public** | ❗ Record and upload | [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
| Technologies, APIs, datasets, sponsor tools | ✅ | "Built with" below |
| Disclosure of anything made before Hacklanta | ✅ | "Disclosure" below |
| Test credentials / special instructions for judges | ✅ | "Instructions for judges" below |
| Google Form (one member) | ❗ After Devpost | Discord announcement |

| Field | Value |
|---|---|
| **Project title** | Finovate |
| **Team** | Turn It Off and On Again |
| **Members** | Harold Aghedo (captain), Micheal White |
| **Live demo** | https://finovate.biz |
| **Main track** | Fintech |
| **Side challenges** | MLH: Best Use of Auth0 · Photon: Agents in iMessage · MLH: Best Domain Name from GoDaddy Registry |
| **Repository** | https://github.com/Simerr4life/Finovate |
| **Built with** | Python, Django, SQLite, PostgreSQL, Auth0 (auth0-server-python, Authlib), Photon Spectrum (spectrum-ts), Bun, TypeScript, Twelve Data API, Supabase, Vercel, HTML, CSS, JavaScript |

## Devpost write-up (paste into the description; covers ideation and development process)

**Finovate — make your money move, and always know why.**

### Inspiration (ideation)
Our team kept running into the same problem: budgets live in one app, savings goals in a spreadsheet, and investing in a brokerage that never talks to either, so nobody can say how much money is actually spare. Automated money tools make it worse by acting without explaining. For the Fintech track ("rethink how money moves"), we set three rules before writing code: every dollar has a purpose, every automated action is explainable, and the user stays in control.

### Who it's for
Students and early-career earners, often with irregular income, who want one honest view of cash, savings, and investing, and who want to learn investing without risking real money.

### What it does
- **Budgeting from real data:** enter transactions or import a bank CSV. Finovate detects columns, handles messy exports, skips duplicates, flags rows it can't read instead of guessing, and reconciles statements against their stated totals.
- **A savings plan that shows its work:** a rule-based engine reads income, bills, debts, and emergency savings, picks one of five scenarios, computes a *safe-to-save* amount after a safety buffer, and splits it across Rainy Day, Investment, and Regular Savings pools, with every assumption on screen.
- **Goals with a pace:** targets, deadlines, 25/50/75/100% milestones, the weekly/monthly pace needed, and projected completion.
- **Honest round-ups:** a $4.35 purchase creates a $0.65 *pending* round-up. A simulated sweep respects your cash reserve and cap.
- **Simulated investing with guardrails:** proposals wait for your approval, can't reuse the same surplus twice, and keep cash, invested principal, and market value as separate numbers.
- **An agent in iMessage (Photon Spectrum):** text "how's my budget" or "I got paid $500". Anything that changes data waits for "yes", and withdrawals are always refused.
- **Auth0 sign-in:** Universal Login, an email-verification gate, and access-token-protected API. Accounts map to Auth0's user ID, never just an email.

### How we built it (development process)
We started from a Figma Make layout and built a Django 6.1 / Python 3.13 server-rendered app, with Decimal arithmetic for every dollar. Each domain (budgets, savings, investing, imports, assistant) keeps its logic in service functions, so the website and the iMessage agent call the same code and can't disagree. We integrated Auth0 with the official `auth0-server-python` SDK (encrypted cookie sessions, Management API verification refresh, Post-Registration Action webhook, RS256 API token checks). For Photon, a Bun/TypeScript adapter built on Spectrum (`spectrum-ts`, iMessage provider) relays messages to a secret-protected Django bridge with duplicate protection, and a second endpoint verifies Spectrum's HMAC webhook signatures. Twelve Data provides optional live quotes behind a shared quota cache. On the last morning we ran a full audit: it found and fixed 27 bugs (including round-ups never being created for real transactions), added 48 regression tests, and brought the suite to **381 passing tests**.

### Challenges
Keeping numbers honest was harder than computing them. Making automation safe meant row locks so double-clicks can't approve an order twice, idempotent imports, and plans that stay paused when paused. Identity was subtle too: two accounts with the same email must never merge.

### Accomplishments
An explainable savings engine, a CSV importer that refuses to guess, an iMessage agent that cannot move money, and 381 automated tests.

### What we learned
In finance, trust comes from transparency and consent. Labeling something "pending" or "simulated" is a product decision, not a footnote.

### What's next
Read-only bank connections with explicit consent, notification delivery and weekly summaries, auto-categorization, and a brokerage partner behind the approval flow we already built.

### Disclosure (built before Hacklanta / not ours)
- The UI layout started from a **Figma Make** design export (in `.figma-make-inspect/`).
- Open-source libraries and SDKs: Django, auth0-server-python, Authlib, psycopg, python-dotenv, spectrum-ts. APIs and services: Auth0, Photon Spectrum, Twelve Data, Supabase, Vercel, Google Fonts.
- Datasets: a bundled September 2026 market-data sample (`demo_data/september_2026_verified_market_data.csv`, 109 rows, source noted as a FinanceCharts excerpt), plus fictional demo data and a fictional bank statement generated by our seed commands.
- AI coding assistants (Cursor, Claude Code) helped write and review code. The team designed, reviewed, and integrated everything during the event. All 49 commits are dated October 10–11, 2026.

### Instructions for judges
- **Live site:** https://finovate.biz (sign up with Auth0).
- **Run locally:** `pip install -r requirements.txt && python manage.py migrate && python manage.py seed_demo && python manage.py runserver`. Website sign-in uses Auth0. Without Auth0 credentials, see `docs/USER_GUIDE.md` (section 1, option C) for a local walkthrough with sample data.
- **Try the iMessage agent without Photon:** `python manage.py chat_demo --username demo`.
- **Simulated:** no bank or brokerage is connected and no money moves. Live prices need a `TWELVE_DATA_API_KEY`.
- **Tests:** `python manage.py test` (381 passing).

## Tagline (15 words · 104 characters)

Budgeting, savings goals, and simulated investing that explain every number and ask before every change.

## Short description (52 words · 358 characters)

Finovate is a Python personal-finance assistant that keeps cash, savings goals, round-ups, and investments as separate, labeled numbers. It builds a budget from your transactions or bank CSV, recommends a safe-to-save amount with its reasoning, tracks goals, and simulates round-up investing. Nothing changes without your approval, on the web or by iMessage.

## Medium description (177 words · 1,181 characters)

Most people manage budgets, savings goals, and investing in separate apps, so they guess how much money is actually spare, and automated tools rarely explain themselves.

Finovate is a Django web app plus an iMessage-compatible assistant built on one rule: every dollar has a purpose. Users sign in with Auth0, enter or import transactions (CSV import with duplicate detection and statement reconciliation), and set income, bills, and category limits. A rule-based savings engine picks one of five scenarios, from stabilization to strong capacity, computes a safe-to-save amount, and splits it across Rainy Day, Investment, and Regular Savings pools while showing every assumption. Goals track milestones, required pace, and projected completion.

A $4.35 purchase creates a $0.65 pending round-up; a simulated sweep respects the user's cash reserve and cap. Investment proposals stay pending until approved, and cash, invested principal, and market value are never merged. Through Photon Spectrum, the same backend answers texts like "how's my budget" and asks for a "yes" before recording income or changing a goal.

Investing is simulated: no bank, brokerage, or money movement.

## Extended description

<!-- extended-start -->
### Inspiration

Budgeting apps show where money went. Brokerages show what it's worth. Neither tells you how much you can safely set aside this month, or explains what an "automatic" feature just did. We wanted a financial assistant built on three promises: every dollar has a purpose, every automated action is explainable, and the user stays in control.

### What it does

- **Budgeting from real data.** Add transactions by hand or import a bank CSV. Finovate detects columns, handles messy exports (preamble rows, semicolons, European decimals, debit/credit columns), skips duplicates, and flags rows it can't read instead of guessing. Statements reconcile computed totals against what the bank claimed.
- **A savings plan that shows its work.** From income, bills, debts, and emergency savings, the engine chooses a scenario (stabilization, build reserve, debt focus, stable, or strong), computes a safe-to-save amount after a safety buffer, and splits it across Rainy Day, Investment, and Regular Savings pools. It never allocates more than is safe and explains each choice.
- **Goals with a pace.** Targets, deadlines, milestones at 25/50/75/100%, the weekly/monthly/yearly pace needed, and a projected completion date from recent progress.
- **Honest round-ups.** A $4.35 purchase creates a $0.65 pending round-up. A simulated sweep moves pending round-ups only within the user's cash reserve and cap.
- **Simulated investing with guardrails.** Proposals stay pending until approved, cannot reuse the same surplus twice, and keep cash, invested principal, and market value as separate numbers. Every page says "simulated."
- **The same brain over iMessage.** Through Photon Spectrum, users ask "how's my budget" or say "I got paid $500"; anything that changes data waits for "yes," and withdrawals are always refused.

### How we built it

Python 3.13 and Django 6.1 with server-rendered pages, and Decimal arithmetic for every dollar. Auth0 handles sign-up, login, email verification (refreshed through the Management API), and API access-token validation; accounts map to Auth0's user ID, never an email. A Bun/TypeScript adapter using Photon's spectrum-ts SDK relays iMessage to a secret-protected Django bridge, and a signed webhook endpoint verifies Spectrum HMAC signatures. Twelve Data provides optional live quotes behind a shared quota and cache. SQLite runs locally and PostgreSQL in production; the project is configured for Vercel. 381 automated tests cover the money math, identity rules, imports, chat confirmations, and cross-user isolation.

### Challenges we ran into

Keeping numbers honest was harder than computing them: a "spare cash" figure tempts you to merge cash, goal money, and investments, so we kept them separate everywhere. Making automation safe meant locking rows so double-clicks can't approve an order twice, making imports idempotent, and making sure a paused plan stays paused. Identity was subtle too: two accounts with the same email must never merge.

### Accomplishments that we're proud of

An explainable savings engine; a CSV importer that refuses to guess; a chat assistant that cannot move money; and a same-day audit that found and fixed 27 bugs, backed by 48 new regression tests.

### What we learned

Trust in a finance tool comes from transparency and consent more than from features. Labeling something "pending" or "simulated" is a product decision, not a footnote.

### What's next for Finovate

Read-only bank connections with explicit consent, notification delivery and weekly summaries, auto-categorization, and a brokerage partner behind the approval flow we already built.

**Try it:** https://finovate.biz · **Code:** https://github.com/Simerr4life/Finovate

**Disclaimer:** Finovate is a prototype and not financial advice. Investing features are simulated; no money moves.
<!-- extended-end -->

*Extended description: 566 words · 3,757 characters (Markdown included).*

## How it works (judge summary)

1. Sign in with Auth0 → onboarding (import a CSV, enter finances manually, or skip) → preferences.
2. Dashboard: total cash, this month's flow, safe-to-save, chart, savings opportunity.
3. Budgeting: income, bills, categories, limits → plan recalculates automatically.
4. Savings plan and goals: scenario, pool split, pace, milestones.
5. Investments: pending round-ups, simulated sweep, propose → approve.
6. Chat: the same actions by text, with confirmation.

Architecture: [TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md). Feature evidence: [FEATURE_REFERENCE.md](FEATURE_REFERENCE.md), [TESTING_AND_VALIDATION.md](TESTING_AND_VALIDATION.md).

## Side challenges

| Track | What we built | Evidence | Gap |
|---|---|---|---|
| **MLH: Best Use of Auth0** | Universal Login sign-up/login/logout via `auth0-server-python`; sub-based identity; email-verification gate with Management API refresh and resend; Post-User-Registration Action webhook; RS256 access-token validation for `/api/me/` | `accounts/` code; mocked tests pass | Record a live login against the tenant |
| **Photon: Agents in iMessage** | Spectrum adapter (`spectrum-ts`, iMessage provider) relaying to a secret-protected bridge; HMAC-verified webhook; confirmation-gated assistant; one-time-code chat linking; duplicate protection | `assistant/`, `spectrum/`; 43 tests; in-process transcript | Record a live iMessage exchange |
| **MLH: Best Domain Name from GoDaddy Registry** | **finovate.biz** (`.biz` is a GoDaddy Registry TLD) serves the live app. *Finovate* = finance + innovate | Live at https://finovate.biz; host configured in `finovate/settings.py` | — |

## Known limitations

No bank or brokerage connection; investing is simulated. Live market data needs a Twelve Data key. Notifications are recorded, not delivered. Live iMessage delivery was not verified during documentation. Full list: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Responsible AI and financial safety

- **Product:** the assistant is rule-based (regular expressions, no LLM), so its behavior is deterministic and testable. It cannot move money; every data change needs explicit confirmation. The savings engine and demo investment ideas are deterministic rules with visible inputs and "not financial advice" language.
- **Development:** the team used AI coding assistants (repository configuration for Cursor and Claude Code is present, and some commits are AI co-authored). The team reviewed and owns the submitted code. *Confirm the official AI-use policy and adjust this statement if disclosure wording is prescribed.*
- **Data:** no bank credentials, card numbers, or brokerage credentials are collected. Bank account numbers are never collected in full: only the last few digits (at most six) are stored.

---

### Counts

| Section | Words | Characters |
|---|---|---|
| Tagline | 15 | 104 |
| Short | 52 | 358 |
| Medium | 177 | 1,181 |
| Extended (between the markers, Markdown included) | 566 | 3,757 |

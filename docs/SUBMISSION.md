# Hacklanta 2026 Submission — Finovate

> The platform, fields, and character limits come from the official Hacker Guide, which could not be read while this was prepared ([HACKATHON_REQUIREMENTS.md](HACKATHON_REQUIREMENTS.md)). Descriptions are therefore provided at several lengths with exact counts. Trim to the official limits once known. Section headings in the extended description follow the common Devpost format; rename them if the platform differs.

| Field | Value |
|---|---|
| **Project title** | Finovate |
| **Team** | Turn It Off and On Again |
| **Members** | *To be filled in by the team.* Commit authors use the GitHub handles `Simerr4life` and `Bigmike0814` |
| **Main track** | Finance |
| **Side tracks** | Auth0 · Photon · GoDaddy (**claim only with evidence**, see [THIRD_PARTY_SERVICES.md §3](THIRD_PARTY_SERVICES.md#3-godaddy)) |
| **Repository** | `https://github.com/Simerr4life/Finovate` (remote verified; public visibility **not verified**) |
| **Live demo** | *Not verified.* Vercel project `finovate` exists; add the production URL after testing it |
| **Demo video** | *Not recorded yet* |
| **Built with** | Python, Django, SQLite/PostgreSQL, Auth0 (auth0-server-python, Authlib), Photon Spectrum (spectrum-ts, Bun, TypeScript), Twelve Data API, Supabase (optional), Vercel, HTML/CSS/JavaScript |

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

## Sponsor tracks

| Track | What we built | Evidence | Gap |
|---|---|---|---|
| **Auth0** | Universal Login sign-up/login/logout via `auth0-server-python`; sub-based identity; email-verification gate with Management API refresh and resend; Post-User-Registration Action webhook; RS256 access-token validation for `/api/me/` | `accounts/` code; mocked tests pass | Record a live login against the tenant |
| **Photon** | Spectrum adapter (`spectrum-ts`, iMessage provider) relaying to a secret-protected bridge; HMAC-verified webhook; confirmation-gated assistant; one-time-code chat linking; duplicate protection | `assistant/`, `spectrum/`; 43 tests; in-process transcript | Record a live iMessage exchange |
| **GoDaddy** | Only the `finovate.biz` domain configuration is in the code | None in the repo | Show registrar/DNS evidence or don't claim this track |

## Known limitations

No bank or brokerage connection; investing is simulated. Live market data needs a Twelve Data key. Notifications are recorded, not delivered. Live Auth0, Photon, and production deployment were not verified during documentation. Full list: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

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

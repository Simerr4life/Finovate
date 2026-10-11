# Judge Readiness

**Official format (Hacker Guide, *Judging*):** Judging Expo, Sunday October 11, 9:30–11:30 AM, State Ballroom. **3 minutes to pitch + 2 minutes of Q&A** at a table with two judges. Wait in line until staff call you to an open table, then exit after presenting.

## Official judging questions

The guide lists these as the questions judges ask themselves:

| Official question | What Finovate shows | Evidence | Weakness to manage | One-line answer |
|---|---|---|---|---|
| **Does the project address the track's prompt?** (Fintech: "rethink how money moves: payments, budgeting, investing, and the tools that make finances easier to manage") | Budgeting from real or imported data, an explainable safe-to-save engine, round-ups, simulated investing with approvals, money questions by iMessage | [FEATURE_REFERENCE.md](FEATURE_REFERENCE.md) | Investing is simulated; no payments rail | "Finovate rethinks how money moves by making every movement explained and approved: budget, save, round up, invest, by web or text." |
| **How polished is the prototype or demo?** | Consistent design system, light/dark, mobile layout, empty states, clear errors; 381 passing tests; 98-page crawl with no errors | Screenshots 01–26; [TESTING_AND_VALIDATION.md](TESTING_AND_VALIDATION.md) | Explore tab needs a Twelve Data key; sign-in needs Auth0 configured | "Every button does something real, or says clearly that it's simulated." |
| **How effective is the team's presentation?** | 3-minute script that is one continuous story, not a tour of screens | [DEMO_SCRIPT.md §2](DEMO_SCRIPT.md#2-recommended-3-minute-demo) | Live provider risk | Rehearse twice; keep the `chat_demo` fallback open |
| **Is there a clear, compelling use case?** | "How much can I safely save this month?" for students and irregular earners | Savings plan page | Two similar "available" labels | "It answers the question everyone has, and shows its math." |

### Side challenges

| Challenge | Strongest evidence | Gap | Pitch line |
|---|---|---|---|
| MLH: Best Use of Auth0 | Universal Login, sub-based identity, verification gate with Management API refresh, Post-Registration Action webhook, RS256 API audience validation | Not shown live in docs prep | "Auth0 isn't just a login button here: it gates verification and protects our API." |
| Photon: Agents in iMessage (must integrate Spectrum) | Bun adapter on `spectrum-ts` (iMessage provider) → secret-protected bridge; confirmation-gated agent; one-time-code linking; duplicate protection | Live iMessage not verified in docs prep | "Text your budget; the agent asks before it changes anything and can never move money." |
| MLH: Best Domain Name from GoDaddy Registry | `finovate.biz` (`.biz` = GoDaddy Registry) serves the live app; Finovate = finance + innovate | — | "finovate.biz: finance plus innovate, on a business domain." |

## Defensible differentiators

1. **Separated money categories everywhere:** cash, goal allocations, pending round-ups, invested principal, and market value (dashboard, investing, chat replies).
2. **Explainable, deterministic engine:** scenario choice, buffers, and splits are printed on the page; no black-box model.
3. **Consent by design:** pending-then-approve orders, chat confirmations, pause that stays paused, refused withdrawals.
4. **One backend, two interfaces:** chat and web call the same service functions and always agree.
5. **Data integrity:** idempotent imports, reconciliation against stated totals, and row locks on money actions.

## Problem → solution narrative

*People don't fail at saving because they lack apps; they fail because no app tells them what is safe to save, and automated tools act without explaining. Finovate turns income, bills, debts, and goals into one explained number — safe-to-save — and makes every automated step visible and approvable, on the web or by text.*

## Why the Fintech track

It addresses budgeting, emergency savings, debt prioritization, and investing literacy, the core of personal financial health. It handles financial data carefully (no credentials, last-few-digit account identifiers only) and is honest about simulation.

## Likely judge questions

| Question | Evidence-based answer |
|---|---|
| Is any of this real money? | No. Investing is simulated, and no bank or brokerage is connected. Budgeting uses data you enter or import. |
| Where does the data come from? | Manual entry, CSV statement import, or the chat ("I got paid $500"). The demo uses seeded sample data. |
| How do you calculate safe-to-save? | Monthly income − monthly expenses − a buffer (cash reserve ÷ 3 + 25% of essentials, 50% if income is irregular), floored at $0. |
| What if expenses exceed income? | Stabilization scenario: no savings allocation, plus a shortfall warning. |
| How is a round-up calculated? | Next multiple of your rounding amount minus the purchase: $4.35 → $0.65. It stays pending until a sweep, which respects your reserve and cap. |
| Could the chat drain my account? | No. There's no money-movement capability; withdrawals are refused; data changes need "yes." |
| How do you prevent duplicate imports? | Bank reference IDs, or a fingerprint of account, date, amount, kind, and description, unique per user; identical rows within a file are flagged for review. |
| How does Auth0 fit in? | It handles sign-up/login (no passwords stored), email verification, and access tokens for the API. Accounts map to Auth0's user ID, never an email. |
| What's Photon's role? | Photon Spectrum delivers iMessage; our adapter relays messages to Django with a shared secret, and webhooks are HMAC-verified. |
| What did you use for AI? | The assistant is rule-based (no LLM). The team used AI coding assistants during development. |
| What's next? | Read-only bank connections, notification delivery and weekly summaries, auto-categorization, and a brokerage partner behind the approval flow. |

## Risks that could undermine the presentation

| Risk | Mitigation |
|---|---|
| Can't sign in (Auth0 not configured, email not verified) | Pre-verified account; local fallback (USER_GUIDE option C) |
| Explore tab empty | Set `TWELVE_DATA_API_KEY` or skip Explore |
| iMessage fails live | `chat_demo` terminal fallback |
| Deployed data reset (SQLite on Vercel) | Set `DATABASE_URL` or demo locally |
| Claiming more than is built (real trades, GoDaddy beyond the domain) | Follow "What not to say" in [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
| Confusion between the two "available" figures | One sentence: "monthly flow vs. cash on hand" |

## Prioritized final checklist

1. **P0** Submit on Devpost **before 9:00 AM EDT**, then the Google Form (one member).
2. **P0** Team on Devpost: Harold Aghedo (captain), Micheal White.
3. **P0** Record and upload a **2–3 minute public** demo video (3-minute script).
4. ✅ Live at https://finovate.biz; repo public.
5. **P0** Select Fintech + 3 challenges: Auth0, Photon, GoDaddy Registry.
6. **P1** Set `TWELVE_DATA_API_KEY` and `DATABASE_URL` on the demo server; confirm `FINOVATE_SECRET_KEY`.
7. ✅ Docs and fixes merged to `main`.
8. ✅ Team names in README and SUBMISSION.
9. **P2** Add a LICENSE if required.

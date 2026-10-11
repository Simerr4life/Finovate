# Judge Readiness

> **The official judging criteria were not available** (the Hacker Guide was blocked; see [HACKATHON_REQUIREMENTS.md](HACKATHON_REQUIREMENTS.md)). The criteria below are **commonly used hackathon categories, assumed, not official**. Replace them with the guide's wording and weights before judging.

## Criteria map (assumed criteria)

| Criterion (assumed) | What judges look for | Finovate's strongest capability | Evidence | Current weakness | Recommended improvement | One-line pitch |
|---|---|---|---|---|---|---|
| Technical complexity | Non-trivial engineering that works | Scenario-based savings engine; idempotent CSV importer with a fallback reader; Auth0 with verification and API token validation; signed Photon webhook plus bridge; row locking for money actions | 381 passing tests; [FEATURE_REFERENCE.md](FEATURE_REFERENCE.md) | Provider integrations not shown live | Record live Auth0 and iMessage clips | "Eight Django apps and 381 tests: identity, imports, a planning engine, and a messaging bridge that share one backend." |
| Innovation / originality | A fresh angle | Explainability and consent as the product: separated money buckets, pending-first round-ups, approve-before-act, a chat that cannot move money | Dashboard, plan page, chat transcript | Round-ups and budgeting exist elsewhere | Lead with "every dollar has a purpose" and explainability | "Other apps show numbers or move money. Finovate explains the numbers and waits for your yes." |
| Impact / usefulness | A real problem for real people | Safe-to-save for irregular incomes; emergency-reserve-first logic; debt prioritization | Savings plan scenarios | No real bank data | Show the CSV import of real-format data | "It answers the question everyone has: how much can I safely save this month?" |
| Design / UX | Polished, coherent, accessible | Consistent design system, light/dark themes, mobile layout, empty states, clear errors | Screenshots 01–26 | Two similar "available" labels; onboarding button text alignment | Explain the two numbers in the demo | "Every screen tells you what's real, what's estimated, and what's simulated." |
| Completeness / functionality | Works end to end | Full flow: sign-in → onboarding → budget → plan → goals → round-ups → simulated invest → chat | Browser flows in [TESTING_AND_VALIDATION.md](TESTING_AND_VALIDATION.md) | Explore needs a Twelve Data key; sign-in needs Auth0 configured | Configure both on the demo server | "Every button you see does something real or says clearly that it's simulated." |
| Presentation | Clear story, good demo | Scripts at 60 s / 3 min / 5 min | [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Video not recorded | Record today | — |
| Finance track fit | Financial empowerment, responsible handling | Budgeting, savings, investing education, risk disclosures, no money movement | Investing disclaimers on every page | — | — | "A financial co-pilot that's honest about what it doesn't know." |
| Sponsor: Auth0 | Meaningful Auth0 use | Universal Login, sub-based identity, verification gate, Management API, Action webhook, API audience validation | [THIRD_PARTY_SERVICES.md §1](THIRD_PARTY_SERVICES.md#1-auth0) | Not shown live | Live login on video | "Auth0 isn't a login button here; it gates verification and protects the API too." |
| Sponsor: Photon | Meaningful Photon use | Spectrum iMessage adapter, HMAC-verified webhook, confirmation-gated assistant, one-time-code linking | [§2](THIRD_PARTY_SERVICES.md#2-photon-spectrum-imessage) | Not shown live | Live iMessage on video | "Text your budget; Finovate asks before it changes anything." |
| Sponsor: GoDaddy | Meaningful GoDaddy use | — | Only the domain string | **No evidence** | Show registrar/DNS proof or don't enter | — |

## Defensible differentiators

1. **Separated money categories everywhere:** cash, goal allocations, pending round-ups, invested principal, and market value (dashboard, investing, chat replies).
2. **Explainable, deterministic engine:** scenario choice, buffers, and splits are printed on the page; no black-box model.
3. **Consent by design:** pending-then-approve orders, chat confirmations, pause that stays paused, refused withdrawals.
4. **One backend, two interfaces:** chat and web call the same service functions and always agree.
5. **Data integrity:** idempotent imports, reconciliation against stated totals, and row locks on money actions.

## Problem → solution narrative

*People don't fail at saving because they lack apps; they fail because no app tells them what is safe to save, and automated tools act without explaining. Finovate turns income, bills, debts, and goals into one explained number — safe-to-save — and makes every automated step visible and approvable, on the web or by text.*

## Why Finance track

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
| Claiming more than is built (GoDaddy, real trades) | Follow "What not to say" in [DEMO_SCRIPT.md](DEMO_SCRIPT.md) |
| Confusion between the two "available" figures | One sentence: "monthly flow vs. cash on hand" |

## Prioritized final checklist

1. **P0** Read the official guide; confirm the deadline, video limit, and criteria; update this file and HACKATHON_REQUIREMENTS.md.
2. **P0** Confirm every member is registered/accepted.
3. **P0** Record and upload the demo video (3-minute script).
4. **P0** Verify the live URL and sign-in, or choose the local demo.
5. **P0** Decide sponsor tracks: Auth0 and Photon with live clips; GoDaddy only with proof.
6. **P1** Set `TWELVE_DATA_API_KEY` and `DATABASE_URL` on the demo server; confirm `FINOVATE_SECRET_KEY`.
7. **P1** Merge the audit and docs branch to the default branch so judges see the current code.
8. **P1** Fill in team member names in README and SUBMISSION.
9. **P2** Add a LICENSE if required.

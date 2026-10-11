# Known Limitations

**Reviewed:** 2026-10-11. Every item comes from code inspection or execution during documentation prep. Severity: **Critical** (blocks submission or demo) · **High** (judges will likely notice) · **Medium** · **Low**.

## Critical blockers (submission / demo)

| # | Component | Current behavior | Expected | Impact | Severity | Depends on | Recommended fix | Blocks |
|---|---|---|---|---|---|---|---|---|
| K1 | Hackathon rules | Official Hacker Guide not reviewed (network blocked) | Every rule checked | Unknown eligibility risks, wrong limits | Critical | Guide access | Paste or export the guide; update [HACKATHON_REQUIREMENTS.md](HACKATHON_REQUIREMENTS.md) | Submission |
| K2 | Demo video | Not recorded | Uploaded video link | Probably required | Critical | Team | Record using [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Submission |
| K3 | Judge access | Website sign-in needs Auth0 or Supabase credentials; with neither, login says "Sign-in isn't configured." There is no local password login by design | Judges can sign in | Judges may not get past the landing page | Critical | Configured deployment or credentials | Provide a working deployed URL with Auth0 enabled, plus a judge test account or open sign-up; or demo from a presenter laptop | Demo |
| K4 | Live deployment | Vercel project exists; URL, health, and env not verifiable here | A known-good URL | No live link to submit | Critical | Vercel access | Open the production URL, sign in, and run [DEMO_CHECKLIST.md](DEMO_CHECKLIST.md) | Submission (if required) |
| K5 | GoDaddy track | No code or infrastructure evidence of GoDaddy use (only the `finovate.biz` string) | Demonstrable GoDaddy product use | Sponsor claim unsupported | Critical *for that track* | Registrar/DNS access | Provide proof ([THIRD_PARTY_SERVICES.md §3](THIRD_PARTY_SERVICES.md#3-godaddy)) or drop the track | Track eligibility |

## High

| # | Component | Current behavior | Expected | Impact | Severity | Depends on | Recommended fix | Blocks |
|---|---|---|---|---|---|---|---|---|
| K6 | Photon live delivery | Assistant, webhook verification, and bridge work in-process; the Bun adapter was not run against Photon | Live iMessage round-trip | Photon track evidence is code + tests only | High | Photon project credentials, a Mac/iMessage line per Photon setup | Record one live exchange | Photon track evidence |
| K7 | Auth0 live login | Fully implemented, mocked tests pass; not run against the tenant here | Recorded live login | Auth0 track evidence is code + tests only | High | Tenant config | Record sign-up → verify → dashboard | Auth0 track evidence |
| K8 | Market data | Explore, My investments valuation, demo ideas, market-data page, and price-based scenario use **Twelve Data rows only**. The 109 bundled sample rows are loaded by migrations but **no page displays them** | Data visible in demo | Without `TWELVE_DATA_API_KEY` the Explore tab is an empty notice | High | API key (free tier) | Set the key on the demo server, or (code change) fall back to the bundled sample with clear labeling | Demo of Explore |
| K9 | Investing | Entirely simulated: "sweep" and "approve" update local rows only. Swept/approved snapshots set market value = contributions (no market drift) | Clearly labeled simulation (it is) | Fine if presented honestly | High (framing) | Brokerage partner | Keep the "simulated" language in every demo line | — |
| K10 | Two "available" numbers | Dashboard *Available to save* = monthly **safe-to-save** from the savings plan (flow). *Available to consider* / *Investable surplus* = cash on hand minus reserves (stock). Similar labels, different meanings | One clear explanation | Judges may ask why they differ | High | — | Explain in the demo (see [USER_GUIDE.md](USER_GUIDE.md#understanding-the-numbers)); later, rename labels | — |

## Medium

| # | Component | Current behavior | Expected | Severity | Recommended fix | Blocks |
|---|---|---|---|---|---|---|
| K11 | Notifications | Events are recorded in-app (`NotificationEvent`, shown in Settings → Notification history) but never delivered by email/SMS/push | Delivery channel | Medium | Wire a sender; Photon adapter could push | No |
| K12 | Budget warnings | No `BUDGET_WARNING` event is ever created; the "Notify me about budget warnings" setting only gates the round-up-paused notice. Warnings show only as progress-bar colors | Warning events when a limit's threshold is crossed | Medium | Emit an event on threshold crossing | No |
| K13 | Weekly reports / scheduled jobs | No scheduler, cron, or background worker. Plan recalculation runs on data change and page view | Weekly summary | Medium | Add a scheduled command | No |
| K14 | Bank connection | Onboarding shows "Connect a bank account — coming soon" (disabled); `BANK_PROVIDER_API_KEY` unused | Read-only bank feed | Medium | Plaid-style read-only provider | No |
| K15 | Categorization | Imported transactions are saved **uncategorized**; a CSV "Category" column is recognized but ignored. No automatic categorization or recurring-payment detection | Suggested categories, recurring detection | Medium | Map hints to user categories; detect repeats | No |
| K16 | Refund/reversal linking | `Transaction.reverses` exists and round-ups skip reversals, but nothing in the UI or importer sets it | Refunds linked to purchases | Medium | Expose in edit form/import | No |
| K17 | Round-up eligibility | Every new expense transaction is eligible; there is no posted/pending distinction and transfers are not distinguished from purchases | Only posted purchases | Medium | Add a status/type to transactions | No |
| K18 | Production secret key | If `FINOVATE_SECRET_KEY` is missing in production, settings fall back to a published development key | Fail closed | Medium (High if unset in prod) | Confirm it is set; optionally refuse to boot on Vercel without it | No |
| K19 | Vercel persistence | Without `DATABASE_URL`, Vercel uses `/tmp` SQLite, which resets on cold start | Persistent DB | Medium | Set a Postgres URL | Possibly the demo |
| K20 | Account lifecycle | No self-service account deletion or full data export (transactions CSV export exists); no password reset in-app (handled by Auth0/Supabase hosted flows) | Delete/export | Medium | Add a deletion flow | No |
| K21 | Goals | No pause/archive for goals; default pools (Rainy Day, Investment, Regular Savings) cannot be deleted (by design, since they're engine-managed) | Pause/archive | Medium | Add an archived flag | No |
| K22 | Import ambiguity | Identical rows inside one CSV (same date, amount, description) are flagged "needs review" and cannot be imported from that file | Let users confirm | Medium | Allow explicit confirmation with unique IDs | No |

## Low

| # | Item | Notes |
|---|---|---|
| K23 | Rate limiting | Per-process cache (`LocMemCache`); best-effort on serverless. Trusts `X-Forwarded-For` only on Vercel |
| K24 | Pagination | Transaction and ledger lists are unpaginated |
| K25 | Budget periods | No automatic monthly rollover |
| K26 | Onboarding buttons | Button labels on `/accounts/onboarding/` sit near the top of each button (cosmetic) |
| K27 | Duplicate calculator script | `static/js/finovate.js` contains an older projection handler; the inline script on the Calculator tab produces the correct result |
| K28 | Dependencies | `auth0-server-python` is a beta release; `authlib.jose` emits a deprecation warning |
| K29 | No LICENSE file | Clarify reuse terms if the rules require open source |
| K30 | Chat understanding | Regex intents only; unusual phrasings fall back to "Reply help" |

## Fixed during this documentation pass

| Item | Change |
|---|---|
| Theme toggle rendered as a blank button | Added the missing `moon`/`sun` icons to `templates/partials/icon.html` (template-only, no behavior change) |

Fixes from the preceding code audit (round-ups never created for real transactions, duplicate-category crash, plan dead ends, and more) are summarized in [TESTING_AND_VALIDATION.md](TESTING_AND_VALIDATION.md#audit-regressions).

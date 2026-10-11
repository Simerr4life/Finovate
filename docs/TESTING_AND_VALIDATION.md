# Testing and Validation

**Run date:** 2026-10-11 · **Environment:** Linux cloud container, Python 3.13.16, Django 6.1.2, SQLite, Chromium 141 (Playwright 1.56) · **Branch:** `claude/codebase-audit-fixes`

Nothing here was run against production, and no real financial transaction was attempted. Results are copied from actual runs. Tests that could not run are marked **Blocked** with the reason.

## 1. Automated suite

```bash
python manage.py test
```

**Result:** `Ran 381 tests in 97.053s — OK` (0 failures, 0 errors).

| Module | Tests | Focus |
|---|---|---|
| `investing/tests.py` + `investing/test_audit_fixes.py` | 71 + 9 | Round-up math, idempotency and creation from transactions, sweeps (reserve, cap), surplus, orders, Twelve Data quota/cache, demo ideas |
| `accounts/tests.py` | 61 | Auth0 login/callback/logout (mocked), sub-based identity, Supabase sign-in (mocked), API token validation, manual setup, open-redirect guards, rate limits |
| `assistant/tests.py` | 43 | Intents, confirmations, linking codes, Spectrum signature verification, bridge auth and dedupe |
| `imports/tests.py` + `imports/test_csv_enhanced.py` | 41 + 16 | CSV validation, column detection, debit/credit/net agreement, duplicates, enhanced reader (preambles, `;`, European decimals, DR/CR) |
| `accounts/test_verification_backup.py` | 19 | Email verification monotonicity, Management API refresh, backup webhook |
| `savings/*` (4 files) | 48 | Plan scenarios, safe-to-save cap, pools, milestones, locking, plan status |
| `budgets/*` (2 files) | 24 | Progress, plan recalculation, validation, isolation |
| `core/*` (2 files) | 17 | Round-up helper, Decimal quantizing, empty states, charts, insights |
| `accounts/test_profile_name_theme.py` | 13 | Display name and theme persistence |
| `accounts/test_audit_fixes.py` | 9 | Webhook secret, IP for rate limits, timestamp parsing, settings validation |
| `transactions/tests.py` | 10 | Idempotent import, running balances, reconciliation |

Other checks: `python manage.py check` → no issues. `python manage.py makemigrations --check` → no changes. `ruff` (pyflakes/bugbear rules) → one stylistic warning in a test file.

## 2. Validation cases

| ID | Objective | Preconditions | Steps | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|---|---|
| T-BUILD-01 | App boots and schema builds | Fresh SQLite | `migrate`, `seed_demo`, `seed_peachtree_demo`, `runserver` | Server returns 200 on `/` | 200; the Peachtree seed printed a fully reconciled statement (opening $1,245.80 + deposits $3,133.50 − withdrawals $1,567.16 = $2,812.14, all matching) | Pass | Command output |
| T-CRAWL-01 | No broken pages | Demo user, seeded | Logged-in crawl following every internal link plus 24 explicit URLs (incl. `?range=bogus`) | No 4xx/5xx | 98 pages visited, 0 errors | Pass | Crawl script output |
| T-UI-01 | No console errors, no horizontal scroll | Demo user | Playwright: 23 pages at 1280×900 and 390×844 | 0 console/page errors, 0 failed requests, no overflow | 0 errors at both sizes (after fixing a 29 px overflow on `/statements/` in the audit) | Pass | Browser script output |
| T-UI-02 | Review modal and mobile menu open | Demo user | Click *Review investment plan*; tap the mobile menu | Both open; Escape closes | Opened/closed as expected | Pass | Browser script |
| T-UI-03 | Theme toggle visible | Any page | Inspect header | Moon/sun icon | Was blank (missing icons); fixed; now renders ([dark screenshot](assets/screenshots/submission/22-dashboard-dark.png)) | Pass after fix | Screenshot |
| T-AUTH-01 | Login without providers fails safely | No Auth0/Supabase env | Open `/accounts/login/` | No password form; explanatory message | "Sign-in isn't configured on this server." | Pass | [02-login-unconfigured.png](assets/screenshots/submission/02-login-unconfigured.png) |
| T-AUTH-02 | Live Auth0 sign-up, verification, login, logout | Tenant credentials | Universal Login round-trip | Profile created by `sub`; verify gate; dashboard | Not run | **Blocked** — no credentials, outbound network blocked | Mocked tests in `accounts/tests.py` pass |
| T-AUTH-03 | Account recovery | Auth0/Supabase hosted | Use the provider's reset flow | Handled by the provider | Not run; Finovate has no in-app reset by design | **Blocked** | — |
| T-API-01 | `/api/me/` rejects missing tokens | — | `GET /api/me/` with no header | 401, no data | `401 {"error": "authentication_failed"}` | Pass | Shell output |
| T-API-02 | Cross-user isolation | Two users | Automated tests request another user's objects | 404 / no data | Pass (e.g. `test_goal_query_returns_only_that_users_goal`, `test_other_user_cannot_see_or_affect_this_users_manual_estimate`, `test_access_token_returns_only_that_users_records`) | Pass | Test suite |
| T-BUD-01 | Budget progress math | Budget with spend | Unit tests | spent/limit, warning ≥ threshold and < 100%, over ≥ 100% | Pass | Pass | `budgets/tests.py` |
| T-BUD-02 | Invalid budget input reported | Logged in | Post negative income; duplicate category; period ending before start | Error message, nothing saved, no crash | Messages shown; duplicate category previously crashed with a 500 (fixed) | Pass | `budgets/test_audit_fixes.py`, browser flow 1 |
| T-SAV-01 | Plan never allocates more than safe-to-save | Income/expenses | Unit test | Sum of allocations ≤ safe-to-save | Pass | Pass | `test_never_allocates_more_than_safe_to_save` |
| T-SAV-02 | Over-withdrawal blocked | Goal with $300 | Withdraw $999,999 in the browser | Inline error | "You can withdraw at most $300.00 from this goal." | Pass | Browser flow 4 |
| T-SAV-03 | Disabled plan can be re-enabled | Active plan | Disable → *Turn recommendations back on* | Status Active | "Status: Active" | Pass | Browser flow 5 |
| T-TX-01 | Import deduplication | CSV imported twice | Unit tests | Second import skips duplicates; identical rows within a file flagged | Pass | Pass | `imports/tests.py` |
| T-RU-01 | $4.35 → $0.65 | — | `round_up_to_nearest(4.35, 1.00)` | 0.65 | 0.65 | Pass | `core/tests.py::test_example_from_spec` |
| T-RU-02 | Manual expense creates a pending round-up | Round-ups enabled | Add a $7.25 expense in the browser | Pending $0.75 entry on Investing | Entry listed as Pending | Pass | Browser flow 2 |
| T-RU-03 | Sweep respects reserve and cap | Pending entries | Unit tests | Nothing swept below the reserve; cap honored | Pass | Pass | `investing/tests.py::SweepTests` |
| T-PREC-01 | Decimal precision | — | `quantize_money(1.005)` | 1.01 (half-up) | 1.01 | Pass | `core/tests.py` |
| T-INV-01 | Order cannot be approved twice | Pending order | Approve with a stale copy | Second approval refused; contributions counted once | Pass | Pass | `investing/test_audit_fixes.py` |
| T-INV-02 | Surplus cannot be proposed twice | $500 surplus | Propose $500 twice | One order; remaining surplus $0 | Pass | Pass | `investing/test_audit_fixes.py` |
| T-INV-03 | Projection calculator math | Calculator tab | Start $1,000, $100/month, 6%, 10 → 20 years | $18,179 → $49,411 | $18,179 and $49,411 | Pass | Browser script; matches the compound formula |
| T-INV-04 | Live quotes and Explore | Twelve Data key | Open Explore | Price history cards | "Twelve Data history is not available…" | **Blocked** — no API key | [17-investing-explore-no-feed.png](assets/screenshots/submission/17-investing-explore-no-feed.png) |
| <a id="t-msg-01"></a>T-MSG-01 | Assistant conversation | Demo user | Send messages via `handle_incoming_message` | Correct replies; confirmation before changes | See transcript below | Pass | Shell output |
| T-MSG-02 | Bridge dedupe | DEBUG, no bridge secret | POST the same `message_id` twice to `/assistant/bridge/` | First reply, then `duplicate: true` | `{"ok": true, "duplicate": false, "reply": "This chat isn't linked to a Finovate account yet."}` then `{"ok": true, "duplicate": true, "reply": ""}` | Pass | Shell output |
| T-MSG-03 | Webhook fails closed when unconfigured | No webhook secret | POST with a signature header | 503 | `503 {"error": "webhook secret is not configured"}` | Pass | Shell output |
| T-MSG-04 | Live iMessage round-trip | Photon credentials, Bun | `bun start` in `spectrum/` | Reply delivered over iMessage | Not run | **Blocked** — credentials and network | Signature/bridge tests pass |
| T-NOTIF-01 | Notifications recorded | Contribution crosses a milestone | Automated + browser | Event in Settings history | Recorded; **not delivered** externally by design | Pass (record only) | `savings/tests.py` |
| T-CFG-01 | Missing provider configuration | No keys | Open login, Explore, webhook | Clear messages, no crashes | As above (T-AUTH-01, T-INV-04, T-MSG-03) | Pass | — |
| T-DEPLOY-01 | Production deployment health | Vercel access | Open the production URL | 200 and sign-in works | Not run | **Blocked** — Vercel API 403; DNS blocked | — |

### T-MSG-01 transcript (demo user, sample data)

```text
> hows my budget
Budget status for October 2026:
- Groceries: $76.45/$400.00 (on track)
- Dining out: $49.85/$150.00 (on track)
- Transport: $40.00/$120.00 (on track)
> I got paid $500
Record $500 as income today? This will add a transaction.
(Reply "yes" to confirm or "no" to cancel.)
> yes
Recorded $500 income for today.
> pause round-ups
Done — round-ups are paused. Say "resume round-ups" any time to turn them back on.
> how is my portfolio doing
Simulated investment performance (not real brokerage data):
- General bucket as of 2026-10-11: contributed $2.71, value $2.71, gain/loss $0.00
> propose investing $100
Create a simulated pending proposal to invest $100? Estimated investable surplus not already proposed is $2290.35. This does not place a brokerage order or move money. ...
> no
Okay, cancelled. Nothing changed.
> withdraw $50 to my bank
Withdrawals to a bank account are not available. No transfer provider is connected, so nothing was requested, pending, or completed.
```

## 3. <a id="audit-regressions"></a>Audit regressions (same day, before documentation)

A code audit fixed 27 confirmed defects and added 48 regression tests (28 of them fail on the pre-fix code). Highlights: round-ups were never created for user transactions; duplicate category names caused a 500 error; a disabled savings plan could not be re-enabled; default pools could be "deleted" and silently recreated empty; orders could be approved twice; the same surplus could be proposed repeatedly; Auth0 backup timestamps crashed on Django 5; rate limits could be bypassed with a spoofed `X-Forwarded-For` header. The full list is in commit `9f7c157`.

## 4. Verification limitations

- No live calls to Auth0, Supabase, Photon, Twelve Data, Vercel, or GoDaddy (the network policy blocked them, and no credentials were present).
- Browser testing used a forced session for the seeded `demo` user, because website login needs a configured provider.
- Mobile testing used Chromium device emulation (390×844), not physical devices or Safari.
- No load, accessibility-audit, or penetration testing was performed.

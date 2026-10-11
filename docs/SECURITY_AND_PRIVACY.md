# Security and Privacy

**Reviewed:** 2026-10-11 by code inspection, automated tests, and local execution. This is **not** a penetration test or a compliance assessment. Finovate makes **no claim** of compliance with PCI DSS, SOC 2, GLBA, GDPR, or any other standard.

## Summary

Finovate handles personal finance data (transactions, balances, goals) but **cannot move money**: no bank, payment, or brokerage credentials exist anywhere in the system, and every investing action is a local simulated record. The main risks are therefore account takeover, cross-user data exposure, and leaking stored financial history. The design handles these well for a prototype. The remaining gaps are mostly deployment hardening.

## Verified controls

| Area | Control | Evidence |
|---|---|---|
| Identity | Auth0 Universal Login: Finovate never sees or stores Auth0 passwords. Optional Supabase sign-in: passwords go to Supabase over TLS and are not stored | `accounts/auth0.py`, `accounts/supabase_auth.py`; `test_signup_redirects_to_auth0_and_creates_no_user` |
| Identity mapping | Profiles keyed by immutable provider IDs (`auth0_sub`, `supabase_uid`), **never merged by email** | `test_two_different_auth0_accounts_sharing_an_email_are_not_merged`, `test_supabase_login_never_merges_into_an_auth0_account_with_the_same_email` |
| Email verification | Unverified Auth0 users are confined to the verify page. Status comes only from fresh ID-token claims or the Management API, never from URL parameters, and it never downgrades | `test_client_cannot_force_verified_via_query_state`, `test_stale_unverified_claim_does_not_downgrade_confirmed_status` |
| Sessions | 8-hour Django session; cookies HTTP-only, `SameSite=Lax`, `Secure` on HTTPS. Auth0 state in encrypted cookies. Access token refreshed before expiry, otherwise logout | `finovate/settings.py`, `accounts/middleware.py`; `test_expired_session_is_logged_out_before_the_dashboard` |
| CSRF / clickjacking | Django CSRF middleware on all forms; `X-Frame-Options` middleware; logout is POST-only | `settings.MIDDLEWARE` |
| Open redirects | `safe_next()` rejects absolute, protocol-relative, and backslash URLs (used by login, callback, theme, and investing redirects) | `test_off_site_targets_are_rejected`, `investing/test_audit_fixes.py` |
| Authorization | Every user-data query is scoped to `request.user`; object lookups use `get_object_or_404(…, user=request.user)` | Isolation tests in budgets, savings, assistant, accounts |
| API | `/api/me/` accepts only RS256 access tokens for the configured audience (issuer, audience, expiry checked); ID tokens rejected; unverified users get 403 without data | `accounts/tokens.py`; `test_id_token_audience_is_rejected` |
| Webhooks | Spectrum HMAC-SHA256 signatures with a 5-minute replay window; bridge and Auth0 Action secrets compared in constant time; endpoints return 503 when unconfigured outside DEBUG | `assistant/spectrum.py`, `assistant/views.py`, `accounts/views.py` |
| Chat safety | Any state-changing chat intent requires an explicit "yes". Withdrawals are refused. Chats link only through a hashed, single-use, 15-minute code, and a phone number is never the identity key | `assistant/services.py`, `assistant/linking.py`; 43 tests |
| Rate limiting | Login 20 / 10 min, signup 10 / 10 min, verification resend 3 / 15 min, Auth0 Action 120 / min, per client IP | `accounts/views.py::_rate_limited` |
| Input validation | Positive amounts, category/kind agreement, date ordering, percentage and APR bounds, upload size (2 MB) and content checks; CSV rows are re-parsed from stored bytes, never trusted from the client | Forms, `imports/pipeline.py`, audit tests |
| Data integrity | `Decimal` money; unique constraints for imports, round-ups, and pools; row locks on goal contributions, order approval, and sweeps | Models, `investing/services.py`, `savings/services.py` |
| Logging | Structured logs record events and error codes, not amounts or account numbers | `settings.LOGGING` comment; log statements in services |
| Secrets | Read from environment variables; `.env`/`.env.local` git-ignored; the browser never receives management or service keys | `.gitignore`, `.env.example` |

## Findings

| ID | Severity | Finding | Impact | Recommendation |
|---|---|---|---|---|
| S1 | **High** if unset | If `FINOVATE_SECRET_KEY` is missing in production, Django falls back to a published development key | Session and CSRF tokens could be forged | Confirm it is set in Vercel; consider refusing to start on Vercel without it |
| S2 | Medium | No `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, or Content-Security-Policy | Weaker transport and XSS defense in depth | Enable HSTS/redirect on the HTTPS domain; add a CSP (fonts come from Google) |
| S3 | Medium | Rate limits and token caches use a per-process memory cache | On serverless, limits are per instance (best-effort) | Use a shared cache (Redis or the database) |
| S4 | Medium | Raw uploaded statement files are stored in the database (`ImportBatch.raw_file`, ≤ 2 MB) until the user deletes the source file | Retained bank-statement data | Default auto-deletion after commit; document retention |
| S5 | Medium | No self-service account deletion or full data export | Privacy expectations unmet | Add a deletion flow (cascade deletes exist at the model level) |
| S6 | Low | Chat message bodies are stored (`ConversationMessage`) for both directions | Financial details in chat history | Retention limit; disclose in privacy text |
| S7 | Low | Phone numbers are stored unverified unless Auth0 reports them verified (labeled as such) | Contact data accuracy | — |
| S8 | Low | The webhook/bridge accept unauthenticated calls **only when DEBUG is on and no secret is set** (local development) | Local-only exposure | Keep DEBUG off in production (default on Vercel) |
| S9 | Low | Google Fonts loaded from Google's CDN | Third-party request reveals visitor IP to Google | Self-host fonts if needed |
| S10 | Low | Beta auth SDK and a deprecated JWT module | Future breaking changes | Track upgrades |

### Fixed during the 2026-10-11 audit

Constant-time comparison of the Auth0 Action secret; `X-Forwarded-For` trusted only behind Vercel (it previously allowed rate-limit bypass); `safe_next` applied to the investment-proposal redirect (which previously allowed a `/\host` bypass); an Auth0 backup timestamp crash; race conditions on order approval, sweeps, and contributions.

## Financial authorization model

| Permission | Exists? | Notes |
|---|---|---|
| Read bank data | **No** | No aggregator connected; data comes from user entry or user-uploaded CSV |
| Move money / ACH | **No** | No transfer provider; chat refuses withdrawals |
| Place trades | **No** | `SimulatedOrder` is a local record; approval only updates simulated snapshots |
| Change in-app plans | Yes, user-initiated | Website forms; chat changes require "yes" |

A future real integration should keep **read-only data access** and **money-moving authority** as separate grants, with explicit per-action consent and limits (the current pending-then-approve order flow is the intended pattern).

## Audit trail

`Contribution` history per goal, `SavingsPlanRevision` snapshots, `NotificationEvent` log, `ConversationMessage` (chat), `ImportBatch` (counts, warnings, timestamps), `RoundUpLedgerEntry` states, `SimulatedOrder` states, `Auth0UserBackup` sync status.

## Secure deployment checklist

1. Set `FINOVATE_SECRET_KEY` (long, random) and keep `FINOVATE_DEBUG=false`.
2. Set `APP_BASE_URL` to the HTTPS origin; match the Auth0 callback, logout, and web-origin URLs.
3. Set `DATABASE_URL` to a managed Postgres with TLS.
4. Set `IMESSAGE_WEBHOOK_SECRET` and `ASSISTANT_BRIDGE_SECRET` before exposing messaging endpoints.
5. Keep `AUTH0_MGMT_CLIENT_SECRET`, `SUPABASE_SECRET_KEY`, and `TWELVE_DATA_API_KEY` server-side only.
6. Never commit `.env` or `.env.local`; rotate any key that was ever shared.

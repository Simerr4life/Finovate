# Integrations

**Last reviewed:** 2026-10-11

| Integration | Purpose | Config | Failure behavior |
|---|---|---|---|
| Auth0 | Primary identity | `AUTH0_*`, `APP_BASE_URL` | Signup/login unavailable if incomplete |
| Supabase Auth | Email/password | `SUPABASE_URL`, keys | Forms hidden if unconfigured |
| Supabase/Postgres | Hosted DB | `DATABASE_URL` / `SUPABASE_DB_URL` | Falls back to SQLite |
| Twelve Data | Live quotes/history | `TWELVE_DATA_API_KEY` | Sample data / unavailable messaging; credit windows |
| Photon Spectrum | Inbound messaging | `IMESSAGE_*`, webhook secrets | Invalid signature rejected; no Django outbound |
| Bank provider | Future | `BANK_PROVIDER_API_KEY` | Unused |
| Brokerage | Future | `BROKERAGE_PROVIDER_API_KEY` | Unused |
| Email | Django console backend | — | Prints to console in dev |

See also: [integration-readiness.md](../integration-readiness.md), [messaging-assistant.md](../messaging-assistant.md).

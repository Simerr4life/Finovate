# API reference

**Last reviewed:** 2026-10-11

Finovate is primarily form-posted HTML. JSON endpoints:

## `GET /api/me/`

- **Auth:** `Authorization: Bearer <Auth0 access token>` with audience `AUTH0_AUDIENCE`
- **Success:** `{ "identity_status", "email_verified", "transaction_count" }`
- **Errors:** 401 invalid/missing token; 403 when appropriate

## `POST /assistant/photon-webhook/`

- **Auth:** Spectrum HMAC signature or legacy webhook secret
- **Body:** Photon webhook payload
- **Response:** JSON including `reply`, `delivered: false` (Django does not send iMessage)
- **Idempotency:** `SpectrumDelivery` unique `(webhook_id, message_id)`

## `GET /investing/live-quotes/`

- **Auth:** Django session login
- **Response:** JSON quotes for user’s filled demo holdings

## `GET /investing/market-data/live-quotes/`

- **Auth:** Django session login
- **Response:** JSON shared market stock quotes

## Form POST endpoints

All feature mutations (transactions, budgets, goals, investing actions, imports) are session-authenticated form posts with CSRF, returning redirects/HTML — not a public REST surface.

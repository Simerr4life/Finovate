# Security

**Last reviewed:** 2026-10-11

## Controls (verified)

| Control | Implementation |
|---|---|
| AuthN | Auth0 OIDC / Supabase Auth |
| AuthZ | Login required + user-scoped ORM filters |
| CSRF | Django middleware on form posts |
| Sessions | Django sessions; Auth0 SDK cookies when used |
| Rate limits | Cache IP limits on signup/login/resend |
| Webhook auth | Spectrum HMAC / shared secret |
| API tokens | Auth0 JWT via JWKS (`accounts/tokens.py`) |
| Secrets | Env vars only; `.env.example` empty placeholders |
| Money integrity | Decimal quantization |

## Validation

Django forms for user input; import pipeline validates CSV structure/size.

## Known gaps / hardening

- CDN fonts without SRI (noted in README)
- No CSS/JS build pipeline / minification
- Notification channel not secured because not delivered
- Bank/brokerage keys are placeholders — must not be treated as live integrations

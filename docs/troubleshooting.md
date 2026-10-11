# Troubleshooting

**Last reviewed:** 2026-10-11

| Symptom | Likely cause | Resolution |
|---|---|---|
| Login/signup does nothing useful | Auth0/Supabase not configured | Set env vars; restart server |
| Stuck on verify page | Auth0 email unverified | Resend email; confirm in Auth0; refresh |
| Callback error | `APP_BASE_URL` mismatch | Align Auth0 callback with `<APP_BASE_URL>/callback` |
| Empty dashboard after seed | Viewing wrong user / not logged in | Use configured IdP account; seed is fixture |
| Import rejected | >2MB or unreadable CSV | Shrink/fix file; use manual setup |
| Twelve Data warnings | Missing/exhausted API key | Set key or rely on sample market data |
| Investing “orders” not in brokerage | Expected | Simulated only |
| Webhook 401/403 | Bad signature/secret | Check `IMESSAGE_WEBHOOK_SECRET` / Photon secret |
| Vercel data loss | Ephemeral `/tmp` SQLite | Configure Postgres URL |
| Tests fail on missing migrations | Models changed | `python manage.py makemigrations` / migrate in CI |

# Deployment

**Last reviewed:** 2026-10-11

## Vercel

- `vercel.json` sets Django framework + `finovate/wsgi.py` `maxDuration: 60`
- WSGI boot may migrate + seed demo when configured
- Prefer Postgres (`DATABASE_URL`) for persistence
- Set `FINOVATE_DEBUG=false`, strong `FINOVATE_SECRET_KEY`, Auth0, `APP_BASE_URL=https://your-domain`

## Checklist

1. Configure IdP callback URLs
2. Set CSRF trusted origins / allowed hosts (Vercel branch in settings helps `*.vercel.app`)
3. Configure webhook URL for Spectrum if used
4. Do not expose management/service-role keys to the browser
5. Confirm Twelve Data key only on server

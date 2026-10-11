# Architecture

**Last reviewed:** 2026-10-11

## Request flow

```mermaid
flowchart TD
  Req[HTTP request] --> MW[Django middleware + Auth0SessionMiddleware]
  MW --> URL[URLConf]
  URL --> View[Thin view]
  View --> Svc[services.py / plan_engine / pipeline]
  Svc --> ORM[Django ORM]
  ORM --> DB[(SQLite/Postgres)]
  View --> Tpl[Template + context processors]
  Tpl --> Res[HTML response]
```

## Design invariants

1. **Decimal money only** — `core.services`
2. **Business logic in services** — reusable by web + assistant
3. **Per-user ownership** on every query
4. **Simulated vs real labeled** in investing UI
5. **IdP owns passwords** — Finovate stores subjects/uids

## Deployment architecture

```mermaid
flowchart LR
  User --> Vercel
  Vercel --> WSGI[finovate/wsgi.py]
  WSGI --> Migrate[migrate on boot]
  WSGI --> App[Django]
  App --> PG[(Postgres optional)]
  App --> Auth0
  App --> Twelve[Twelve Data]
  Spectrum[Spectrum sidecar] -. webhook .-> App
```

On Vercel: `VERCEL` enables hosts/SSL/tmp SQLite unless Postgres URL set; optional `seed_demo` when `DEMO_ACCOUNT_PASSWORD` set and no demo user.

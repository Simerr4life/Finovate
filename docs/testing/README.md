# Testing

**Last reviewed:** 2026-10-11

## Strategy

Django `TestCase` / client tests per app. Run:

```bash
python manage.py test
```

Hundreds of `test_*` methods cover auth, imports, budgets, savings plan engine, investing, assistant, isolation.

## Regression priorities

1. Per-user isolation
2. Decimal round-up example $4.35 → $0.65
3. Idempotent imports
4. Budget progress live recompute
5. Savings plan scenarios + allocation caps
6. Webhook signature + confirmation gating
7. Simulated order approve/reject

## UI verification for docs

Playwright captures against local `runserver` with force-login session cookie for the `demo` fixture (documentation only — not a production login path).

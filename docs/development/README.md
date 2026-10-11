# Development

**Last reviewed:** 2026-10-11

## Layout

See root README architecture table. Put domain logic in `services.py` (or `plan_engine.py` / `pipeline.py`), keep views thin.

## Commands

```bash
python manage.py runserver
python manage.py test
python manage.py test savings.investing  # example subset
python manage.py chat_demo
python manage.py seed_demo
```

## Contribution notes

- Never use floats for money
- Filter by `request.user` on every user data path
- Label simulated investing clearly
- Do not commit secrets
- Prefer extending tests beside features

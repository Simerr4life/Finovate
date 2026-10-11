# Finovate product demo video

Presentation-ready walkthrough of Finovate for stakeholders, users, and investors.

## Deliverable

| File | Description |
|---|---|
| `export/finovate_product_demo.mp4` | Final 1920×1080 demo video |
| `source/cards/` | Branded intro / section / closing stills |
| `source/raw/` | Raw screen recordings used in the edit |
| `project/` | Editable build scripts (cards + compose) |

## Rebuild

```bash
# App must be running with seeded demo data:
python manage.py migrate
python manage.py seed_demo --reset
python manage.py seed_peachtree_demo
python manage.py runserver

python docs/assets/demo-video/project/make_cards.py
python docs/assets/demo-video/project/compose_demo.py
```

## Structure

1. Introduction — product name, logo, problem
2. First impressions — landing + dashboard
3. Core walkthrough — transactions, budgets, savings goals
4. Differentiators — savings plan + simulated investing
5. Complete journey — insights + mobile layout
6. Closing — value reinforcement

Investing sequences are clearly labeled as simulated. No unsupported claims.

## Final export details

- **File:** `export/finovate_product_demo.mp4`
- **Resolution:** 1920×1080 @ 30 fps
- **Duration:** ~2 minutes
- **Audio:** original ambient bed (generated, royalty-free) mixed under captions
- **Captions:** burned-in chapter captions (`project/finovate_product_demo.srt`)
- **Source recordings:** `source/raw/` plus `/opt/cursor/artifacts/finovate_demo_segment*.mp4`

Honest product boundaries are visible in-app during the investing and savings-plan sections (simulated investing; recommendations only).

Mobile viewport demos live under `docs/assets/screenshots/mobile/`; the video focuses on live desktop walkthrough plus simulated investing disclaimers.

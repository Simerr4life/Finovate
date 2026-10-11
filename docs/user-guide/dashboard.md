# Dashboard (Overview)

![Annotated dashboard](assets/screenshots/annotated/dashboard-overview-annotated.png)

## Purpose

Home view of recorded cash, monthly income/spending, potential savings, recent transactions, budget progress snippets, and a savings-opportunity panel.

## Location

`/dashboard/` — requires login; typically after onboarding.

## Controls

| Control | Action |
|---|---|
| Chart range 1W/1M/3M/6M/1Y | Changes cash chart window |
| View all (transactions) | Goes to transaction list |
| Review savings plan | Opens savings plan / related CTA |
| Notification bell | UI affordance (events recorded in settings) |
| Log out | Ends session (+ Auth0 logout when applicable) |

## Data shown

- **Total cash** — income minus expenses (all time, recorded)
- **Monthly income / spending** — current month aggregates
- **Potential savings / investable surplus** — estimate after reserves, goals, bills buffer
- **Simulated portfolio** — kept separate from cash figure (disclaimer in UI)

## Failure / empty states

- Empty accounts show zeroed metrics and prompts to add data or import
- Manual-estimate banner may appear when onboarding used manual setup

## Acceptance checks

1. With seeded demo data, cash cards render non-zero values
2. Chart range buttons change the visible series without full logout
3. Footer disclaimer remains visible

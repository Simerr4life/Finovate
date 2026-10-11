# Personalized savings plan engine

Finovate builds a **recommendation-only** savings plan from the user’s
recorded income, expenses, debts, emergency balance, and goals. It never
moves money, never places trades, and never treats credit as savings.

## Default pools

On first visit to Savings / Pools / Plan, three system pools are created
if missing (balances are never reset or duplicated):

| Pool | `Goal.system_key` | Role |
|---|---|---|
| Rainy Day | `rainy_day` | Emergency reserve |
| Investment | `investment` | Long-term investing (investable) |
| Regular Savings | `regular` | Short/medium-term goals |

## Analysis

`savings/plan_engine.py::analyze_finances` normalizes active
`IncomeSource` / `RecurringExpense` rows to monthly figures, excludes
non-earned income transfers from take-home estimates, classifies expenses
as essential vs discretionary by name keywords, and computes:

```
Monthly Surplus = Income − Expenses
Safe-to-Save = max(0, Surplus − additional buffer)
```

The additional buffer covers a checking reserve slice and irregular-bill
padding. Debt minimums from `DebtObligation` are included only when they
are not already represented as debt-named recurring expenses.

Emergency targets: starter floor/cap ($500–$1,000, tied to essentials),
then ~3 months of essentials (6 if income cadence is irregular).

## Scenarios

Chosen automatically (never asked of the user):

| Scenario | When |
|---|---|
| Stabilization | Expenses ≥ income / negative surplus |
| Build reserve | Emergency balance below starter target |
| Debt focus | Starter reserve met + high-interest debt (APR ≥ 10%) |
| Stable | Adequate reserve, manageable debt |
| Strong | Full reserve, solid surplus, no debt |

Stable/strong use the 20/30/50 Rainy/Investment/Regular fallback only when
that scenario fits — never for underfunded emergency or cash-flow stress.

## Persistence

- `SavingsPlan` — latest recommendation (OneToOne per user)
- `SavingsPlanRevision` — prior snapshots when the plan materially changes
- Fingerprint + dollar/percent thresholds avoid rewrite noise

Users can pause, disable, or edit allocation percentages (must total 100%
of the amount allocated from safe-to-save).

## UI

- `/savings/` — summary + explanation
- `/savings/plan/` — full plan, warnings, goal feasibility, history
- `/savings/debts/` — optional APR/balance inputs

## Tests

`python manage.py test savings` covers pool idempotency, each scenario,
unrealistic goals, allocation caps, and plan pages.

# Savings, pools, goals, and plan

![Savings index](assets/screenshots/raw/savings-index.png)

## Goals and pools

- **Financial Goals** `/savings/goals/` — deadline-based goals with pace suggestions
- **Pools** `/savings/pools/` — investable / system pools
- Goal detail supports contributions/withdrawals/adjustments

Milestones at 25/50/75/100% create `NotificationEvent` records (not externally delivered).

![Goals list](assets/screenshots/raw/savings-goals.png)

## Personalized savings plan

![Savings plan annotated](assets/screenshots/annotated/savings-plan-annotated.png)

Recommendation-only engine (`savings/plan_engine.py`):

```
Monthly Surplus = Income − Expenses
Safe-to-Save = max(0, Surplus − additional buffer)
```

Scenarios auto-selected: stabilization, build_reserve, debt_focus, stable, strong.

Default system pools (created if missing): Rainy Day, Investment, Regular Savings.

UI:

- `/savings/plan/` full explanation, warnings, history
- Refresh / pause / disable / edit allocation percents (must total 100% of allocated safe-to-save)
- `/savings/debts/` optional APR/balance inputs for debt_focus

Never transfers money or places trades.

Details: [savings-plan-engine.md](../savings-plan-engine.md).

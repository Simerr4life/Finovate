# Budgets

![Budgets index](assets/screenshots/raw/budgets-index.png)

## Purpose

Plan monthly income and recurring expenses, set category limits for a budget period, and see live progress.

## Location

`/budgets/` (also surfaced via Insights nav mapping in places)

## Workflows

### Create period and limits

1. Add a budget period (start/end, active flag)
2. Add category limits for that period
3. Progress computes **live** from expense transactions in-range (never stored spent totals)

### Income and recurring expenses

- Add/delete income sources and recurring expenses with cadence
- Cadence → monthly factor: weekly 4.33, biweekly 2.17, monthly 1, irregular 1

### Formulas (verified)

```
spent = sum(expenses in period for category)
remaining = limit - spent
percent_used = floor((spent / limit) * 100)   # int conversion as implemented
is_warning = percent_used >= warning_threshold and percent_used < 100
is_over = percent_used >= 100
```

Budget plan (`build_budget_plan`):

```
monthly_income = Σ monthly_equivalent(income)
monthly_recurring = Σ monthly_equivalent(expenses)
suggested_monthly_savings = heuristic from remaining goals / 12 (see services)
leftover_after_plan = income - recurring - suggested_savings
```

## Permissions

Login required; all objects scoped to the user.

## Acceptance

- Changing transactions updates progress without editing the Budget row
- Warning/over flags match threshold

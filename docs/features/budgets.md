# Budgets

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Set limits and see live spending progress.
- **Intended users:** Signed-in users
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Categories + active BudgetPeriod
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

![Budgets](assets/screenshots/raw/budgets-index.png)

## 3. Step-by-step workflow

Create period → add limits → spend via transactions → progress updates. Delete limit/period via confirm.

## 4. Business logic

See user-guide/budgets.md formulas; warning thresholds per budget or profile default.

## 5. Technical implementation

`budgets/services.py`, models BudgetPeriod/Budget/IncomeSource/RecurringExpense.

## 6. Errors and edge cases

Overlapping unique (period, category). Zero limit → percent_used 0.

## 7. Testing and acceptance criteria

Progress/plan tests in `budgets/tests.py`.

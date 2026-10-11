# Savings plan engine

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Recommend how to allocate safe-to-save across pools/debt.
- **Intended users:** Signed-in users with income/expense context
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Income sources, expenses, optional debts, emergency balances
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

![Plan](assets/screenshots/raw/savings-plan.png)

## 3. Step-by-step workflow

Open `/savings/plan/` → review scenario → optional refresh/status/allocations → edit debts as needed.

## 4. Business logic

Scenario table and safe-to-save math in `docs/savings-plan-engine.md` (verified against `plan_engine.py`).

## 5. Technical implementation

`savings/plan_engine.py`, `SavingsPlan`, `SavingsPlanRevision`, `DebtObligation`.

## 6. Errors and edge cases

No income → stabilization. Unrealistic goals flagged. Fingerprint skips noisy rewrites.

## 7. Testing and acceptance criteria

`savings/test_plan_engine.py`.

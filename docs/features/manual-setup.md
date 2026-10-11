# Manual setup

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Bootstrap estimates when CSV/bank unavailable.
- **Intended users:** Users in onboarding
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Onboarding path
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

![Manual setup](assets/screenshots/raw/manual-setup.png)

## 3. Step-by-step workflow

Enter savings balance / monthly goal style fields → summary via `build_budget_plan` → continue preferences.

## 4. Business logic

`accounts/manual_setup.py` applies profile fields; does not invent transactions.

## 5. Technical implementation

`accounts/views.py` manual_setup*, Profile manual_* fields.

## 6. Errors and edge cases

Invalid numbers → form errors.

## 7. Testing and acceptance criteria

Accounts tests for manual setup.

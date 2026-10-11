# Transactions

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Record and manage income/expense rows powering budgets and insights.
- **Intended users:** Signed-in users
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Optional categories; optional statement accounts
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

List with search; add/edit forms; delete confirm; CSV export. ![Transactions](assets/screenshots/raw/transactions-list.png)

## 3. Step-by-step workflow

Add → validate → save → redirect list. Edit/delete similar. Export downloads CSV of user’s rows.

## 4. Business logic

Positive `amount` + `kind`; `quantize_money`; idempotent import via `external_id`.

## 5. Technical implementation

`budgets/views.py` (UI), `transactions/models.py`, `transactions/services.py`, forms in budgets.

## 6. Errors and edge cases

Invalid amount/date → form errors. Cross-user pk → 404. Duplicate external_id → no double count.

## 7. Testing and acceptance criteria

CRUD isolation tests in `budgets/tests.py` / `transactions/tests.py`.

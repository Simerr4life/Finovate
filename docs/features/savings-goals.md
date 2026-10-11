# Savings goals and pools

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Track targets, contributions, and investable pools.
- **Intended users:** Signed-in users
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** None beyond login
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

![Goals](assets/screenshots/raw/savings-goals.png)

## 3. Step-by-step workflow

Add goal → contribute → milestones fire events → edit/delete. Pools page filters investable/system goals.

## 4. Business logic

`progress_percent`, `remaining_amount`; pace estimates; withdrawal cannot go negative.

## 5. Technical implementation

`savings/services.py`, `Goal`, `Contribution`.

## 6. Errors and edge cases

Over-withdraw blocked. Overdue goals prompt new date.

## 7. Testing and acceptance criteria

`savings/tests.py`.

# Dashboard

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Summarize recorded finances and surface next actions.
- **Intended users:** Signed-in users who finished (or skipped into) the app
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Transactions/budgets/goals data improve usefulness; works empty
- **Related:** See [feature inventory](../feature-inventory.md)

![Dashboard](assets/screenshots/raw/dashboard-overview.png)

## 2. User interface walkthrough

Overview cards, cash chart ranges, recent txns, savings opportunity, insights snippets. ![Dashboard](assets/screenshots/annotated/dashboard-overview-annotated.png)

## 3. Step-by-step workflow

1. Land on `/dashboard/` after login.
2. Review cards and chart.
3. Jump to transactions, savings plan, or investing as needed.
4. If operation fails (session expired) → redirect to login.

## 4. Business logic

Aggregations over user’s transactions; surplus estimate subtracts bills buffer, goal allocations, reserve. Simulated portfolio kept separate.

## 5. Technical implementation

Frontend: `templates/core/dashboard.html`, `static/js/finovate.js`. Backend: `core/views.py`. Data: Transaction, Budget, Goal, PortfolioSnapshot, Profile.

## 6. Errors and edge cases

Expired session → login redirect. Empty data → zeros/empty lists. No bank connected badge always when integration absent.

## 7. Testing and acceptance criteria

Seed demo → open dashboard → non-zero cash; chart controls respond; disclaimer visible.

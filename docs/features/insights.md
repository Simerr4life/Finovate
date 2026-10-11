# Insights

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Visualize spending patterns and savings rate style metrics.
- **Intended users:** Signed-in users
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Transaction history
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

![Insights](assets/screenshots/raw/insights-overview.png)

## 3. Step-by-step workflow

Open `/insights/` → review MoM and category visuals.

## 4. Business logic

Aggregations in `core/views.py` / display helpers.

## 5. Technical implementation

`templates/core/insights.html`, `core/display.py`.

## 6. Errors and edge cases

Empty history → empty/zero charts.

## 7. Testing and acceptance criteria

Covered partly by `core/tests.py` empty states.

# Market data explorer

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Browse sample/live prices and place budget-limited simulated buys.
- **Intended users:** Signed-in users
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Seeded MarketPrice rows; optional Twelve Data
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

![Market data](assets/screenshots/raw/investing-market-data.png)

## 3. Step-by-step workflow

Open Explore → inspect chart → invest amount within demo budget → order simulated.

## 4. Business logic

Uses verified OHLCV sample and/or Twelve Data; charts via `market-charts.js`.

## 5. Technical implementation

`investing/views.py`, `MarketPrice`, `LiveMarketQuote`.

## 6. Errors and edge cases

Insufficient demo budget → rejected. Stale quotes possible when credits exhausted.

## 7. Testing and acceptance criteria

Market explorer tests in `investing/tests.py`.

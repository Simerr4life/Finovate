# Simulated investing

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Educate with round-ups, surplus proposals, and demo orders — without real trades.
- **Intended users:** Signed-in users
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Optional Twelve Data key for live quotes
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

![Investing](assets/screenshots/annotated/investing-index-annotated.png)

## 3. Step-by-step workflow

Enable round-ups → spend → sweep → propose surplus → approve/reject orders → explore market demo buys.

## 4. Business logic

`round_up_to_nearest`; sweep caps/reserves; demo AI ranking rules; portfolio snapshots.

## 5. Technical implementation

`investing/services.py`, `live_quotes.py`, models RoundUp*, SimulatedOrder, DemoInvestment*.

## 6. Errors and edge cases

Paused round-ups skip sweep. Missing API key → sample/history messaging. Always simulated.

## 7. Testing and acceptance criteria

`investing/tests.py` (large suite).

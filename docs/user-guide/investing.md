# Simulated investing

![Investing annotated](assets/screenshots/annotated/investing-index-annotated.png)

## Critical disclaimer

**No brokerage is connected. No real orders are placed.** UI labels this throughout.

## Features

| Feature | Path / action | Behavior |
|---|---|---|
| Portfolio tab | `/investing/` | Snapshots, pending round-ups, surplus propose |
| Round-ups | settings + sweep | Expense → pending ledger → simulated sweep |
| Demo budget | add virtual funds | Caps demo AI / explore buys |
| Demo AI ideas | generate/accept/decline | Rule-based; prefers Twelve Data history |
| Explore | `/investing/market-data/` | Sample/live quotes; simulated buys |
| Historical demo | `/investing/historical-demo/` | Hypothetical scenarios on verified prices |
| Order approve/reject | POST endpoints | Fills or rejects `SimulatedOrder` |

## Round-up math (verified)

```
round_up = round_up_to_nearest(expense_amount, round_to)
# Example: 4.35 with round_to 1.00 → 0.65
```

Sweep respects pause flag, contribution cap, and minimum cash reserve.

## Live quotes

- Polling JS: `static/js/live-holdings.js`, `live-market-quotes.js` (~5 min)
- Requires `TWELVE_DATA_API_KEY`; otherwise UI explains history/quotes unavailable

## Errors

- Propose without surplus / over budget → validation/message
- Twelve Data credit exhaustion → usage window blocks; cached quotes may remain

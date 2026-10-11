# Round-up sweep workflow

1. Enable round-ups in Investing settings; set round_to, cap, reserve, target pool
2. Record expense transaction → pending `RoundUpLedgerEntry` (when rules match)
3. User clicks **Simulate a sweep now** or equivalent service path
4. System checks pause, reserve, cap
5. On success: entries marked swept; `PortfolioSnapshot` / simulated contribution updated
6. Failure: pause/cap/reserve → no sweep; user sees messaging

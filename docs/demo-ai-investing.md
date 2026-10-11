# Demo investing and market data

Explore, recommendations, the verified historical calculator, holdings
history, and simulated order reference prices use provider data stored in
`MarketPrice` rows marked as Twelve Data. Runtime queries do not fall back
to the bundled Excel-derived sample rows. Older sample rows may remain in
existing databases, but they are not shown or used by these features.

The current supported stock list is AAPL, AMZN, GOOGL, MSFT, and NVDA. Daily
OHLCV history is fetched from Twelve Data's
[`/time_series`](https://twelvedata.com/docs/market-data/time-series)
endpoint (up to 90 daily bars per symbol) and shared across users for 12
hours. Current prices come from Twelve Data's `/price` endpoint and are
shared for five minutes. Explore checks for stale history when opened and
polls current quotes every five minutes while open. Refreshes share a server
quota counter configured for eight credits per minute and 800 credits per
UTC day; each history or quote symbol consumes a credit.

The three bundled index tickers do not have verified mappings in the current
Twelve Data stock catalog, so Explore omits them rather than showing the old
sample values or substituting a different instrument. Add symbols to
`MARKET_STOCKS` only after verifying their Twelve Data identity and account
access.

Set `TWELVE_DATA_API_KEY` in the server environment (for Vercel, add it under
the project's Environment Variables and redeploy). The key remains
server-side. Twelve Data may restrict display, redistribution, or commercial
use depending on the subscription and intended audience. Verify that the
account's current terms permit showing this data to your users before
enabling the feature in a public deployment.

Recommendations rank supported stocks with at least two daily provider bars
by historical return minus observed daily volatility. The verified
calculator only offers Twelve Data rows. Simulated orders use the latest
available cached Twelve Data quote when possible, otherwise the latest
provider daily close; fractional shares are calculated from that reference
price. No recommendation or order is investment advice or a real trade.

Cash in investable savings pools, estimated cash surplus, and user-entered
virtual funds can contribute to the demo budget. Orders remain simulated,
must be separately approved, and do not connect to a brokerage or move real
money. The `seed_excel_demo_market` command and bundled CSV remain only as
legacy/demo fixtures; running them does not make their rows eligible for
the provider-backed investing features.

# Sample-data investing recommendations

Finovate's demo investing ideas and Explore page use the September 2026 CSV
supplied with the project owner's Excel demo package. Applying the database
migrations loads those 109 sample rows automatically. To load or refresh them
manually later, run:

```bash
python manage.py seed_excel_demo_market
```

The command is safe to run again and uses the CSV committed at
`demo_data/september_2026_verified_market_data.csv`. It does not contact a
market-data provider. The source notes travel with each imported sample row.
The Explore page groups those rows by stock and index, shows the supplied
price history as either a table or an interactive graph. The graph marks
sample-to-sample rises in green and drops in red, and its slider/hover
selection reveals the date and close. Users can also create a pending
simulated buy order with an amount and optional savings-pool attribution.
The available demo budget is rechecked before an order is created.
Cash already held in a savings pool marked investable, along with estimated
cash surplus and virtual demo funds, contributes to the simulated investing
budget. Demo orders reserve their amounts against that combined budget.
Virtual demo funds only increase the simulated investing budget; they do not
change cash balances or move real money.

The "Demo AI" is transparent, deterministic ranking logic, not a language
model, machine-learning prediction, or investment advice. It ranks symbols
with at least two supplied stock-price rows by sample-period percentage
change minus the standard deviation of the supplied daily percentage-change
values. It offers up to three ideas, with their amounts sharing no more than
$75 and never exceeding the user's remaining demo investing budget (estimated
cash surplus plus cash in investable savings pools and virtual demo funds,
less pending or already-filled simulated orders). Only rows marked as coming
from this bundled dataset are used; other market-data rows are excluded. It
reviews all available sample stocks and shows the three highest-ranked ideas
when data and budget are available.

Every idea needs a user decision. Accepting creates a pending simulated order
with fractional shares calculated from the sample close and its date. The
user must separately approve that order before it appears in the simulated
portfolio. Declining creates no order. No brokerage API is called, no real
order is submitted, and no money moves. These historical sample prices are
not live prices and do not predict future performance.

# Bank statement import

A user can upload a bank statement — during onboarding, or later from the
Statements page — and have it turned into real `Transaction` rows, with a
review step before anything is saved. Lives entirely in the `imports` app;
every other app (`transactions`, `budgets`, `savings`, `investing`) is
unchanged and unaware this feature exists, because imported transactions
are ordinary `Transaction` rows with `source="imported"`.

## Supported formats (tested)

- **CSV** — the only format implemented. Column mapping is fully
  automatic by header name (date, posting date, description/memo, amount,
  net amount, debit, credit, balance, reference/ID, currency) -- **there
  is no column-mapping screen**. Either a single signed amount column, a
  separate net-amount column, or separate debit/credit columns is
  accepted, including the `Money_In_USD`/`Money_Out_USD`/`Amount_USD`/
  `Net_Amount_USD`/`Running_Balance_USD` naming style. Extra columns like
  `Category`, `Transaction_Type`, `Recurring`, `Payment_Method`, `Month`,
  `Is_Income` are recognized as optional metadata and simply ignored --
  never required, never guessed at.

### Classic vs enhanced CSV readers

The **classic** reader in `imports/pipeline.py` is unchanged and still
handles the simple first-row-header, comma-separated exports above.

An **enhanced** reader in `imports/csv_enhanced.py` runs only when classic
cannot read the file reliably (or when a DR/CR `Type` column would be
misread as unsigned amounts). It does **not** replace the classic format:
it normalizes messier exports into the same shape classic already
understands, then reuses classic column detection and row parsing.

Enhanced additions (additive):

- Skip preamble rows (account metadata above the real header)
- Semicolon / tab / pipe delimiters
- European decimals (`4,35` / `1.234,56`) and `dd.mm.yyyy` dates
- `Amount` + `Type` (DR/CR) → signed amounts
- Join `Description` + `Memo` into one description

When enhanced is used, `ImportBatch.column_mapping` stores a reserved
`_reader` metadata object beside the role→header map so preview/commit
can rematerialize from the original upload bytes. Classic imports have
no `_reader` key.

**When more than one amount-like column is present** (e.g. both
`Amount_USD` and `Net_Amount_USD`, or debit/credit alongside a signed
amount), they are never added together. Each is treated as a candidate
signed value for that row; if they all agree, that value is used; if they
disagree, the row is flagged "needs review" and excluded from that
import rather than guessing which one is authoritative.

**If the file can't be read reliably** -- unsupported format, no
recognizable date/description/amount columns, or a header match with no
usable rows underneath -- the user never reaches a wizard at all. They
land on `imports/unreadable.html` ("We couldn't read this bank
statement.") with two actions: upload another file, or go straight to
the manual income/expense setup (see below). The same page handles a
genuinely corrupt/empty/binary upload too.

**Not implemented:** OFX/QFX, QIF, PDF (text or scanned/OCR). The upload
form only accepts `.csv`-shaped content; anything else is rejected with a
friendly error, not silently mis-parsed. Don't claim these formats work —
they don't yet. Extending to one of them means adding a new parser module
behind the same `ImportBatch` pipeline, not a schema change.

**Currency:** Finovate assumes every transaction is in USD — there's no
currency field on `Account` or `Transaction`. If a mapped currency column
says anything other than `USD`, that row is flagged for manual review
instead of being imported assuming the number is directly comparable.

## Pipeline (`imports/pipeline.py`)

Pure functions, no DB writes except the one read-only duplicate lookup,
mirroring `transactions/services.py`:

1. `validate_file` — content-based (decodes as text, sniffs as CSV,
   checks size/shape), not filename-based. A renamed non-CSV file fails
   here regardless of its extension.
2. `prepare_statement` — classic-first preparation. Uses
   `read_headers` / `detect_columns` / `parse_rows` / `assess_readability`
   on the raw text; if that is not readable (or a DR/CR type column is
   present), tries `csv_enhanced.prepare` and re-runs classic detection
   on the normalized CSV.
3. `parse_rows` — typed, Decimal-only parsing, including `_resolve_amount`'s
   candidate-reconciliation logic (see above) for files with more than
   one amount-like column. A single bad row is recorded in that row's
   `errors` and flagged for review; it never raises and never blocks the
   rest of the file. Reserved mapping keys starting with `_` are ignored.
4. `assess_readability` — enough of a recognizable shape to import from
   at all? If not, the user goes straight to the unreadable-file page
   instead of into a wizard for a file that was never going to work.
5. `detect_duplicates` — see below.
6. `summarize` — counts for the review screen.

## Data model

One new table: `imports.ImportBatch` (user, account, source_format,
original_filename, size-capped `raw_file` bytes, status, column_mapping
JSON, row counts, validation_summary JSON, error_message, committed_at).
No changes to `Account` or `Transaction` — both already had everything
needed (statement period/balance fields, `external_id` uniqueness,
`source` field, `reconcile_account()`).

**File storage:** raw bytes live in a `BinaryField` on `ImportBatch`,
capped at 2 MB, access-controlled the same way as every other per-user
row in this app (`user=` filtering). This app deploys to Vercel
(serverless, no durable local disk) with SQLite or Postgres as the only
configured datastores — no S3/Supabase Storage bucket — so the database
row *is* the private storage. Deleting a committed batch's source file
(Settings → import history → "Delete source file") clears `raw_file` but
keeps the audit row and the already-imported transactions, which are
independent records once committed.

## Duplicate detection

1. A CSV row with a mapped reference/ID column gets `external_id =
   f"csv:{value}"` and is matched exactly against existing transactions
   on the chosen account.
2. Otherwise, a fingerprint of `account + date + amount + kind +
   normalized description` (sha256, truncated) is used as `external_id`.
3. **Ambiguity rule:** if two or more *new* rows in the same upload share
   a fingerprint (e.g. two identical $20 coffee charges the same day),
   none of them are auto-deduped — they're flagged "needs review" and
   excluded from that import, because there's no way to safely tell which
   are genuinely new. The user can still enter them manually, or fix the
   source file.

This, plus `Transaction`'s existing DB-level unique constraint on
`(user, source, external_id)`, is what makes re-importing the same
statement (or an overlapping one) safe: re-running an identical import
produces 0 imported / N duplicates-skipped, never doubled totals.

## What's never done automatically

- Existing transactions are never deleted because they're absent from a
  newly imported statement (statements can cover different periods).
- A historical statement never overwrites `Account.opening_balance` or
  any balance a live connection would report — there is no live bank
  connection in this app, so this only matters if one is added later.
- No trades, transfers, or money movement happen as a side effect of
  importing — investing/round-up logic is untouched and still requires
  its own explicit flows.

## User-facing flow

Onboarding's first step (`accounts:onboarding` →
`templates/accounts/onboarding_start.html`) offers four things: **Import
a statement**, **Connect a bank account** (visibly disabled — no real
integration exists), **Enter finances manually**, or **Skip for now**
(goes straight to the existing preferences form, at
`accounts:onboarding_preferences`).

The import wizard is now just three steps: `/imports/upload/` →
`.../account/` → `.../preview/` → commit. **There is no column-mapping
step** -- columns are auto-detected at upload time (see Pipeline above),
and a file that doesn't auto-detect well enough sends the user to the
unreadable-file page instead of a wizard screen. It's reachable any time
from the Statements page or Settings, not just onboarding. The dashboard
is computed live from the database on every request (see
`core/views.py::dashboard`), so a successful import is reflected
immediately with no separate "refresh" step.

## Manual financial setup (`accounts/manual_setup.py`)

For a user with no statement to import (or whose file couldn't be read),
a one-page form (`accounts:manual_setup`) collects monthly take-home
income, additional income, either a lump total-monthly-expenses figure
or a category breakdown (housing, utilities, groceries, transportation,
insurance, debt payments, subscriptions, other -- breakdown always wins
over the lump total if both are filled in, to avoid double-counting),
current savings balance, minimum cash reserve, and a monthly savings
goal. Every field is optional.

**No new calculation logic**: submitting the form writes ordinary
`IncomeSource`/`RecurringExpense` rows (the same tables `budgets/urls.py`
already has add/delete views for), each named with an `"(estimate)"`
suffix -- e.g. `"Take-home income (estimate)"` -- which is how a
manually-declared row is distinguished from anything else in the budgets
UI, without a new source column. `budgets.services.build_budget_plan()`
is the one and only surplus/shortfall calculation; `accounts/manual_setup.py`
never computes its own estimate. Resubmitting the form updates the same
reserved-name rows (keyed by name + user) rather than piling up
duplicates.

Two numbers have nowhere existing to live and got two small `Profile`
fields instead (migration `accounts/0006_...`): `manual_savings_balance`
(+ `manual_savings_balance_updated_at`) and `manual_monthly_savings_goal`.
The minimum cash reserve reuses the existing `Profile.cash_reserve_target`
field directly -- the same field the round-up/investing-eligibility logic
already reads, so filling it in here has the same effect as setting it
in Settings. **Nothing here ever creates a `Transaction`** -- an
estimate is never turned into fake transaction history, and it never
overwrites a balance that came from an import or (if one ever exists) a
live bank connection; it's purely additive, read by `build_budget_plan`
alongside whatever real data exists.

The dashboard shows a labeled "estimate, not verified bank data" banner
when a manual estimate exists and there are still zero real transactions
(see `core/views.py::dashboard`'s `has_manual_estimate` context flag and
the banner in `templates/core/dashboard.html`); it disappears the moment
any real transaction exists, since `month_income`/`cash_balance` etc. are
already computed from real `Transaction` rows elsewhere on the page.

## Known limitations

- CSV only; no OFX/QFX/QIF/PDF/OCR.
- No background job queue — parsing happens synchronously in the request.
  Fine for CSVs up to the 2 MB / 20,000-row cap; would need a queue for
  anything bigger.
- A row flagged "needs review" (bad date/amount, ambiguous duplicate,
  conflicting amount columns, non-USD currency, zero amount) is never
  imported in that pass, and there is no way to override that from the
  UI — fix the source file and re-upload, or enter that one manually.
  This is deliberate: the whole point of removing the mapping screen was
  to stop asking a user to adjudicate things a machine can't safely guess
  either.
- Column detection is header-name matching against a fixed alias list; an
  unusual or non-English header just means that file won't auto-detect
  (and the user lands on the unreadable-file page) — it's never guessed.
- No multi-currency support: `Account`/`Transaction` have no currency
  field, so a mismatched currency column is a review flag, not a
  conversion.
- The manual-setup "monthly savings goal" is stored but not wired into
  any goal-progress UI yet — it's informational until a `savings.Goal`
  is created separately.

## Env vars / migrations

No new environment variables. Migrations: `imports/migrations/0001_initial.py`,
`accounts/migrations/0006_profile_manual_monthly_savings_goal_and_more.py`
(four additive `Profile` fields for the manual-setup feature).

## Tests run

`python manage.py test imports` — 57 tests covering file validation
(empty, oversized, binary-content-despite-.csv-extension, no
recognizable columns), automatic column detection including the
`Money_In_USD`/`Money_Out_USD`/`Amount_USD`/`Net_Amount_USD`/
`Running_Balance_USD` naming style and ignored optional-metadata columns,
single-amount vs. debit/credit vs. net-amount parsing, alternate date
formats, parenthesized/negative refund amounts, zero-amount flagging,
non-USD currency flagging, both-debit-and-credit-filled flagging,
agreeing vs. disagreeing amount columns (used once when they agree,
flagged for review rather than guessed when they don't, and
`Running_Balance_USD` never treated as a second amount), exact-reference
duplicate detection, in-batch ambiguous-fingerprint detection, the full
upload→account→preview→confirm happy path with **no column-mapping step**
(asserting the dashboard reflects it immediately), excluding a row via
its checkbox, re-importing the same file (no double-count), atomic
rollback on a simulated mid-commit failure (zero transactions persisted,
no raw exception text in the stored error message), cross-user 404s on
every step, and delete/retry behavior.

`python manage.py test accounts.tests.ManualFinancialSetupTests` — 11
tests: minimum-fields-only submission, a single field being enough,
breakdown-vs-lump-total precedence (never both), negative amounts
rejected, negative surplus shown as a shortfall, savings balance/goal
persisting across logout, idempotent resubmission, no fabricated
transactions, form prefill for editing, `cash_reserve_target` untouched
when its field is left blank, and cross-user isolation.

`python manage.py test core.tests.DashboardManualEstimateTests` — 3
tests: banner hidden with nothing entered, shown with a manual estimate
and zero real transactions, hidden again once a real transaction exists.

`python manage.py test` (full suite, 227 tests) — all pass except the
same 4 pre-existing failures in `transactions.tests` unrelated to this
feature (`seed_peachtree_demo` refusing its demo password when `DEBUG`
is false in this environment; not touched by either change in this doc).

# Transactions and statements

![Annotated transactions list](assets/screenshots/annotated/transactions-list-annotated.png)

## Transactions list

- Path: `/budgets/transactions/`
- Search/filter, add/edit/delete, CSV export (`/budgets/transactions/export/`)

### Workflow: add a transaction

1. Start at Transactions
2. Open **Add**
3. Provide kind (income/expense), amount (positive), description, date, optional category
4. Submit → row appears; dashboard/budget progress recalculate from live sums
5. On validation failure, form redisplays with errors (no row created)

### Business rules

- Amounts are always stored positive; `kind` determines sign for display (`signed_amount`)
- Money math uses `Decimal` with `ROUND_HALF_UP` to 2 places (`core.services.quantize_money`)
- Per-user isolation: every query filters `user=request.user`

## Statements

![Statement detail](assets/screenshots/raw/statement-detail.png)

- `/statements/` lists statement accounts (e.g. Peachtree demo)
- Detail shows running balances and reconciliation vs stated totals
- Seed: `python manage.py seed_peachtree_demo`

## Edge cases

- Duplicate imported `external_id` does not double-count (`transactions.services.record_transaction`)
- No pagination yet — large histories may load slowly

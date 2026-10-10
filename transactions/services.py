"""Transaction creation helpers, including idempotent import handling."""

from dataclasses import dataclass
from decimal import Decimal

from core.services import quantize_money

from .models import Account, Transaction


def record_transaction(user, *, kind, amount, occurred_on, category=None, description="",
                        source="manual", external_id=None, is_demo=False, reverses=None,
                        account=None):
    """Create a transaction, or return the existing one if this external_id
    was already recorded for this user+source (idempotent import).

    Returns (transaction, created).
    """
    if external_id:
        existing = Transaction.objects.filter(
            user=user, source=source, external_id=external_id
        ).first()
        if existing:
            return existing, False

    transaction = Transaction.objects.create(
        user=user,
        account=account,
        category=category,
        kind=kind,
        amount=amount,
        description=description,
        occurred_on=occurred_on,
        source=source,
        external_id=external_id,
        is_demo=is_demo,
        reverses=reverses,
    )
    return transaction, True


@dataclass
class LedgerRow:
    transaction: Transaction
    balance_after: Decimal


def compute_running_balances(account: Account) -> list[LedgerRow]:
    """Chronological running balance starting from account.opening_balance.

    Always computed live from opening_balance + the transaction sequence —
    never stored — so it can never drift out of sync with the ledger.
    """
    balance = quantize_money(account.opening_balance)
    rows = []
    qs = Transaction.objects.filter(account=account).order_by("occurred_on", "created_at")
    for txn in qs:
        balance = quantize_money(balance + txn.signed_amount)
        rows.append(LedgerRow(transaction=txn, balance_after=balance))
    return rows


@dataclass
class ReconciliationReport:
    opening_balance: Decimal
    computed_total_deposits: Decimal
    computed_total_withdrawals: Decimal
    computed_ending_balance: Decimal
    stated_total_deposits: Decimal | None
    stated_total_withdrawals: Decimal | None
    stated_ending_balance: Decimal | None
    deposits_match: bool | None
    withdrawals_match: bool | None
    ending_balance_match: bool | None

    @property
    def fully_reconciled(self) -> bool:
        return all(
            v is True for v in (self.deposits_match, self.withdrawals_match, self.ending_balance_match)
        )


def reconcile_account(account: Account) -> ReconciliationReport:
    """Verify the computed ledger against whatever totals the source
    statement claimed (account.stated_*). Never silently trusts the
    source totals — always recomputes from the transactions themselves
    using the accounting identity: ending = opening + deposits - withdrawals.
    """
    deposits = Decimal("0.00")
    withdrawals = Decimal("0.00")
    for txn in Transaction.objects.filter(account=account):
        if txn.kind == Transaction.Kind.INCOME:
            deposits += txn.amount
        else:
            withdrawals += txn.amount
    deposits = quantize_money(deposits)
    withdrawals = quantize_money(withdrawals)
    ending = quantize_money(account.opening_balance + deposits - withdrawals)

    def _match(stated, computed):
        if stated is None:
            return None
        return quantize_money(stated) == computed

    return ReconciliationReport(
        opening_balance=quantize_money(account.opening_balance),
        computed_total_deposits=deposits,
        computed_total_withdrawals=withdrawals,
        computed_ending_balance=ending,
        stated_total_deposits=account.stated_total_deposits,
        stated_total_withdrawals=account.stated_total_withdrawals,
        stated_ending_balance=account.stated_ending_balance,
        deposits_match=_match(account.stated_total_deposits, deposits),
        withdrawals_match=_match(account.stated_total_withdrawals, withdrawals),
        ending_balance_match=_match(account.stated_ending_balance, ending),
    )

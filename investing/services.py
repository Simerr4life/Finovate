"""Simulated round-up and investing math.

Nothing here talks to a real brokerage. "Sweeping" round-ups means moving
simulated ledger rows from pending to swept and updating a simulated
PortfolioSnapshot — it is a stand-in for what a real funding/investment
provider would eventually confirm.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from budgets.models import RecurringExpense
from budgets.services import monthly_equivalent
from core.services import quantize_money, round_up_to_nearest
from transactions.models import Transaction

from .models import PortfolioSnapshot, RoundUpLedgerEntry, RoundUpSettings, SimulatedOrder


def get_or_create_settings(user) -> RoundUpSettings:
    settings, _ = RoundUpSettings.objects.get_or_create(user=user)
    return settings


def create_roundup_for_transaction(transaction: Transaction) -> RoundUpLedgerEntry | None:
    """Create a pending round-up ledger entry for an eligible expense.

    Idempotent: a transaction can only ever have one round-up entry
    (enforced by the OneToOneField), so calling this twice for the same
    transaction (e.g. a duplicate webhook delivery) is a safe no-op.
    Returns None if round-ups are disabled/paused or the transaction isn't
    an eligible expense (income, or already reversed).
    """
    if transaction.kind != Transaction.Kind.EXPENSE:
        return None
    if transaction.reverses_id is not None:
        return None
    if hasattr(transaction, "roundup_entry"):
        return transaction.roundup_entry

    rs = get_or_create_settings(transaction.user)
    if not rs.enabled or rs.is_paused:
        return None

    roundup_amount = round_up_to_nearest(transaction.amount, rs.round_to)
    if roundup_amount <= 0:
        return None

    return RoundUpLedgerEntry.objects.create(
        user=transaction.user,
        source_transaction=transaction,
        eligible_amount=quantize_money(transaction.amount),
        round_up_amount=roundup_amount,
        status=RoundUpLedgerEntry.Status.PENDING,
    )


def reverse_roundup_for_transaction(transaction: Transaction) -> None:
    """Mark a transaction's round-up entry reversed if the purchase itself was reversed/refunded."""
    entry = getattr(transaction, "roundup_entry", None)
    if entry and entry.status == RoundUpLedgerEntry.Status.PENDING:
        entry.status = RoundUpLedgerEntry.Status.REVERSED
        entry.save(update_fields=["status", "updated_at"])


def available_cash_balance(user) -> Decimal:
    """Simple cash balance: all-time income minus all-time expenses.

    This intentionally ignores savings-goal allocations and invested
    principal — see the dashboard's balance breakdown — because "spare"
    cash should never be inferred from one unlabeled number.
    """
    income = Transaction.objects.filter(user=user, kind=Transaction.Kind.INCOME).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    expenses = Transaction.objects.filter(user=user, kind=Transaction.Kind.EXPENSE).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    return quantize_money(income - expenses)


def sweep_pending_roundups(user, as_of: date | None = None) -> dict:
    """Simulate sweeping eligible pending round-ups into the portfolio.

    Respects the contribution cap and minimum cash reserve. Never moves
    real money; this only updates simulated ledger/portfolio rows. If the
    user has chosen a target_pool (an is_investable Goal/Savings Pool), the
    resulting order and snapshot are attributed to that pool; otherwise
    they land in the general/unassigned bucket (pool=None).
    """
    as_of = as_of or timezone.now().date()
    rs = get_or_create_settings(user)
    pool = rs.target_pool if (rs.target_pool_id and rs.target_pool.is_investable) else None
    if not rs.enabled or rs.is_paused:
        return {"swept_amount": Decimal("0.00"), "entries_swept": 0, "reason": "round-ups disabled or paused"}

    pending = RoundUpLedgerEntry.objects.filter(user=user, status=RoundUpLedgerEntry.Status.PENDING)
    pending_total = pending.aggregate(total=Sum("round_up_amount"))["total"] or Decimal("0")

    cash_balance = available_cash_balance(user)
    headroom = cash_balance - rs.minimum_cash_reserve
    if headroom < 0:
        headroom = Decimal("0.00")

    sweep_limit = pending_total
    if rs.contribution_cap_per_period is not None:
        sweep_limit = min(sweep_limit, rs.contribution_cap_per_period)
    sweep_limit = min(sweep_limit, headroom)
    sweep_limit = quantize_money(sweep_limit)

    if sweep_limit <= 0:
        return {"swept_amount": Decimal("0.00"), "entries_swept": 0, "reason": "no headroom under cash reserve/cap"}

    running_total = Decimal("0.00")
    swept_ids = []
    for entry in pending.order_by("created_at"):
        if running_total + entry.round_up_amount > sweep_limit:
            continue
        running_total = quantize_money(running_total + entry.round_up_amount)
        swept_ids.append(entry.id)

    if not swept_ids:
        return {"swept_amount": Decimal("0.00"), "entries_swept": 0, "reason": "no single entry fit under the remaining limit"}

    RoundUpLedgerEntry.objects.filter(id__in=swept_ids).update(
        status=RoundUpLedgerEntry.Status.SWEPT, swept_at=timezone.now()
    )

    order = SimulatedOrder.objects.create(
        user=user,
        pool=pool,
        order_type=SimulatedOrder.OrderType.BUY,
        amount=running_total,
        status=SimulatedOrder.Status.FILLED,
        filled_at=timezone.now(),
    )

    prior_snapshot = PortfolioSnapshot.objects.filter(user=user, pool=pool).order_by("-as_of").first()
    prior_contributions = prior_snapshot.net_contributions if prior_snapshot else Decimal("0.00")
    prior_value = prior_snapshot.market_value if prior_snapshot else Decimal("0.00")

    new_contributions = quantize_money(prior_contributions + running_total)
    new_value = quantize_money(prior_value + running_total)  # simulated: no market drift applied here

    PortfolioSnapshot.objects.update_or_create(
        user=user,
        pool=pool,
        as_of=as_of,
        defaults={"net_contributions": new_contributions, "market_value": new_value},
    )

    return {"swept_amount": running_total, "entries_swept": len(swept_ids), "order": order, "pool": pool}


@dataclass
class SurplusBreakdown:
    """Transparent breakdown of how much cash is actually free to invest.

    Never infers that money is "spare" just because it's left after
    recorded expenses: it explicitly subtracts the user's declared cash
    reserve, money already earmarked in savings goals, and a one-month
    buffer for known recurring bills, before calling anything a surplus.
    """

    cash_balance: Decimal
    minimum_cash_reserve: Decimal
    goal_allocations: Decimal
    upcoming_bills_buffer: Decimal
    investable_surplus: Decimal
    notes: list[str] = field(default_factory=list)


def compute_investable_surplus(user) -> SurplusBreakdown:
    from savings.models import Goal  # local import avoids a hard app-load-order dependency

    cash_balance = available_cash_balance(user)
    rs = get_or_create_settings(user)

    goal_allocations = Decimal("0.00")
    for g in Goal.objects.filter(user=user, achieved_at__isnull=True):
        goal_allocations += g.current_amount
    goal_allocations = quantize_money(goal_allocations)

    bills_buffer = Decimal("0.00")
    for exp in RecurringExpense.objects.filter(user=user, is_active=True):
        bills_buffer += monthly_equivalent(exp.amount, exp.cadence)
    bills_buffer = quantize_money(bills_buffer)

    reserved = quantize_money(rs.minimum_cash_reserve + goal_allocations + bills_buffer)
    surplus = cash_balance - reserved
    if surplus < 0:
        surplus = Decimal("0.00")
    surplus = quantize_money(surplus)

    notes = [
        f"Starts from cash balance (${cash_balance}), not any goal or invested funds.",
        f"Protects your minimum cash reserve (${rs.minimum_cash_reserve}).",
        f"Protects money already allocated to active savings goals (${goal_allocations}).",
        f"Reserves one month of your active recurring expenses as a bills buffer (${bills_buffer}).",
        "This is an estimate for illustration — it does not know about one-off upcoming bills you haven't entered.",
    ]

    return SurplusBreakdown(
        cash_balance=cash_balance,
        minimum_cash_reserve=rs.minimum_cash_reserve,
        goal_allocations=goal_allocations,
        upcoming_bills_buffer=bills_buffer,
        investable_surplus=surplus,
        notes=notes,
    )


def propose_surplus_investment(user, amount: Decimal, pool=None) -> SimulatedOrder:
    """Create a PENDING simulated order representing a proposed investment
    of surplus cash into an investable savings pool (or the general
    bucket if pool is None). Nothing is approved/filled until a separate,
    explicit approve_order() call — mirroring the confirmation step a real
    brokerage integration would require before moving money.
    """
    if pool is not None and not pool.is_investable:
        raise ValueError("pool must have is_investable=True")
    return SimulatedOrder.objects.create(
        user=user,
        pool=pool,
        order_type=SimulatedOrder.OrderType.BUY,
        amount=quantize_money(amount),
        status=SimulatedOrder.Status.PENDING,
    )


def approve_order(order: SimulatedOrder, as_of: date | None = None) -> SimulatedOrder:
    """Simulate approving/filling a pending order: never a real trade."""
    as_of = as_of or timezone.now().date()
    order.status = SimulatedOrder.Status.FILLED
    order.filled_at = timezone.now()
    order.save(update_fields=["status", "filled_at", "updated_at"])

    prior = PortfolioSnapshot.objects.filter(user=order.user, pool=order.pool).order_by("-as_of").first()
    prior_contributions = prior.net_contributions if prior else Decimal("0.00")
    prior_value = prior.market_value if prior else Decimal("0.00")
    PortfolioSnapshot.objects.update_or_create(
        user=order.user,
        pool=order.pool,
        as_of=as_of,
        defaults={
            "net_contributions": quantize_money(prior_contributions + order.amount),
            "market_value": quantize_money(prior_value + order.amount),
        },
    )
    return order


def reject_order(order: SimulatedOrder) -> SimulatedOrder:
    order.status = SimulatedOrder.Status.REJECTED
    order.save(update_fields=["status", "updated_at"])
    return order


def investable_pools(user):
    """Savings Pools the user has marked investable — the only pools
    eligible as a round-up/surplus investment target."""
    from savings.models import Goal

    return Goal.objects.filter(user=user, is_investable=True)


def pool_investment_summaries(user) -> list[dict]:
    """Latest invested-amount snapshot for each investable pool, kept
    separate from that pool's own cash current_amount (see Goal.is_investable
    docstring) so cash savings and market exposure are never conflated."""
    summaries = []
    for pool in investable_pools(user):
        snapshot = PortfolioSnapshot.objects.filter(user=user, pool=pool).order_by("-as_of").first()
        summaries.append({"pool": pool, "snapshot": snapshot})
    return summaries


@dataclass
class HypotheticalScenario:
    """A purely illustrative "what if" calculation using prices the caller
    supplies themselves.

    This is deliberately NOT backed by any market-data API: Finovate has
    no live or historical price feed connected, so it never claims a price
    is "verified." The caller (today, a human typing numbers into a form)
    is responsible for the prices; this function only does the decimal-safe
    arithmetic and keeps the disclaimer front and center.
    """

    symbol: str
    invest_date: date
    invest_price: Decimal
    valuation_date: date
    valuation_price: Decimal
    amount_invested: Decimal
    shares: Decimal
    value_at_valuation_date: Decimal
    gain_loss: Decimal
    gain_loss_percent: Decimal


SHARE_PLACES = Decimal("0.000001")


def compute_hypothetical_scenario(
    *, symbol: str, invest_date: date, invest_price: Decimal,
    valuation_date: date, valuation_price: Decimal, amount_invested: Decimal,
) -> HypotheticalScenario:
    if invest_price <= 0:
        raise ValueError("invest_price must be positive")
    amount_invested = quantize_money(amount_invested)
    shares = (amount_invested / invest_price).quantize(SHARE_PLACES)
    value_at_valuation_date = quantize_money(shares * valuation_price)
    gain_loss = quantize_money(value_at_valuation_date - amount_invested)
    gain_loss_percent = (
        quantize_money((gain_loss / amount_invested) * 100) if amount_invested > 0 else Decimal("0.00")
    )
    return HypotheticalScenario(
        symbol=symbol,
        invest_date=invest_date,
        invest_price=invest_price,
        valuation_date=valuation_date,
        valuation_price=valuation_price,
        amount_invested=amount_invested,
        shares=shares,
        value_at_valuation_date=value_at_valuation_date,
        gain_loss=gain_loss,
        gain_loss_percent=gain_loss_percent,
    )

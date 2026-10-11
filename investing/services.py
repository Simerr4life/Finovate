"""Simulated round-up and investing math.

Nothing here talks to a real brokerage. "Sweeping" round-ups means moving
simulated ledger rows from pending to swept and updating a simulated
PortfolioSnapshot — it is a stand-in for what a real funding/investment
provider would eventually confirm.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_DOWN

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from budgets.models import RecurringExpense
from budgets.services import monthly_equivalent
from core.services import quantize_money, round_up_to_nearest
from transactions.models import Transaction

from .models import (
    DemoInvestmentFunding,
    DemoInvestmentSuggestion,
    MarketPrice,
    PortfolioSnapshot,
    RoundUpLedgerEntry,
    RoundUpSettings,
    SimulatedOrder,
)


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


def available_demo_investment_budget(user) -> Decimal:
    surplus = compute_investable_surplus(user).investable_surplus
    demo_funds = (
        DemoInvestmentFunding.objects.filter(user=user).aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )
    committed = (
        SimulatedOrder.objects.filter(
            user=user,
            status__in=[SimulatedOrder.Status.PENDING, SimulatedOrder.Status.FILLED],
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    return max(quantize_money(surplus + demo_funds - committed), Decimal("0.00"))


def add_demo_investment_funds(user, amount: Decimal) -> DemoInvestmentFunding:
    """Record a virtual top-up without changing the user's real cash ledger."""
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Enter a demo amount greater than $0.00.")
    if amount > Decimal("9999999999.99"):
        raise ValueError("Enter a demo amount no greater than $9,999,999,999.99.")
    rounded_amount = quantize_money(amount)
    if amount != rounded_amount:
        raise ValueError("Enter a demo amount with no more than two decimal places.")
    return DemoInvestmentFunding.objects.create(user=user, amount=rounded_amount)


@db_transaction.atomic
def create_demo_market_order(user, symbol: str, amount: Decimal, pool=None) -> SimulatedOrder:
    """Create a pending simulated buy order using the latest bundled sample close."""
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Enter an amount greater than $0.00.")
    amount = quantize_money(amount)
    if pool is not None and (pool.user_id != user.pk or not pool.is_investable):
        raise ValueError("Choose one of your investable savings pools.")

    latest_price = MarketPrice.objects.filter(
        symbol=symbol,
        is_verified=True,
        is_demo_sample=True,
    ).order_by("-date").first()
    if latest_price is None:
        raise ValueError("Choose an asset from the supplied sample market data.")

    if amount > available_demo_investment_budget(user):
        raise ValueError(
            "That amount is above your available demo investing budget. "
            "Check your investable surplus and pending orders."
        )

    shares = (amount / latest_price.close).quantize(SHARE_PLACES)
    return SimulatedOrder.objects.create(
        user=user,
        pool=pool,
        symbol=latest_price.symbol,
        order_type=SimulatedOrder.OrderType.BUY,
        amount=amount,
        status=SimulatedOrder.Status.PENDING,
        demo_execution_price=latest_price.close,
        demo_shares=shares,
        demo_data_date=latest_price.date,
    )


def _demo_stock_metrics(rows: list[MarketPrice]) -> dict | None:
    if len(rows) < 2 or rows[0].close <= 0:
        return None

    first, latest = rows[0], rows[-1]
    total_return = quantize_money(
        ((latest.close - first.close) / first.close) * Decimal("100")
    )
    daily_changes = [
        row.daily_change_percent
        for row in rows
        if row.daily_change_percent is not None
    ]
    if daily_changes:
        mean = sum(daily_changes, Decimal("0")) / len(daily_changes)
        variance = sum(
            ((change - mean) ** 2 for change in daily_changes), Decimal("0")
        ) / len(daily_changes)
        volatility = quantize_money(variance.sqrt())
    else:
        volatility = Decimal("0.00")

    score = quantize_money(total_return - volatility)
    return {
        "symbol": latest.symbol,
        "data_date": latest.date,
        "price": latest.close,
        "return": total_return,
        "volatility": volatility,
        "score": score,
        "first_date": first.date,
    }


def generate_demo_investment_suggestions(user) -> list[DemoInvestmentSuggestion]:
    """Create once-per-dataset, user-reviewed ideas from the bundled sample prices.

    This is deterministic demo logic, not a predictive model or investment
    advice. The suggested amounts are capped by the user's available demo
    investing budget, and accepting an idea only creates a simulated order.
    """
    available_budget = available_demo_investment_budget(user)
    if available_budget <= 0:
        return []

    stock_rows = MarketPrice.objects.filter(
        asset_type=MarketPrice.AssetType.STOCK,
        is_verified=True,
        is_demo_sample=True,
    ).order_by("symbol", "date")
    grouped: dict[str, list[MarketPrice]] = {}
    for row in stock_rows:
        grouped.setdefault(row.symbol, []).append(row)

    candidates = [
        metrics
        for rows in grouped.values()
        if (metrics := _demo_stock_metrics(rows)) is not None
    ]
    candidates.sort(key=lambda candidate: (-candidate["score"], candidate["symbol"]))
    candidates = candidates[:3]
    if not candidates:
        return []

    new_candidates = [
        candidate
        for candidate in candidates
        if not DemoInvestmentSuggestion.objects.filter(
            user=user,
            symbol=candidate["symbol"],
            data_date=candidate["data_date"],
        ).exists()
    ]
    if not new_candidates:
        return [
            DemoInvestmentSuggestion.objects.get(
                user=user,
                symbol=candidate["symbol"],
                data_date=candidate["data_date"],
            )
            for candidate in candidates
        ]

    budget = min(available_budget, Decimal("75.00"))
    cents = int((budget * 100).to_integral_value(rounding=ROUND_DOWN))
    recommendation_count = min(len(new_candidates), cents)
    if recommendation_count <= 0:
        return []
    new_candidates = new_candidates[:recommendation_count]
    base_cents, extra_cents = divmod(cents, recommendation_count)

    suggestions = []
    for index, candidate in enumerate(new_candidates):
        amount = Decimal(base_cents + (1 if index < extra_cents else 0)) / 100
        explanation = (
            f"From {candidate['first_date']} to {candidate['data_date']}, "
            f"{candidate['symbol']} changed {candidate['return']}% in the supplied "
            f"sample; observed daily volatility was {candidate['volatility']}%. "
            "The demo ranks sample-period return minus volatility. Past movement "
            "does not predict future results."
        )
        suggestion, _ = DemoInvestmentSuggestion.objects.get_or_create(
            user=user,
            symbol=candidate["symbol"],
            data_date=candidate["data_date"],
            defaults={
                "amount": amount,
                "demo_execution_price": candidate["price"],
                "historical_return_percent": candidate["return"],
                "volatility_percent": candidate["volatility"],
                "score": candidate["score"],
                "explanation": explanation,
            },
        )
        suggestions.append(suggestion)
    return suggestions


@db_transaction.atomic
def accept_demo_investment_suggestion(
    user, suggestion: DemoInvestmentSuggestion, pool=None
) -> SimulatedOrder:
    suggestion = DemoInvestmentSuggestion.objects.select_for_update().get(
        pk=suggestion.pk, user=user, status=DemoInvestmentSuggestion.Status.PENDING
    )
    if pool is not None and (
        pool.user_id != user.pk or not pool.is_investable
    ):
        raise ValueError("Choose one of your investable savings pools.")

    current_budget = available_demo_investment_budget(user)
    if suggestion.amount > current_budget:
        raise ValueError("Your current demo investing budget is below this suggestion.")

    shares = (suggestion.amount / suggestion.demo_execution_price).quantize(
        SHARE_PLACES
    )
    order = SimulatedOrder.objects.create(
        user=user,
        pool=pool,
        symbol=suggestion.symbol,
        order_type=SimulatedOrder.OrderType.BUY,
        amount=suggestion.amount,
        status=SimulatedOrder.Status.PENDING,
        demo_execution_price=suggestion.demo_execution_price,
        demo_shares=shares,
        demo_data_date=suggestion.data_date,
    )
    suggestion.status = DemoInvestmentSuggestion.Status.ACCEPTED
    suggestion.simulated_order = order
    suggestion.save(update_fields=["status", "simulated_order", "updated_at"])
    return order


@db_transaction.atomic
def decline_demo_investment_suggestion(
    user, suggestion: DemoInvestmentSuggestion
) -> DemoInvestmentSuggestion:
    suggestion = DemoInvestmentSuggestion.objects.select_for_update().get(
        pk=suggestion.pk, user=user, status=DemoInvestmentSuggestion.Status.PENDING
    )
    suggestion.status = DemoInvestmentSuggestion.Status.DECLINED
    suggestion.save(update_fields=["status", "updated_at"])
    return suggestion


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

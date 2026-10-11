"""Automated savings: capacity calculation, default pools, and the savings plan.

This module is the one place the "how much can I afford to save" formula
lives. Views, signals, and tests all call it; nothing else re-derives it.

    Available savings = confirmed monthly income
                        - monthly costs (recurring obligations + budgeted spending)

Everything here is a *recommendation*. Nothing in this module moves money,
records a deposit, or places an investment order. Money reaches a pool only
when the user records a Contribution themselves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from budgets.models import Budget, BudgetPeriod, IncomeSource, RecurringExpense
from budgets.services import monthly_equivalent
from core.display import add_months, month_start
from core.services import quantize_money
from transactions.models import Transaction

from .models import Goal, SavingsPlan, SavingsPlanAllocation

ZERO = Decimal("0.00")
WEEKS_PER_YEAR = Decimal("52")
MONTHS_PER_YEAR = Decimal("12")
RECORDED_LOOKBACK_MONTHS = 3
RAINY_DAY_TARGET_MONTHS = 3

# The three pools every user gets. Order here is display order, and also the
# tie-break order when a leftover cent is handed out during rounding.
DEFAULT_POOLS = [
    {
        "pool_kind": Goal.PoolKind.RAINY_DAY,
        "name": "Rainy Day",
        "category": Goal.Category.EMERGENCY,
        "color": "#2f7d62",
        "is_investable": False,
        "purpose": "For emergencies and unexpected expenses.",
    },
    {
        "pool_kind": Goal.PoolKind.INVESTMENT,
        "name": "Investment",
        "category": Goal.Category.OTHER,
        "color": "#c8963e",
        "is_investable": True,
        "purpose": "For long-term investing goals.",
    },
    {
        "pool_kind": Goal.PoolKind.REGULAR,
        "name": "Regular Savings",
        "category": Goal.Category.OTHER,
        "color": "#4f7cac",
        "is_investable": False,
        "purpose": "For general savings and planned purchases.",
    },
]
POOL_ORDER = [spec["pool_kind"] for spec in DEFAULT_POOLS]
POOL_PURPOSE = {spec["pool_kind"]: spec["purpose"] for spec in DEFAULT_POOLS}


# ---------------------------------------------------------------------------
# Default pools
# ---------------------------------------------------------------------------


def ensure_default_pools(user) -> dict[str, Goal]:
    """Create any of the three default pools the user is missing.

    Safe to call on every request: existing pools (and their balances) are
    never modified, and the (user, pool_kind) unique constraint means two
    concurrent calls can't both insert the same pool.
    """
    existing = {g.pool_kind: g for g in Goal.objects.filter(user=user).exclude(pool_kind="")}
    for spec in DEFAULT_POOLS:
        kind = spec["pool_kind"]
        if kind in existing:
            continue
        defaults = {
            "name": spec["name"],
            "category": spec["category"],
            "color": spec["color"],
            "is_investable": spec["is_investable"],
            "target_amount": ZERO,
            "current_amount": ZERO,
        }
        try:
            with transaction.atomic():
                pool, _ = Goal.objects.get_or_create(user=user, pool_kind=kind, defaults=defaults)
        except IntegrityError:
            pool = Goal.objects.get(user=user, pool_kind=kind)
        existing[kind] = pool
    return existing


def ensure_plan(user) -> SavingsPlan:
    plan, _ = SavingsPlan.objects.get_or_create(user=user)
    return plan


# ---------------------------------------------------------------------------
# Savings capacity
# ---------------------------------------------------------------------------


@dataclass
class CapacityLine:
    label: str
    amount: Decimal
    note: str = ""


@dataclass
class SavingsCapacity:
    basis: str
    monthly_income: Decimal = ZERO
    total_costs: Decimal = ZERO
    available: Decimal = ZERO
    shortfall: Decimal = ZERO
    income_lines: list[CapacityLine] = field(default_factory=list)
    cost_lines: list[CapacityLine] = field(default_factory=list)
    excluded_lines: list[CapacityLine] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing and bool(self.basis)

    @property
    def has_shortfall(self) -> bool:
        return self.is_complete and self.shortfall > 0


def _declared_capacity(user) -> SavingsCapacity | None:
    """Capacity from income sources and recurring expenses the user entered."""
    regular_income = ZERO
    income_lines = []
    excluded = []
    for src in IncomeSource.objects.filter(user=user, is_active=True).order_by("name"):
        monthly = monthly_equivalent(src.amount, src.cadence)
        if monthly <= 0:
            continue
        if src.cadence == "irregular":
            excluded.append(
                CapacityLine(src.name, monthly, "Irregular income isn't guaranteed, so it isn't counted.")
            )
            continue
        regular_income += monthly
        income_lines.append(CapacityLine(src.name, monthly, src.get_cadence_display()))

    recurring = list(RecurringExpense.objects.filter(user=user, is_active=True).order_by("name"))
    if not income_lines and not recurring:
        return None

    capacity = SavingsCapacity(basis=SavingsPlan.Basis.DECLARED, excluded_lines=excluded)
    capacity.income_lines = income_lines
    capacity.monthly_income = quantize_money(regular_income)

    obligations = ZERO
    for exp in recurring:
        monthly = monthly_equivalent(exp.amount, exp.cadence)
        obligations += monthly
        capacity.cost_lines.append(CapacityLine(exp.name, monthly, "Recurring obligation"))

    # Budgeted variable spending (e.g. groceries) counts too, unless the same
    # category is already covered by a recurring expense, or the user's manual
    # setup estimate already describes *all* monthly costs. Either way it would
    # be counted twice.
    from accounts.manual_setup import ALL_MANUAL_EXPENSE_NAMES

    manual_estimate = any(exp.name in ALL_MANUAL_EXPENSE_NAMES for exp in recurring)
    budgeted = ZERO
    if not manual_estimate:
        covered = {exp.category_id for exp in recurring if exp.category_id}
        period = BudgetPeriod.objects.filter(user=user, is_active=True).first()
        if period:
            for budget in Budget.objects.filter(period=period, user=user).select_related("category"):
                if budget.category_id in covered or budget.limit_amount <= 0:
                    continue
                amount = quantize_money(budget.limit_amount)
                budgeted += amount
                capacity.cost_lines.append(
                    CapacityLine(f"{budget.category.name} budget", amount, "Planned spending limit")
                )

    capacity.total_costs = quantize_money(obligations + budgeted)

    if not income_lines:
        capacity.missing.append(
            "Add your regular take-home income so we can tell how much is left after costs."
        )
    if not capacity.cost_lines:
        capacity.missing.append(
            "Add your monthly expenses (housing, bills, transport, debt payments, subscriptions)."
        )

    capacity.assumptions = [
        "Weekly amounts count as 4.33 per month and every-two-weeks amounts as 2.17.",
        "Only active, regular income counts. Irregular income, credit limits, and borrowed money are never treated as available cash.",
        "Recurring expenses already include bills, housing, utilities, transport, debt payments and subscriptions you entered.",
        "Budget limits are added only for categories that aren't already a recurring expense, so nothing is counted twice.",
    ]
    if manual_estimate:
        capacity.assumptions.append(
            "Your manual setup estimate covers all monthly costs, so budget limits aren't added on top."
        )
    return capacity


def _recorded_capacity(user, today: date) -> SavingsCapacity | None:
    """Fallback: average of the last complete months of recorded transactions."""
    window_end = month_start(today)  # exclusive: the current month is incomplete
    window_start = add_months(window_end, -RECORDED_LOOKBACK_MONTHS)
    qs = Transaction.objects.filter(user=user, occurred_on__gte=window_start, occurred_on__lt=window_end)
    first = qs.order_by("occurred_on").values_list("occurred_on", flat=True).first()
    if first is None:
        return None
    first_month = month_start(first)
    months = (window_end.year - first_month.year) * 12 + (window_end.month - first_month.month)
    months = max(months, 1)

    earned = qs.filter(kind=Transaction.Kind.INCOME).filter(
        Q(category__isnull=True) | Q(category__is_earned_income=True)
    ).aggregate(total=Sum("amount"))["total"] or ZERO
    transfers = qs.filter(
        kind=Transaction.Kind.INCOME, category__is_earned_income=False
    ).aggregate(total=Sum("amount"))["total"] or ZERO
    spent = qs.filter(kind=Transaction.Kind.EXPENSE).aggregate(total=Sum("amount"))["total"] or ZERO

    divisor = Decimal(months)
    capacity = SavingsCapacity(basis=SavingsPlan.Basis.RECORDED)
    capacity.monthly_income = quantize_money(earned / divisor)
    capacity.total_costs = quantize_money(spent / divisor)
    period = f"{months} complete month{'s' if months != 1 else ''}"
    capacity.income_lines.append(
        CapacityLine("Average earned income", capacity.monthly_income, f"From {period} of transactions")
    )
    capacity.cost_lines.append(
        CapacityLine("Average spending", capacity.total_costs, f"From {period} of transactions")
    )
    if transfers > 0:
        capacity.excluded_lines.append(
            CapacityLine(
                "Transfers & reimbursements",
                quantize_money(transfers / divisor),
                "Not earned income, so not counted.",
            )
        )
    if capacity.monthly_income <= 0:
        capacity.missing.append("No earned income was recorded recently. Add your regular income.")
    if capacity.total_costs <= 0:
        capacity.missing.append("No spending was recorded recently. Add your monthly expenses.")
    capacity.assumptions = [
        f"Averages your last {period} of recorded transactions; the current month is left out because it isn't finished.",
        "Recurring bills are already inside your recorded spending, so they aren't subtracted twice.",
        "Transfers and reimbursements aren't earned income and are left out.",
        "Enter your income and recurring expenses for a more precise plan.",
    ]
    return capacity


def compute_savings_capacity(user, today: date | None = None) -> SavingsCapacity:
    """How much the user can afford to save each month, with a full breakdown.

    Never returns a positive figure built from missing data: when income or
    expenses are unknown, ``missing`` says what to add and ``available`` is 0.
    """
    today = today or timezone.localdate()
    capacity = _declared_capacity(user)
    if capacity is None or not capacity.income_lines:
        recorded = _recorded_capacity(user, today)
        if recorded is not None and (capacity is None or recorded.is_complete):
            capacity = recorded
    if capacity is None:
        capacity = SavingsCapacity(
            basis=SavingsPlan.Basis.NONE,
            missing=[
                "Add your regular income and monthly expenses, or import a bank statement, to see how much you can save."
            ],
        )

    if capacity.is_complete:
        net = capacity.monthly_income - capacity.total_costs
        capacity.available = quantize_money(max(net, ZERO))
        capacity.shortfall = quantize_money(max(-net, ZERO))
    else:
        capacity.available = ZERO
        capacity.shortfall = ZERO
    return capacity


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def validate_percents(percents: dict[str, int]) -> None:
    if any(p < 0 for p in percents.values()):
        raise ValueError("Allocation percentages can't be negative.")
    if sum(percents.values()) != 100:
        raise ValueError("Allocation percentages must add up to 100.")


def allocate(available: Decimal, percents: dict[str, int]) -> dict[str, Decimal]:
    """Split ``available`` across pools by percentage, to the cent.

    Each share is rounded *down* to a cent, then any leftover cents go one at
    a time to the shares with the largest dropped fraction. The total always
    equals ``available`` truncated to cents, so it can never exceed it.
    """
    validate_percents(percents)
    available = Decimal(available)
    if available <= 0:
        return {kind: ZERO for kind in percents}
    cents = int((available * 100).to_integral_value(rounding=ROUND_DOWN))
    shares = {kind: cents * pct // 100 for kind, pct in percents.items()}
    leftover = cents - sum(shares.values())
    order = sorted(
        (kind for kind, pct in percents.items() if pct > 0),
        key=lambda kind: (-((cents * percents[kind]) % 100), _order_index(kind)),
    )
    for kind in order[:leftover]:
        shares[kind] += 1
    return {kind: (Decimal(value) / 100).quantize(Decimal("0.01")) for kind, value in shares.items()}


def _order_index(kind: str) -> int:
    return POOL_ORDER.index(kind) if kind in POOL_ORDER else len(POOL_ORDER)


def per_period(monthly: Decimal, cadence: str) -> Decimal:
    """Convert a monthly recommendation to the plan's cadence, rounding down."""
    monthly = Decimal(monthly)
    if cadence == SavingsPlan.Cadence.WEEKLY:
        return (monthly * MONTHS_PER_YEAR / WEEKS_PER_YEAR).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return quantize_money(monthly)


# ---------------------------------------------------------------------------
# Plan recalculation
# ---------------------------------------------------------------------------


@dataclass
class RecalcResult:
    plan: SavingsPlan
    capacity: SavingsCapacity
    created: bool
    changed: bool
    notified: bool


def recalculate_plan(user, today: date | None = None) -> RecalcResult:
    """Bring the user's pools and savings plan up to date. Idempotent.

    Running this any number of times with the same financial data leaves the
    database exactly as one run would: no duplicate pools, plans,
    allocations, or notifications. Nothing here records a deposit or moves
    money.
    """
    from accounts.models import NotificationEvent

    capacity = compute_savings_capacity(user, today=today)
    with transaction.atomic():
        pools = ensure_default_pools(user)
        plan, created = SavingsPlan.objects.get_or_create(user=user)
        plan = SavingsPlan.objects.select_for_update().get(pk=plan.pk)

        allocatable = capacity.available
        if plan.status == SavingsPlan.Status.DISABLED or not capacity.is_complete:
            allocatable = ZERO
        amounts = allocate(allocatable, plan.percents())

        changed = (
            plan.basis != capacity.basis
            or plan.monthly_income != capacity.monthly_income
            or plan.monthly_costs != capacity.total_costs
            or plan.available_monthly != capacity.available
            or plan.shortfall_monthly != capacity.shortfall
        )
        for kind, pool in pools.items():
            pct = plan.percents()[kind]
            alloc, alloc_created = SavingsPlanAllocation.objects.get_or_create(
                plan=plan, pool=pool, defaults={"percent": pct, "recommended_monthly": amounts[kind]}
            )
            if not alloc_created and (alloc.percent != pct or alloc.recommended_monthly != amounts[kind]):
                alloc.percent = pct
                alloc.recommended_monthly = amounts[kind]
                alloc.save(update_fields=["percent", "recommended_monthly", "updated_at"])
                changed = True
            elif alloc_created:
                changed = True

        first_run = plan.recalculated_at is None
        notified = False
        if changed or first_run:
            plan.basis = capacity.basis
            plan.monthly_income = capacity.monthly_income
            plan.monthly_costs = capacity.total_costs
            plan.available_monthly = capacity.available
            plan.shortfall_monthly = capacity.shortfall
            plan.recalculated_at = timezone.now()
            plan.save()
            message = _change_message(plan, capacity, amounts, first_run)
            if message and plan.status == SavingsPlan.Status.ACTIVE:
                NotificationEvent.objects.create(
                    user=user, event_type=NotificationEvent.EventType.SAVINGS_PLAN, message=message[:255]
                )
                notified = True
    return RecalcResult(plan=plan, capacity=capacity, created=created, changed=changed, notified=notified)


def _change_message(plan, capacity, amounts, first_run) -> str:
    if not capacity.is_complete:
        return ""
    if capacity.has_shortfall:
        return (
            f"Your current budget can't support savings: monthly costs exceed income by "
            f"${capacity.shortfall:,.2f}. No savings were recommended."
        )
    verb = "created" if first_run else "updated"
    parts = ", ".join(
        f"{spec['name']} ${amounts[spec['pool_kind']]:,.2f}" for spec in DEFAULT_POOLS
    )
    return f"Savings plan {verb}: ${capacity.available:,.2f}/month available ({parts})."


def recalculate_for_user_id(user_id) -> None:
    """Entry point for signals. Skips users deleted in the same transaction."""
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is not None:
        recalculate_plan(user)


# ---------------------------------------------------------------------------
# Presentation helpers (pure; no writes)
# ---------------------------------------------------------------------------


@dataclass
class PoolPlanRow:
    pool: Goal
    purpose: str
    percent: int
    recommended_monthly: Decimal
    recommended_per_period: Decimal
    deposited: Decimal
    estimated_completion: date | None
    required_monthly: Decimal | None
    target_unreachable: bool


def pool_plan_rows(plan: SavingsPlan, today: date | None = None) -> list[PoolPlanRow]:
    from .services import contribution_pace

    today = today or timezone.localdate()
    allocations = {
        a.pool.pool_kind: a for a in plan.allocations.select_related("pool").exclude(pool__pool_kind="")
    }
    rows = []
    for kind in POOL_ORDER:
        alloc = allocations.get(kind)
        if alloc is None:
            continue
        pool = alloc.pool
        recommended = alloc.recommended_monthly if plan.status == SavingsPlan.Status.ACTIVE else ZERO
        eta = None
        if pool.has_target and pool.remaining_amount > 0 and recommended > 0:
            months = math.ceil(pool.remaining_amount / recommended)
            if months <= 600:
                eta = add_months(month_start(today), months)
        required = None
        unreachable = False
        if pool.has_target and pool.target_date and pool.remaining_amount > 0:
            pace = contribution_pace(pool.remaining_amount, pool.target_date, today=today)
            if pace is None:
                unreachable = True  # the target date has already passed
            else:
                required = pace["monthly"]
                unreachable = required > alloc.recommended_monthly
        rows.append(
            PoolPlanRow(
                pool=pool,
                purpose=POOL_PURPOSE.get(kind, ""),
                percent=alloc.percent,
                recommended_monthly=recommended,
                recommended_per_period=per_period(recommended, plan.cadence),
                deposited=pool.current_amount,
                estimated_completion=eta,
                required_monthly=required,
                target_unreachable=unreachable,
            )
        )
    return rows


def suggested_rainy_day_target(capacity: SavingsCapacity) -> Decimal | None:
    """Three months of costs: a common emergency-fund rule of thumb."""
    if not capacity.is_complete or capacity.total_costs <= 0:
        return None
    return quantize_money(capacity.total_costs * RAINY_DAY_TARGET_MONTHS)

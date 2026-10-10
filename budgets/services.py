"""Budget calculation and simple budget-plan generation.

Pure functions over models — no view/request logic here — so they're easy
to unit test and to call from both the website and (later) a messaging
integration without duplicating logic.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from core.services import quantize_money
from transactions.models import Transaction

# Rough multiplier to normalize a recurring amount to "per month", used only
# for the budget-plan estimate. Not exact calendar math on purpose — it's a
# planning aid, not an accounting ledger.
CADENCE_TO_MONTHLY = {
    "weekly": Decimal("4.33"),
    "biweekly": Decimal("2.17"),
    "monthly": Decimal("1"),
    "irregular": Decimal("1"),
}


def monthly_equivalent(amount: Decimal, cadence: str) -> Decimal:
    factor = CADENCE_TO_MONTHLY.get(cadence, Decimal("1"))
    return quantize_money(Decimal(amount) * factor)


@dataclass
class BudgetProgress:
    budget_id: int
    category_name: str
    limit_amount: Decimal
    spent_amount: Decimal
    remaining_amount: Decimal
    percent_used: int
    warning_threshold_percent: int
    is_warning: bool
    is_over: bool


def compute_budget_progress(budget, as_of: date | None = None) -> BudgetProgress:
    """Spent amount is computed live from transactions in the budget's
    period and category — it is never stored, so it can't go stale.
    """
    qs = Transaction.objects.filter(
        user_id=budget.user_id,
        category_id=budget.category_id,
        kind=Transaction.Kind.EXPENSE,
        occurred_on__gte=budget.period.start_date,
        occurred_on__lte=as_of or budget.period.end_date,
    )
    spent = qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    spent = quantize_money(spent)
    limit_amount = quantize_money(budget.limit_amount)
    remaining = quantize_money(limit_amount - spent)
    percent_used = int((spent / limit_amount) * 100) if limit_amount > 0 else 0
    return BudgetProgress(
        budget_id=budget.id,
        category_name=budget.category.name,
        limit_amount=limit_amount,
        spent_amount=spent,
        remaining_amount=remaining,
        percent_used=percent_used,
        warning_threshold_percent=budget.warning_threshold_percent,
        is_warning=percent_used >= budget.warning_threshold_percent and percent_used < 100,
        is_over=percent_used >= 100,
    )


@dataclass
class BudgetPlan:
    monthly_income: Decimal
    monthly_recurring_expenses: Decimal
    monthly_goal_target: Decimal
    suggested_monthly_savings: Decimal
    leftover_after_plan: Decimal
    assumptions: list[str] = field(default_factory=list)


def build_budget_plan(user, goal_monthly_contribution_target: Decimal | None = None) -> BudgetPlan:
    """A deliberately simple, explainable budget plan.

    It is a planning estimate, not a guarantee or professional financial
    advice: it normalizes each income source and recurring expense to a
    monthly figure, then suggests how much is left for savings goals.
    """
    assumptions = [
        "Weekly amounts are treated as 4.33 occurrences per month and "
        "biweekly as 2.17, since months don't divide evenly into weeks.",
        "Only income sources and recurring expenses marked active are included.",
        "This is an estimate for planning purposes, not guaranteed "
        "financial advice, and does not account for one-off spending.",
    ]

    income_total = Decimal("0")
    for src in user.income_sources.filter(is_active=True):
        income_total += monthly_equivalent(src.amount, src.cadence)

    expense_total = Decimal("0")
    for exp in user.recurring_expenses.filter(is_active=True):
        expense_total += monthly_equivalent(exp.amount, exp.cadence)

    income_total = quantize_money(income_total)
    expense_total = quantize_money(expense_total)

    goal_target = quantize_money(goal_monthly_contribution_target or Decimal("0"))
    leftover = quantize_money(income_total - expense_total - goal_target)

    return BudgetPlan(
        monthly_income=income_total,
        monthly_recurring_expenses=expense_total,
        monthly_goal_target=goal_target,
        suggested_monthly_savings=goal_target,
        leftover_after_plan=leftover,
        assumptions=assumptions,
    )


@dataclass
class CategoryTotal:
    category_name: str
    color: str
    total: Decimal


@dataclass
class MonthlySummary:
    """Actual-transaction-derived summary for one calendar month.

    Distinct from BudgetPlan (which is a forward-looking estimate built
    from user-declared IncomeSource/RecurringExpense rows): this reads
    real recorded transactions for the month and is what a bank-statement
    import should populate. Earned income and transfers/reimbursements are
    kept separate per-field — never summed into one "income" number —
    because a Venmo reimbursement is not a raise.
    """

    year: int
    month: int
    earned_income: Decimal
    transfer_income: Decimal
    expense_by_category: list[CategoryTotal]
    total_expenses: Decimal
    net_cash_flow: Decimal


def monthly_summary(user, year: int, month: int, account=None) -> MonthlySummary:
    qs = Transaction.objects.filter(user=user, occurred_on__year=year, occurred_on__month=month)
    if account is not None:
        qs = qs.filter(account=account)

    earned_income = Decimal("0.00")
    transfer_income = Decimal("0.00")
    for txn in qs.filter(kind=Transaction.Kind.INCOME).select_related("category"):
        if txn.category and not txn.category.is_earned_income:
            transfer_income += txn.amount
        else:
            earned_income += txn.amount

    expense_rows = (
        qs.filter(kind=Transaction.Kind.EXPENSE)
        .values("category__name", "category__color")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    expense_by_category = [
        CategoryTotal(
            category_name=row["category__name"] or "Uncategorized",
            color=row["category__color"] or "#94a3b8",
            total=quantize_money(row["total"]),
        )
        for row in expense_rows
    ]
    total_expenses = quantize_money(sum((r.total for r in expense_by_category), Decimal("0.00")))

    earned_income = quantize_money(earned_income)
    transfer_income = quantize_money(transfer_income)
    net_cash_flow = quantize_money(earned_income + transfer_income - total_expenses)

    return MonthlySummary(
        year=year,
        month=month,
        earned_income=earned_income,
        transfer_income=transfer_income,
        expense_by_category=expense_by_category,
        total_expenses=total_expenses,
        net_cash_flow=net_cash_flow,
    )

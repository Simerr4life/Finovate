from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from budgets.models import Budget, BudgetPeriod, RecurringExpense
from budgets.services import build_budget_plan, compute_budget_progress
from core.display import (
    RANGE_MONTHS,
    cash_series,
    category_totals,
    conic_style,
    flow_between,
    greeting_for,
    line_chart,
    month_start,
    monthly_bars,
)
from investing.models import PortfolioSnapshot, RoundUpLedgerEntry
from investing.services import compute_investable_surplus
from savings.models import Goal
from transactions.models import Transaction


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "core/landing.html")


@login_required
def dashboard(request):
    user = request.user
    if not user.profile.onboarding_completed:
        return redirect("accounts:onboarding")

    today = timezone.now().date()
    month_begin = month_start(today)

    income_total = Transaction.objects.filter(
        user=user, kind=Transaction.Kind.INCOME
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    expense_total = Transaction.objects.filter(
        user=user, kind=Transaction.Kind.EXPENSE
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    cash_balance = income_total - expense_total
    month_income, month_expense = flow_between(user, month_begin, today)

    recent_transactions = Transaction.objects.filter(user=user).select_related("category", "account")[:5]

    active_period = BudgetPeriod.objects.filter(user=user, is_active=True).first()
    budget_progress = []
    if active_period:
        for budget in Budget.objects.filter(period=active_period).select_related("category"):
            budget_progress.append(compute_budget_progress(budget))

    goals = Goal.objects.filter(user=user)[:4]

    pending_roundups_total = RoundUpLedgerEntry.objects.filter(
        user=user, status=RoundUpLedgerEntry.Status.PENDING
    ).aggregate(total=Sum("round_up_amount"))["total"] or Decimal("0")

    latest_snapshot = PortfolioSnapshot.objects.filter(user=user).order_by("-as_of").first()

    range_key = request.GET.get("range", "6M")
    if range_key not in RANGE_MONTHS:
        range_key = "6M"
    labels, points = cash_series(user, range_key)
    chart = line_chart(points, labels)
    surplus = compute_investable_surplus(user)
    plan = build_budget_plan(user)
    budget_remaining = sum((row.remaining_amount for row in budget_progress if row.remaining_amount > 0), Decimal("0"))
    income_vs_plan = None
    if plan.monthly_income > 0:
        income_vs_plan = int((month_income / plan.monthly_income) * 100)
    recurring_count = RecurringExpense.objects.filter(user=user, is_active=True).count()
    recurring_total = plan.monthly_recurring_expenses

    context = {
        "today": today,
        "greeting": greeting_for(),
        "cash_balance": cash_balance,
        "income_total": income_total,
        "expense_total": expense_total,
        "month_income": month_income,
        "month_expense": month_expense,
        "income_vs_plan": income_vs_plan,
        "budget_remaining": budget_remaining,
        "recent_transactions": recent_transactions,
        "budget_progress": budget_progress,
        "goals": goals,
        "pending_roundups_total": pending_roundups_total,
        "latest_snapshot": latest_snapshot,
        "has_demo_data": Transaction.objects.filter(user=user, is_demo=True).exists(),
        "chart": chart,
        "range_key": range_key,
        "ranges": ["1W", "1M", "3M", "6M", "1Y"],
        "surplus": surplus,
        "recurring_count": recurring_count,
        "recurring_total": recurring_total,
        "has_transactions": Transaction.objects.filter(user=user).exists(),
    }
    return render(request, "core/dashboard.html", context)


@login_required
def insights(request):
    user = request.user
    if not user.profile.onboarding_completed:
        return redirect("accounts:onboarding")
    today = timezone.now().date()
    month_begin = month_start(today)
    prior_end = month_begin - timedelta(days=1)
    prior_begin = month_start(prior_end)
    month_income, month_expense = flow_between(user, month_begin, today)
    prior_income, prior_expense = flow_between(user, prior_begin, prior_end)
    bars = monthly_bars(user, 6, today)
    categories, category_total = category_totals(user, month_begin, today)
    prior_categories, _ = category_totals(user, prior_begin, prior_end)
    prior_map = {item["name"]: item["total"] for item in prior_categories}
    changes = []
    for item in categories:
        delta = item["total"] - prior_map.get(item["name"], Decimal("0"))
        if delta != 0:
            changes.append({"name": item["name"], "delta": delta})
    changes.sort(key=lambda row: row["delta"])
    income_months = [bar for bar in bars if bar["income"] > 0]
    expense_months = [bar for bar in bars if bar["expense"] > 0]
    avg_income = (
        sum((bar["income"] for bar in income_months), Decimal("0")) / len(income_months)
        if income_months
        else Decimal("0")
    )
    avg_expense = (
        sum((bar["expense"] for bar in expense_months), Decimal("0")) / len(expense_months)
        if expense_months
        else Decimal("0")
    )
    savings_rate = None
    if month_income > 0:
        savings_rate = int(((month_income - month_expense) / month_income) * 100)
    return render(
        request,
        "core/insights.html",
        {
            "month_income": month_income,
            "month_expense": month_expense,
            "prior_income": prior_income,
            "prior_expense": prior_expense,
            "bars": bars,
            "categories": categories[:4],
            "category_total": category_total,
            "donut_style": conic_style(categories[:4]),
            "decreased": changes[0] if changes and changes[0]["delta"] < 0 else None,
            "increased": changes[-1] if changes and changes[-1]["delta"] > 0 else None,
            "avg_income": avg_income,
            "avg_expense": avg_expense,
            "savings_rate": savings_rate,
            "recurring": RecurringExpense.objects.filter(user=user, is_active=True).order_by("name")[:4],
            "has_transactions": Transaction.objects.filter(user=user).exists(),
        },
    )

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from budgets.models import Budget, BudgetPeriod
from budgets.services import compute_budget_progress
from investing.models import PortfolioSnapshot, RoundUpLedgerEntry
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

    income_total = Transaction.objects.filter(
        user=user, kind=Transaction.Kind.INCOME
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    expense_total = Transaction.objects.filter(
        user=user, kind=Transaction.Kind.EXPENSE
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    cash_balance = income_total - expense_total

    recent_transactions = Transaction.objects.filter(user=user).select_related("category")[:8]

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

    category_spending = (
        Transaction.objects.filter(user=user, kind=Transaction.Kind.EXPENSE, category__isnull=False)
        .values("category__name", "category__color")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:6]
    )

    context = {
        "today": today,
        "cash_balance": cash_balance,
        "income_total": income_total,
        "expense_total": expense_total,
        "recent_transactions": recent_transactions,
        "budget_progress": budget_progress,
        "goals": goals,
        "pending_roundups_total": pending_roundups_total,
        "latest_snapshot": latest_snapshot,
        "category_spending": list(category_spending),
        "has_demo_data": Transaction.objects.filter(user=user, is_demo=True).exists(),
    }
    return render(request, "core/dashboard.html", context)

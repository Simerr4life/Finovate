from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from savings.models import Goal
from transactions.models import Category, Transaction

from .forms import (
    BudgetForm,
    BudgetPeriodForm,
    CategoryForm,
    IncomeSourceForm,
    RecurringExpenseForm,
    TransactionForm,
)
from .models import Budget, BudgetPeriod, IncomeSource, RecurringExpense
from .services import build_budget_plan, compute_budget_progress


@login_required
def index(request):
    user = request.user
    periods = BudgetPeriod.objects.filter(user=user)
    active_period = periods.filter(is_active=True).first()

    budgets = []
    if active_period:
        budgets = [
            compute_budget_progress(b)
            for b in Budget.objects.filter(period=active_period).select_related("category")
        ]

    goal_monthly_target = Decimal("0")
    active_goals = Goal.objects.filter(user=user, achieved_at__isnull=True)
    for g in active_goals:
        goal_monthly_target += max(g.remaining_amount / Decimal("12"), Decimal("0"))

    plan = build_budget_plan(user, goal_monthly_target)

    context = {
        "periods": periods,
        "active_period": active_period,
        "budgets": budgets,
        "plan": plan,
        "income_sources": IncomeSource.objects.filter(user=user),
        "recurring_expenses": RecurringExpense.objects.filter(user=user).select_related("category"),
        "categories": Category.objects.filter(user=user),
        "period_form": BudgetPeriodForm(),
        "budget_form": BudgetForm(user=user),
        "category_form": CategoryForm(),
        "income_form": IncomeSourceForm(),
        "expense_form": RecurringExpenseForm(user=user),
    }
    return render(request, "budgets/index.html", context)


@login_required
def transaction_list(request):
    transactions = Transaction.objects.filter(user=request.user).select_related("category")
    return render(request, "budgets/transaction_list.html", {"transactions": transactions})


@login_required
def transaction_add(request):
    if request.method == "POST":
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            txn = form.save(commit=False)
            txn.user = request.user
            txn.source = "manual"
            txn.save()
            messages.success(request, "Transaction added.")
            return redirect("budgets:transaction_list")
    else:
        form = TransactionForm(user=request.user)
    return render(request, "budgets/transaction_form.html", {"form": form, "mode": "add"})


@login_required
def transaction_edit(request, pk):
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == "POST":
        form = TransactionForm(request.POST, instance=txn, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Transaction updated.")
            return redirect("budgets:transaction_list")
    else:
        form = TransactionForm(instance=txn, user=request.user)
    return render(request, "budgets/transaction_form.html", {"form": form, "mode": "edit"})


@login_required
def transaction_delete(request, pk):
    txn = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == "POST":
        txn.delete()
        messages.success(request, "Transaction deleted.")
        return redirect("budgets:transaction_list")
    return render(request, "confirm_delete.html", {"object": txn, "cancel_url": "budgets:transaction_list"})


@login_required
def category_add(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.user = request.user
            cat.save()
            messages.success(request, "Category created.")
    return redirect("budgets:index")


@login_required
def category_delete(request, pk):
    cat = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == "POST":
        cat.delete()
        messages.success(request, "Category deleted.")
    return redirect("budgets:index")


@login_required
def period_add(request):
    if request.method == "POST":
        form = BudgetPeriodForm(request.POST)
        if form.is_valid():
            period = form.save(commit=False)
            period.user = request.user
            if period.is_active:
                BudgetPeriod.objects.filter(user=request.user, is_active=True).update(is_active=False)
            period.save()
            messages.success(request, "Budget period created.")
    return redirect("budgets:index")


@login_required
def budget_add(request):
    if request.method == "POST":
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            budget.save()
            messages.success(request, "Budget added.")
        else:
            messages.error(request, "Could not add budget — check the form.")
    return redirect("budgets:index")


@login_required
def budget_delete(request, pk):
    budget = get_object_or_404(Budget, pk=pk, user=request.user)
    if request.method == "POST":
        budget.delete()
        messages.success(request, "Budget removed.")
    return redirect("budgets:index")


@login_required
def income_add(request):
    if request.method == "POST":
        form = IncomeSourceForm(request.POST)
        if form.is_valid():
            src = form.save(commit=False)
            src.user = request.user
            src.save()
            messages.success(request, "Income source added — plan recalculated.")
    return redirect("budgets:index")


@login_required
def income_delete(request, pk):
    src = get_object_or_404(IncomeSource, pk=pk, user=request.user)
    if request.method == "POST":
        src.delete()
        messages.success(request, "Income source removed — plan recalculated.")
    return redirect("budgets:index")


@login_required
def expense_add(request):
    if request.method == "POST":
        form = RecurringExpenseForm(request.POST, user=request.user)
        if form.is_valid():
            exp = form.save(commit=False)
            exp.user = request.user
            exp.save()
            messages.success(request, "Recurring expense added — plan recalculated.")
    return redirect("budgets:index")


@login_required
def expense_delete(request, pk):
    exp = get_object_or_404(RecurringExpense, pk=pk, user=request.user)
    if request.method == "POST":
        exp.delete()
        messages.success(request, "Recurring expense removed — plan recalculated.")
    return redirect("budgets:index")

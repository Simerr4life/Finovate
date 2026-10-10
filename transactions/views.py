from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from budgets.services import monthly_summary

from .models import Account
from .services import compute_running_balances, reconcile_account


@login_required
def statement_list(request):
    accounts = Account.objects.filter(user=request.user)
    return render(request, "transactions/statement_list.html", {"accounts": accounts})


@login_required
def statement_detail(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    ledger_rows = compute_running_balances(account)
    report = reconcile_account(account)
    summary = None
    if account.statement_start_date:
        summary = monthly_summary(
            request.user, account.statement_start_date.year, account.statement_start_date.month, account=account
        )
    return render(
        request,
        "transactions/statement_detail.html",
        {"account": account, "ledger_rows": ledger_rows, "report": report, "summary": summary},
    )

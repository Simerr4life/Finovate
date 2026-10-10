from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import NotificationEvent

from .forms import HypotheticalScenarioForm, RoundUpSettingsForm, VerifiedScenarioForm
from .models import MarketPrice, PortfolioSnapshot, RoundUpLedgerEntry, SimulatedOrder
from .services import (
    approve_order,
    compute_hypothetical_scenario,
    compute_investable_surplus,
    get_or_create_settings,
    investable_pools,
    pool_investment_summaries,
    propose_surplus_investment,
    reject_order,
    sweep_pending_roundups,
)


@login_required
def index(request):
    rs = get_or_create_settings(request.user)
    if request.method == "POST" and "save_settings" in request.POST:
        form = RoundUpSettingsForm(request.POST, instance=rs, user=request.user)
        if form.is_valid():
            was_paused = rs.is_paused
            form.save()
            if form.instance.is_paused and not was_paused and request.user.profile.notify_budget_warnings:
                NotificationEvent.objects.create(
                    user=request.user,
                    event_type=NotificationEvent.EventType.ROUNDUP_PAUSED,
                    message="Round-up investing was paused.",
                )
            messages.success(request, "Round-up settings saved.")
            return redirect("investing:index")
    else:
        form = RoundUpSettingsForm(instance=rs, user=request.user)

    pending_entries = RoundUpLedgerEntry.objects.filter(
        user=request.user, status=RoundUpLedgerEntry.Status.PENDING
    ).select_related("source_transaction")
    recent_entries = RoundUpLedgerEntry.objects.filter(user=request.user).select_related(
        "source_transaction"
    )[:15]
    all_snapshots = PortfolioSnapshot.objects.filter(user=request.user, pool__isnull=True)
    snapshots = all_snapshots[:12]

    all_orders = SimulatedOrder.objects.filter(
        user=request.user
    ).order_by("-created_at")

    pending_orders = all_orders.filter(
        status=SimulatedOrder.Status.PENDING
    )

    orders = all_orders[:10]

    latest_snapshot = all_snapshots.first()
    surplus = compute_investable_surplus(request.user)
    pools = investable_pools(request.user)
    pool_summaries = pool_investment_summaries(request.user)

    context = {
        "form": form,
        "roundup_settings": rs,
        "pending_entries": pending_entries,
        "pending_total": sum((e.round_up_amount for e in pending_entries), start=0),
        "recent_entries": recent_entries,
        "snapshots": snapshots,
        "orders": orders,
        "pending_orders": pending_orders,
        "latest_snapshot": latest_snapshot,
        "surplus": surplus,
        "investable_pools": pools,
        "pool_summaries": pool_summaries,
    }
    return render(request, "investing/index.html", context)


@login_required
def propose_surplus(request):
    if request.method == "POST":
        surplus = compute_investable_surplus(request.user)
        try:
            requested = Decimal(request.POST.get("amount", "0"))
        except InvalidOperation:
            requested = Decimal("0")
        amount = min(requested, surplus.investable_surplus) if requested > 0 else Decimal("0")
        pool = None
        pool_id = request.POST.get("pool")
        if pool_id:
            pool = get_object_or_404(investable_pools(request.user), pk=pool_id)
        if amount > 0:
            propose_surplus_investment(request.user, amount, pool=pool)
            target = f'"{pool.name}"' if pool else "the general bucket"
            messages.success(request, f"Proposed investing ${amount} into {target} — pending your approval below.")
        else:
            messages.info(request, "No investable surplus available to propose right now.")
    return redirect("investing:index")


@login_required
def approve_order_view(request, pk):
    order = get_object_or_404(SimulatedOrder, pk=pk, user=request.user, status=SimulatedOrder.Status.PENDING)
    if request.method == "POST":
        approve_order(order)
        messages.success(request, f"Approved: simulated purchase of ${order.amount} recorded.")
    return redirect("investing:index")


@login_required
def reject_order_view(request, pk):
    order = get_object_or_404(SimulatedOrder, pk=pk, user=request.user, status=SimulatedOrder.Status.PENDING)
    if request.method == "POST":
        reject_order(order)
        messages.info(request, "Proposed investment rejected.")
    return redirect("investing:index")


@login_required
def historical_demo(request):
    """Illustrative 'what if' calculator, in two flavors:

    - verified_form: prices come from source-cited MarketPrice rows (see
      the Market Data page) — real sourced prices, still a hypothetical
      scenario since no purchase actually happened.
    - form (manual): prices are typed in by the user for any
      symbol/date Finovate has no verified data for.
    """
    scenario = None
    verified_form = VerifiedScenarioForm()
    form = HypotheticalScenarioForm()

    if request.method == "POST" and request.POST.get("mode") == "verified":
        verified_form = VerifiedScenarioForm(request.POST)
        if verified_form.is_valid():
            invest_row = verified_form.cleaned_data["invest_row"]
            valuation_row = verified_form.cleaned_data["valuation_row"]
            scenario = compute_hypothetical_scenario(
                symbol=invest_row.symbol,
                invest_date=invest_row.date,
                invest_price=invest_row.close,
                valuation_date=valuation_row.date,
                valuation_price=valuation_row.close,
                amount_invested=verified_form.cleaned_data["amount_invested"],
            )
            scenario_source = f"{invest_row.source_note} / {valuation_row.source_note}"
            return render(request, "investing/historical_demo.html", {
                "form": form, "verified_form": verified_form, "scenario": scenario, "scenario_source": scenario_source,
            })
    elif request.method == "POST":
        form = HypotheticalScenarioForm(request.POST)
        if form.is_valid():
            scenario = compute_hypothetical_scenario(
                symbol=form.cleaned_data["symbol"],
                invest_date=form.cleaned_data["invest_date"],
                invest_price=form.cleaned_data["invest_price"],
                valuation_date=form.cleaned_data["valuation_date"],
                valuation_price=form.cleaned_data["valuation_price"],
                amount_invested=form.cleaned_data["amount_invested"],
            )
            return render(request, "investing/historical_demo.html", {
                "form": form, "verified_form": verified_form, "scenario": scenario, "scenario_source": "user-supplied (unverified)",
            })

    return render(request, "investing/historical_demo.html", {"form": form, "verified_form": verified_form, "scenario": None})


@login_required
def market_data(request):
    rows = MarketPrice.objects.all()
    by_symbol = {}
    for row in rows:
        by_symbol.setdefault(row.symbol, []).append(row)
    return render(request, "investing/market_data.html", {"by_symbol": by_symbol})


@login_required
def sweep_now(request):
    """Manually trigger a simulated sweep of pending round-ups.

    Stands in for what a real, authorized funding provider would do on a
    schedule. No real money moves — this only updates simulated rows.
    """
    if request.method == "POST":
        result = sweep_pending_roundups(request.user)
        if result["entries_swept"]:
            messages.success(
                request,
                f"Simulated sweep: ${result['swept_amount']} across {result['entries_swept']} round-up(s).",
            )
        else:
            messages.info(request, f"Nothing swept: {result['reason']}.")
    return redirect("investing:index")

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from accounts.models import NotificationEvent

from .forms import HypotheticalScenarioForm, RoundUpSettingsForm, VerifiedScenarioForm
from .models import (
    DemoInvestmentSuggestion,
    MarketPrice,
    PortfolioSnapshot,
    RoundUpLedgerEntry,
    SimulatedOrder,
)
from .services import (
    accept_demo_investment_suggestion,
    available_demo_investment_budget,
    approve_order,
    compute_hypothetical_scenario,
    compute_investable_surplus,
    create_demo_market_order,
    decline_demo_investment_suggestion,
    generate_demo_investment_suggestions,
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
    demo_suggestions = DemoInvestmentSuggestion.objects.filter(
        user=request.user, status=DemoInvestmentSuggestion.Status.PENDING
    ).select_related("simulated_order")[:3]
    has_demo_market_data = MarketPrice.objects.filter(
        asset_type=MarketPrice.AssetType.STOCK,
        is_verified=True,
        is_demo_sample=True,
    ).exists()
    market_rows = []
    for row in MarketPrice.objects.filter(
        is_verified=True,
        is_demo_sample=True,
    ).order_by("symbol", "-date"):
        if not any(existing["symbol"] == row.symbol for existing in market_rows):
            market_rows.append(
                {
                    "symbol": row.symbol,
                    "asset_name": row.asset_name or row.symbol,
                    "asset_type": row.get_asset_type_display(),
                    "date": row.date,
                    "close": row.close,
                    "source_note": row.source_note,
                }
            )

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
        "market_rows": market_rows,
        "demo_suggestions": demo_suggestions,
        "reviewed_demo_suggestions": DemoInvestmentSuggestion.objects.filter(
            user=request.user
        ).exclude(status=DemoInvestmentSuggestion.Status.PENDING).select_related(
            "simulated_order"
        )[:5],
        "has_demo_market_data": has_demo_market_data,
        "tab": request.GET.get("tab", "portfolio"),
    }
    return render(request, "investing/index.html", context)


@login_required
@require_POST
def generate_demo_suggestions_view(request):
    if not MarketPrice.objects.filter(
        asset_type=MarketPrice.AssetType.STOCK,
        is_verified=True,
        is_demo_sample=True,
    ).exists():
        messages.info(
            request,
            "Load the supplied sample prices first with "
            "`python manage.py seed_excel_demo_market`.",
        )
    else:
        suggestions = generate_demo_investment_suggestions(request.user)
        pending_count = sum(
            suggestion.status == DemoInvestmentSuggestion.Status.PENDING
            for suggestion in suggestions
        )
        if pending_count:
            messages.success(
                request,
                f"{pending_count} demo recommendation(s) are ready for your review. "
                "Nothing has been invested.",
            )
        elif not available_demo_investment_budget(request.user):
            messages.info(
                request,
                "No recommendations generated because your current estimated "
                "investable surplus is $0.00.",
            )
        elif suggestions:
            messages.info(
                request,
                "You have already reviewed recommendations for this sample-data snapshot.",
            )
        else:
            messages.info(
                request,
                "The supplied sample does not contain enough dated stock prices "
                "to generate demo recommendations.",
            )
    return redirect("investing:index")


@login_required
@require_POST
def accept_demo_suggestion_view(request, pk):
    suggestion = get_object_or_404(
        DemoInvestmentSuggestion,
        pk=pk,
        user=request.user,
        status=DemoInvestmentSuggestion.Status.PENDING,
    )
    pool = None
    pool_id = request.POST.get("pool")
    if pool_id:
        pool = get_object_or_404(investable_pools(request.user), pk=pool_id)
    try:
        order = accept_demo_investment_suggestion(request.user, suggestion, pool)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Accepted {order.symbol} as a simulated pending order. "
            "Review and approve it below to record it in your demo portfolio.",
        )
    return redirect("investing:index")


@login_required
@require_POST
def decline_demo_suggestion_view(request, pk):
    suggestion = get_object_or_404(
        DemoInvestmentSuggestion,
        pk=pk,
        user=request.user,
        status=DemoInvestmentSuggestion.Status.PENDING,
    )
    decline_demo_investment_suggestion(request.user, suggestion)
    messages.info(request, "Demo recommendation declined. No order was created.")
    return redirect("investing:index")


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
        next_url = request.POST.get("next", "")
        if next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
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
    rows = MarketPrice.objects.filter(
        is_verified=True,
        is_demo_sample=True,
    ).order_by("symbol", "date")
    grouped_rows = {}
    for row in rows:
        grouped_rows.setdefault(row.symbol, []).append(row)

    stock_assets = []
    index_assets = []
    for symbol, history in grouped_rows.items():
        first_price, latest_price = history[0], history[-1]
        period_change = Decimal("0.00")
        if first_price.close:
            period_change = (
                (latest_price.close - first_price.close)
                / first_price.close
                * Decimal("100")
            ).quantize(Decimal("0.01"))
        asset = {
            "symbol": symbol,
            "name": latest_price.asset_name or symbol,
            "asset_type": latest_price.asset_type,
            "asset_type_label": latest_price.get_asset_type_display(),
            "latest": latest_price,
            "history": list(reversed(history)),
            "period_change": period_change,
            "anchor": slugify(symbol),
            "chart_id": f"market-series-{slugify(symbol)}",
            "first_date": history[0].date,
            "chart_data": [
                {"date": price.date.isoformat(), "close": str(price.close)}
                for price in history
            ],
        }
        if latest_price.asset_type == MarketPrice.AssetType.STOCK:
            stock_assets.append(asset)
        else:
            index_assets.append(asset)

    return render(
        request,
        "investing/market_data.html",
        {
            "stock_assets": stock_assets,
            "index_assets": index_assets,
            "demo_budget": available_demo_investment_budget(request.user),
            "investable_pools": investable_pools(request.user),
        },
    )


@login_required
@require_POST
def buy_demo_market_asset(request):
    symbol = request.POST.get("symbol", "").strip()
    try:
        amount = Decimal(request.POST.get("amount", ""))
    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Enter a valid amount to simulate.")
        return redirect("investing:market_data")

    if not amount.is_finite() or amount <= 0:
        messages.error(request, "Enter an amount greater than $0.00 with up to two decimal places.")
        return redirect("investing:market_data")
    try:
        rounded_amount = amount.quantize(Decimal("0.01"))
    except InvalidOperation:
        rounded_amount = None
    if rounded_amount is None or amount != rounded_amount or amount > Decimal("9999999999.99"):
        messages.error(request, "Enter an amount greater than $0.00 with up to two decimal places.")
        return redirect("investing:market_data")

    pool = None
    pool_id = request.POST.get("pool", "").strip()
    if pool_id:
        pool = get_object_or_404(investable_pools(request.user), pk=pool_id)

    try:
        order = create_demo_market_order(request.user, symbol, amount, pool)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("investing:market_data")

    target = f'"{pool.name}"' if pool else "the general bucket"
    messages.success(
        request,
        f"Created a simulated {order.symbol} buy order for ${order.amount} in {target}. "
        "Review and approve it on Investments to add it to your demo portfolio.",
    )
    return redirect(f"{reverse('investing:market_data')}#asset-{slugify(symbol)}")


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

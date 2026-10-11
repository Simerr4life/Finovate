from collections import defaultdict
from datetime import time
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.models import NotificationEvent

from .forms import HypotheticalScenarioForm, RoundUpSettingsForm, VerifiedScenarioForm
from .live_quotes import (
    MARKET_STOCKS,
    refresh_live_market_quotes,
    refresh_twelve_data_history,
)
from .models import (
    DemoInvestmentSuggestion,
    DemoInvestmentFunding,
    MarketPrice,
    PortfolioSnapshot,
    RoundUpLedgerEntry,
    SimulatedOrder,
)
from .services import (
    accept_demo_investment_suggestion,
    add_demo_investment_funds,
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


def _demo_market_assets():
    rows = MarketPrice.objects.filter(
        is_verified=True,
        is_twelve_data=True,
    ).order_by("symbol", "date")
    grouped_rows = defaultdict(list)
    for row in rows:
        grouped_rows[row.symbol].append(row)

    assets = []
    for symbol, history in grouped_rows.items():
        first_price, latest_price = history[0], history[-1]
        period_change = Decimal("0.00")
        if first_price.close:
            period_change = (
                (latest_price.close - first_price.close)
                / first_price.close
                * Decimal("100")
            ).quantize(Decimal("0.01"))
        assets.append({
            "symbol": symbol,
            "name": latest_price.asset_name or symbol,
            "asset_type": latest_price.asset_type,
            "asset_type_label": latest_price.get_asset_type_display(),
            "latest": latest_price,
            "history": list(reversed(history)),
            "period_change": period_change,
            "anchor": slugify(symbol),
            "chart_id": f"market-series-{slugify(symbol)}",
            "first_date": first_price.date,
            "chart_data": [
                {"date": price.date.isoformat(), "close": str(price.close)}
                for price in history
            ],
        })
    return assets


def _user_demo_holdings(user):
    orders = list(
        SimulatedOrder.objects.filter(
            user=user,
            status=SimulatedOrder.Status.FILLED,
            demo_shares__isnull=False,
            demo_data_date__isnull=False,
            demo_price_source=SimulatedOrder.PriceSource.TWELVE_DATA,
        ).order_by("demo_data_date", "created_at")
    )
    orders_by_symbol = defaultdict(list)
    for order in orders:
        orders_by_symbol[order.symbol].append(order)

    holdings = []
    series_by_symbol = {}
    for symbol, symbol_orders in orders_by_symbol.items():
        history = list(
            MarketPrice.objects.filter(
                symbol=symbol,
                is_verified=True,
                is_twelve_data=True,
            ).order_by("date")
        )
        if not history:
            continue

        shares = Decimal("0")
        cost_basis = Decimal("0")
        series = []
        order_index = 0
        for price in history:
            while (
                order_index < len(symbol_orders)
                and symbol_orders[order_index].demo_data_date <= price.date
            ):
                order = symbol_orders[order_index]
                order_index += 1
                order_shares = order.demo_shares or Decimal("0")
                if order.order_type == SimulatedOrder.OrderType.BUY:
                    shares += order_shares
                    cost_basis += order.amount
                elif order.order_type == SimulatedOrder.OrderType.SELL and shares > 0:
                    sold_shares = min(shares, order_shares)
                    cost_basis -= cost_basis * sold_shares / shares
                    shares -= sold_shares

            series.append({
                "date": price.date.isoformat(),
                "close": str(shares * price.close),
            })

        series_by_symbol[symbol] = series
        if shares <= 0:
            continue

        latest_price = history[-1]
        market_value = shares * latest_price.close
        holdings.append({
            "symbol": symbol,
            "name": latest_price.asset_name or symbol,
            "shares": shares,
            "cost_basis": cost_basis,
            "latest_price": latest_price.close,
            "price_date": latest_price.date,
            "market_value": market_value,
            "gain_loss": market_value - cost_basis,
            "chart_id": f"holding-series-{slugify(symbol)}",
            "chart_data": series,
        })

    holdings.sort(key=lambda holding: holding["market_value"], reverse=True)
    date_series = defaultdict(dict)
    all_dates = sorted({
        point["date"]
        for series in series_by_symbol.values()
        for point in series
    })
    for symbol, series in series_by_symbol.items():
        for point in series:
            date_series[symbol][point["date"]] = Decimal(point["close"])

    portfolio_series = []
    latest_values = {}
    for sample_date in all_dates:
        total_value = Decimal("0")
        for symbol, points in date_series.items():
            if sample_date in points:
                latest_values[symbol] = points[sample_date]
            total_value += latest_values.get(symbol, Decimal("0"))
        portfolio_series.append({
            "date": sample_date,
            "close": str(total_value),
        })

    filled_unpriced_total = (
        SimulatedOrder.objects.filter(
            user=user,
            status=SimulatedOrder.Status.FILLED,
            order_type=SimulatedOrder.OrderType.BUY,
        ).filter(
            Q(demo_shares__isnull=True)
            | ~Q(demo_price_source=SimulatedOrder.PriceSource.TWELVE_DATA)
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    return {
        "holdings": holdings,
        "portfolio_series": portfolio_series,
        "holdings_cost_basis": sum(
            (holding["cost_basis"] for holding in holdings), Decimal("0")
        ),
        "holdings_market_value": sum(
            (holding["market_value"] for holding in holdings), Decimal("0")
        ),
        "holdings_gain_loss": sum(
            (holding["gain_loss"] for holding in holdings), Decimal("0")
        ),
        "unpriced_filled_total": filled_unpriced_total,
        "pending_market_orders": SimulatedOrder.objects.filter(
            user=user,
            status=SimulatedOrder.Status.PENDING,
            order_type=SimulatedOrder.OrderType.BUY,
            demo_shares__isnull=False,
        ).order_by("-created_at"),
    }


def _is_us_regular_session(now):
    market_time = now.astimezone(ZoneInfo("America/New_York"))
    return (
        market_time.weekday() < 5
        and time(9, 30) <= market_time.time().replace(tzinfo=None) < time(16)
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
        user=request.user,
        status=DemoInvestmentSuggestion.Status.PENDING,
        data_source=DemoInvestmentSuggestion.DataSource.TWELVE_DATA,
    ).select_related("simulated_order")[:3]
    tab = request.GET.get("tab", "portfolio")
    if tab not in {"portfolio", "explore", "holdings", "calculator"}:
        tab = "portfolio"
    if tab in {"portfolio", "explore"}:
        refresh_twelve_data_history()

    has_demo_market_data = MarketPrice.objects.filter(
        asset_type=MarketPrice.AssetType.STOCK,
        is_verified=True,
        is_twelve_data=True,
    ).exists()
    market_assets = _demo_market_assets()
    holdings = _user_demo_holdings(request.user)
    portfolio_chart_id = "simulated-portfolio-series"
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
        "demo_budget": available_demo_investment_budget(request.user),
        "demo_pool_funds": sum(
            (pool.current_amount for pool in pools), Decimal("0.00")
        ),
        "demo_funded_total": (
            DemoInvestmentFunding.objects.filter(user=request.user).aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        ),
        "demo_stock_count": MarketPrice.objects.filter(
            asset_type=MarketPrice.AssetType.STOCK,
            is_verified=True,
            is_twelve_data=True,
        ).values("symbol").distinct().count(),
        "market_assets": market_assets,
        "market_stocks": [
            asset for asset in market_assets
            if asset["asset_type"] == MarketPrice.AssetType.STOCK
        ],
        "market_indexes": [
            asset for asset in market_assets
            if asset["asset_type"] == MarketPrice.AssetType.INDEX
        ],
        "holdings": holdings["holdings"],
        "portfolio_series": holdings["portfolio_series"],
        "portfolio_chart_id": portfolio_chart_id,
        "holdings_cost_basis": holdings["holdings_cost_basis"],
        "holdings_market_value": holdings["holdings_market_value"],
        "holdings_gain_loss": holdings["holdings_gain_loss"],
        "portfolio_latest_date": (
            holdings["portfolio_series"][-1]["date"]
            if holdings["portfolio_series"]
            else None
        ),
        "unpriced_filled_total": holdings["unpriced_filled_total"],
        "pending_market_orders": holdings["pending_market_orders"],
        "demo_suggestions": demo_suggestions,
        "reviewed_demo_suggestions": DemoInvestmentSuggestion.objects.filter(
            user=request.user,
            data_source=DemoInvestmentSuggestion.DataSource.TWELVE_DATA,
        ).exclude(status=DemoInvestmentSuggestion.Status.PENDING).select_related(
            "simulated_order"
        )[:5],
        "has_demo_market_data": has_demo_market_data,
        "live_market_quotes_enabled": bool(settings.TWELVE_DATA_API_KEY),
        "tab": tab,
    }
    return render(request, "investing/index.html", context)


@login_required
@require_POST
def add_demo_investment_funds_view(request):
    try:
        amount = Decimal(request.POST.get("amount", ""))
    except (InvalidOperation, TypeError, ValueError):
        messages.error(request, "Enter a valid demo amount greater than $0.00.")
        return redirect("investing:index")

    try:
        add_demo_investment_funds(request.user, amount)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Added ${amount:.2f} in virtual demo funds. No real money was added or moved.",
        )
    return redirect("investing:index")


@login_required
@require_GET
@never_cache
def live_demo_quotes(request):
    holdings = _user_demo_holdings(request.user)["holdings"]
    symbols = [holding["symbol"] for holding in holdings]
    market_open = _is_us_regular_session(timezone.now())
    quotes, errors = refresh_live_market_quotes(symbols, allow_refresh=market_open)
    if errors.get("configuration") == "missing-api-key":
        return JsonResponse(
            {
                "error": "Live prices are not configured. Set TWELVE_DATA_API_KEY on the server.",
                "market_open": market_open,
            },
            status=503,
        )

    quote_data = {}
    portfolio_value = Decimal("0")
    for holding in holdings:
        quote = quotes.get(holding["symbol"])
        if quote is None:
            continue
        market_value = holding["shares"] * quote.price
        portfolio_value += market_value
        quote_data[holding["symbol"]] = {
            "price": str(quote.price),
            "market_value": str(market_value),
            "fetched_at": quote.fetched_at.isoformat(),
        }
    complete = len(quote_data) == len(holdings)
    return JsonResponse(
        {
            "quotes": quote_data,
            "portfolio_value": str(portfolio_value) if complete and holdings else None,
            "market_open": market_open,
            "errors": errors,
            "refresh_seconds": 300,
        }
    )


@login_required
@require_GET
@never_cache
def live_market_quotes(request):
    market_open = _is_us_regular_session(timezone.now())
    quotes, errors = refresh_live_market_quotes(
        MARKET_STOCKS,
        allow_refresh=market_open,
    )
    if errors.get("configuration") == "missing-api-key":
        return JsonResponse(
            {
                "error": "Live prices are not configured. Set TWELVE_DATA_API_KEY on the server.",
                "market_open": market_open,
            },
            status=503,
        )
    return JsonResponse(
        {
            "quotes": {
                symbol: {
                    "market_value": str(quote.price),
                    "fetched_at": quote.fetched_at.isoformat(),
                }
                for symbol, quote in quotes.items()
            },
            "market_open": market_open,
            "errors": errors,
            "refresh_seconds": 300,
        }
    )


@login_required
@require_POST
def generate_demo_suggestions_view(request):
    refresh_twelve_data_history()
    if not MarketPrice.objects.filter(
        asset_type=MarketPrice.AssetType.STOCK,
        is_verified=True,
        is_twelve_data=True,
    ).exists():
        messages.info(
            request,
            "Twelve Data history is not available yet. Check the server's "
            "TWELVE_DATA_API_KEY and provider access, then try again.",
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
                "You have already reviewed recommendations for this Twelve Data snapshot.",
            )
        else:
            messages.info(
                request,
                "Twelve Data history does not contain enough dated stock prices "
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
        data_source=DemoInvestmentSuggestion.DataSource.TWELVE_DATA,
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
        try:
            approve_order(order)
        except ValueError as error:
            messages.error(request, str(error))
        else:
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
    refresh_twelve_data_history()
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
    refresh_twelve_data_history()
    assets = _demo_market_assets()

    return render(
        request,
        "investing/market_data.html",
        {
            "stock_assets": [
                asset for asset in assets
                if asset["asset_type"] == MarketPrice.AssetType.STOCK
            ],
            "index_assets": [
                asset for asset in assets
                if asset["asset_type"] == MarketPrice.AssetType.INDEX
            ],
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

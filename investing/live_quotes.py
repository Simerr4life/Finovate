"""Shared, server-side Twelve Data quotes for simulated holdings."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import (
    LiveMarketQuote,
    MarketPrice,
    TwelveDataHistoryState,
    TwelveDataUsageWindow,
)

logger = logging.getLogger(__name__)

QUOTE_TTL = timedelta(minutes=5)
HISTORY_TTL = timedelta(hours=12)
FETCH_LEASE = timedelta(seconds=30)
HISTORY_RETRY_DELAY = timedelta(minutes=5)
MINUTE_CREDIT_LIMIT = 8
DAILY_CREDIT_LIMIT = 800
PROVIDER = "twelve-data"
MARKET_STOCKS = {
    "AAPL": "Apple Inc.",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
}


class TwelveDataQuoteError(Exception):
    """A safe-to-display failure without provider response or credential data."""


def _claim_api_credit(usage, now):
    minute_bucket = now.replace(second=0, microsecond=0)
    if usage.minute_bucket != minute_bucket:
        usage.minute_bucket = minute_bucket
        usage.minute_credits = 0
    if usage.usage_date != now.date():
        usage.usage_date = now.date()
        usage.daily_credits = 0
    if usage.minute_credits >= MINUTE_CREDIT_LIMIT:
        error = "minute-limit"
    elif usage.daily_credits >= DAILY_CREDIT_LIMIT:
        error = "daily-limit"
    else:
        usage.minute_credits += 1
        usage.daily_credits += 1
        error = None
    usage.save(
        update_fields=[
            "minute_bucket",
            "minute_credits",
            "usage_date",
            "daily_credits",
        ]
    )
    return error


def _claim_quote_refresh(symbol: str, now):
    minute_bucket = now.replace(second=0, microsecond=0)
    with transaction.atomic():
        usage, _ = TwelveDataUsageWindow.objects.get_or_create(
            provider=PROVIDER,
            defaults={
                "minute_bucket": minute_bucket,
                "usage_date": now.date(),
            },
        )
        usage = TwelveDataUsageWindow.objects.select_for_update().get(
            provider=PROVIDER
        )
        quote, _ = LiveMarketQuote.objects.get_or_create(symbol=symbol)
        quote = LiveMarketQuote.objects.select_for_update().get(pk=quote.pk)

        if quote.fetched_at and now - quote.fetched_at < QUOTE_TTL:
            return quote, False, None
        if quote.fetch_started_at and now - quote.fetch_started_at < FETCH_LEASE:
            return quote, False, None

        quota_error = _claim_api_credit(usage, now)
        if quota_error:
            return quote, False, quota_error
        quote.fetch_started_at = now
        quote.save(update_fields=["fetch_started_at"])
        return quote, True, None


def _fetch_twelve_data_price(symbol: str) -> Decimal:
    url = "https://api.twelvedata.com/price?" + urlencode(
        {"symbol": symbol, "apikey": settings.TWELVE_DATA_API_KEY}
    )
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
    except HTTPError as error:
        raise TwelveDataQuoteError(f"http-{error.code}") from None
    except (URLError, TimeoutError, OSError):
        raise TwelveDataQuoteError("network-error") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise TwelveDataQuoteError("invalid-response") from None

    if not isinstance(payload, dict) or "price" not in payload:
        raise TwelveDataQuoteError("provider-error")
    try:
        price = Decimal(payload["price"])
    except (InvalidOperation, TypeError, ValueError):
        raise TwelveDataQuoteError("invalid-price") from None
    if not price.is_finite() or price <= 0 or price >= Decimal("10000000000"):
        raise TwelveDataQuoteError("invalid-price")
    try:
        return price.quantize(Decimal("0.0001"))
    except InvalidOperation:
        raise TwelveDataQuoteError("invalid-price") from None


def _fetch_twelve_data_history(symbol: str):
    url = "https://api.twelvedata.com/time_series?" + urlencode(
        {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": "90",
            "apikey": settings.TWELVE_DATA_API_KEY,
        }
    )
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read())
    except HTTPError as error:
        raise TwelveDataQuoteError(f"http-{error.code}") from None
    except (URLError, TimeoutError, OSError):
        raise TwelveDataQuoteError("network-error") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise TwelveDataQuoteError("invalid-response") from None

    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, list) or not values:
        raise TwelveDataQuoteError("provider-error")

    parsed = []
    try:
        for value in values:
            day = date.fromisoformat(value["datetime"][:10])
            close = Decimal(value["close"])
            if not close.is_finite() or close <= 0:
                raise ValueError
            parsed.append(
                {
                    "date": day,
                    "open": _optional_decimal(value.get("open")),
                    "high": _optional_decimal(value.get("high")),
                    "low": _optional_decimal(value.get("low")),
                    "close": close.quantize(Decimal("0.0001")),
                    "volume": _optional_integer(value.get("volume")),
                }
            )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise TwelveDataQuoteError("invalid-history") from None

    parsed.sort(key=lambda row: row["date"])
    for index, row in enumerate(parsed):
        prior_close = parsed[index - 1]["close"] if index else None
        row["daily_change_percent"] = (
            (
                (row["close"] - prior_close)
                / prior_close
                * Decimal("100")
            ).quantize(Decimal("0.01"))
            if prior_close
            else None
        )
    return parsed


def _optional_decimal(value):
    if value in (None, ""):
        return None
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError
    return result.quantize(Decimal("0.0001"))


def _optional_integer(value):
    if value in (None, ""):
        return None
    result = int(value)
    if result < 0:
        raise ValueError
    return result


def _claim_history_refresh(symbol, now):
    with transaction.atomic():
        usage, _ = TwelveDataUsageWindow.objects.get_or_create(
            provider=PROVIDER,
            defaults={
                "minute_bucket": now.replace(second=0, microsecond=0),
                "usage_date": now.date(),
            },
        )
        usage = TwelveDataUsageWindow.objects.select_for_update().get(
            provider=PROVIDER
        )
        state, _ = TwelveDataHistoryState.objects.get_or_create(symbol=symbol)
        state = TwelveDataHistoryState.objects.select_for_update().get(
            symbol=symbol
        )
        if (
            state.refreshed_at
            and now - state.refreshed_at < HISTORY_TTL
            and MarketPrice.objects.filter(
                symbol=symbol,
                is_twelve_data=True,
            ).exists()
        ):
            return state, False, None
        if state.fetch_started_at and now - state.fetch_started_at < FETCH_LEASE:
            return state, False, None
        if state.retry_after and now < state.retry_after:
            return state, False, "provider-unavailable"

        quota_error = _claim_api_credit(usage, now)
        if quota_error:
            return state, False, quota_error
        state.fetch_started_at = now
        state.retry_after = None
        state.save(update_fields=["fetch_started_at", "retry_after"])
        return state, True, None


def _refresh_twelve_data_history_for_symbol(symbol):
    close_old_connections()
    try:
        now = timezone.now()
        _, should_fetch, error = _claim_history_refresh(symbol, now)
        if error:
            return symbol, False, error
        if not should_fetch:
            return symbol, True, None

        try:
            history = _fetch_twelve_data_history(symbol)
            with transaction.atomic():
                for row in history:
                    MarketPrice.objects.update_or_create(
                        symbol=symbol,
                        date=row["date"],
                        defaults={
                            "asset_name": MARKET_STOCKS[symbol],
                            "asset_type": MarketPrice.AssetType.STOCK,
                            "open": row["open"],
                            "high": row["high"],
                            "low": row["low"],
                            "close": row["close"],
                            "volume": row["volume"],
                            "daily_change_percent": row["daily_change_percent"],
                            "source_note": "Twelve Data API",
                            "is_verified": True,
                            "is_demo_sample": False,
                            "is_twelve_data": True,
                        },
                    )
                refreshed_at = timezone.now()
                TwelveDataHistoryState.objects.filter(pk=symbol).update(
                    refreshed_at=refreshed_at,
                    fetch_started_at=None,
                    retry_after=None,
                )
            return symbol, True, None
        except TwelveDataQuoteError as error:
            TwelveDataHistoryState.objects.filter(pk=symbol).update(
                fetch_started_at=None,
                retry_after=timezone.now() + HISTORY_RETRY_DELAY,
            )
            logger.warning(
                "Twelve Data history refresh failed symbol=%s reason=%s",
                symbol,
                str(error),
            )
            return symbol, False, "provider-unavailable"
        except Exception:
            TwelveDataHistoryState.objects.filter(pk=symbol).update(
                fetch_started_at=None,
                retry_after=timezone.now() + HISTORY_RETRY_DELAY,
            )
            logger.exception("Twelve Data history storage failed symbol=%s", symbol)
            return symbol, False, "storage-error"
    finally:
        close_old_connections()


def refresh_twelve_data_history(symbols=None):
    """Refresh supported daily bars once per cache window and share API quotas."""
    if not settings.TWELVE_DATA_API_KEY:
        return {}, {"configuration": "missing-api-key"}

    requested = sorted(set(symbols if symbols is not None else MARKET_STOCKS))
    unsupported = set(requested) - set(MARKET_STOCKS)
    refreshed_symbols = set()
    errors = {symbol: "unsupported-symbol" for symbol in unsupported}
    supported = [symbol for symbol in requested if symbol in MARKET_STOCKS]
    if len(supported) == 1:
        outcomes = [_refresh_twelve_data_history_for_symbol(supported[0])]
    else:
        with ThreadPoolExecutor(max_workers=5) as executor:
            outcomes = executor.map(
                _refresh_twelve_data_history_for_symbol,
                supported,
            )
    for symbol, refreshed, error in outcomes:
        if refreshed:
            refreshed_symbols.add(symbol)
        if error:
            errors[symbol] = error
    return refreshed_symbols, errors


def refresh_live_market_quotes(symbols, allow_refresh=True):
    """Fetch stale quotes once per symbol and enforce the shared free-tier quota."""
    errors = {}
    if not settings.TWELVE_DATA_API_KEY:
        return {}, {"configuration": "missing-api-key"}

    quotes = {}
    for symbol in sorted(set(symbols)):
        if not allow_refresh:
            quote = LiveMarketQuote.objects.filter(symbol=symbol).first()
            if quote and quote.price is not None and quote.fetched_at is not None:
                quotes[symbol] = quote
                continue
        now = timezone.now()
        quote, should_fetch, quota_error = _claim_quote_refresh(symbol, now)
        if quota_error:
            errors[symbol] = quota_error
            continue
        if should_fetch:
            try:
                price = _fetch_twelve_data_price(symbol)
            except TwelveDataQuoteError as error:
                LiveMarketQuote.objects.filter(pk=quote.pk).update(
                    fetch_started_at=None
                )
                logger.warning(
                    "Twelve Data quote refresh failed symbol=%s reason=%s",
                    symbol,
                    str(error),
                )
                errors[symbol] = "provider-unavailable"
                continue
            fetched_at = timezone.now()
            LiveMarketQuote.objects.filter(pk=quote.pk).update(
                price=price,
                fetched_at=fetched_at,
                fetch_started_at=None,
            )
            quote.price = price
            quote.fetched_at = fetched_at
            quote.fetch_started_at = None

        if quote.price is not None and quote.fetched_at is not None:
            quotes[symbol] = quote
    return quotes, errors

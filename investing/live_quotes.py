"""Shared, server-side Twelve Data quotes for simulated holdings."""

import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import LiveMarketQuote, TwelveDataUsageWindow

logger = logging.getLogger(__name__)

QUOTE_TTL = timedelta(minutes=5)
FETCH_LEASE = timedelta(seconds=30)
MINUTE_CREDIT_LIMIT = 8
DAILY_CREDIT_LIMIT = 800
PROVIDER = "twelve-data"


class TwelveDataQuoteError(Exception):
    """A safe-to-display failure without provider response or credential data."""


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

        if usage.minute_bucket != minute_bucket:
            usage.minute_bucket = minute_bucket
            usage.minute_credits = 0
        if usage.usage_date != now.date():
            usage.usage_date = now.date()
            usage.daily_credits = 0
        if usage.minute_credits >= MINUTE_CREDIT_LIMIT:
            return quote, False, "minute-limit"
        if usage.daily_credits >= DAILY_CREDIT_LIMIT:
            return quote, False, "daily-limit"

        usage.minute_credits += 1
        usage.daily_credits += 1
        usage.save(
            update_fields=[
                "minute_bucket",
                "minute_credits",
                "usage_date",
                "daily_credits",
            ]
        )
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

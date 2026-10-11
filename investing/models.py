"""Investing models.

Everything in this app is simulated. No brokerage is connected, no real
orders are ever placed, and no money actually moves. These models exist so
the UI can show a believable, clearly-labeled preview of round-ups and
portfolio tracking, with clean boundaries so a real brokerage adapter can
be plugged in later (see docs/integration-readiness.md) without changing
this schema's shape.
"""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel
from savings.models import Goal
from transactions.models import Transaction


class DemoInvestmentFunding(TimeStampedModel):
    """A user-entered balance top-up for simulated investing only."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="demo_investment_fundings",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Demo investing funds ${self.amount} for {self.user}"


class LiveMarketQuote(models.Model):
    """Shared, short-lived quote cache for the Twelve Data live-price feed."""

    symbol = models.CharField(max_length=20, unique=True)
    price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    fetch_started_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Live quote cache for {self.symbol}"


class TwelveDataUsageWindow(models.Model):
    """Shared API-credit counters for the configured free Twelve Data tier."""

    provider = models.CharField(max_length=20, primary_key=True)
    minute_bucket = models.DateTimeField()
    minute_credits = models.PositiveSmallIntegerField(default=0)
    usage_date = models.DateField()
    daily_credits = models.PositiveSmallIntegerField(default=0)


class TwelveDataHistoryState(models.Model):
    """Shared refresh status for each cached Twelve Data daily time series."""

    symbol = models.CharField(max_length=20, primary_key=True)
    refreshed_at = models.DateTimeField(null=True, blank=True)
    fetch_started_at = models.DateTimeField(null=True, blank=True)
    retry_after = models.DateTimeField(null=True, blank=True)


class RoundUpSettings(TimeStampedModel):
    """Per-user configuration for the simulated round-up feature."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roundup_settings"
    )
    enabled = models.BooleanField(default=False)
    target_pool = models.ForeignKey(
        Goal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roundup_settings_targeting_this_pool",
        help_text=(
            "Which investable savings pool swept round-ups are attributed to. "
            "Must be a pool with is_investable=True. Null means a general, "
            "unassigned investing bucket."
        ),
    )
    is_paused = models.BooleanField(
        default=False, help_text="Explicit pause switch, independent of enabled."
    )
    round_to = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
        help_text='Round eligible purchases up to the nearest multiple of this amount (e.g. 1.00 = nearest dollar).',
    )
    contribution_cap_per_period = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional cap on total round-ups swept per budget period.",
    )
    minimum_cash_reserve = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Round-ups will not be swept if doing so would dip below this reserve.",
    )

    def __str__(self) -> str:
        return f"RoundUpSettings<{self.user_id}>"


class RoundUpLedgerEntry(TimeStampedModel):
    """One pending/swept/reversed round-up computed from a purchase.

    Status starts as PENDING and would only move to SWEPT once a real,
    authorized funding/investment provider confirms the sweep — which
    cannot happen today because no provider is connected. In this
    prototype, "sweeping" is simulated by the investing dashboard action
    and clearly labeled as such.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SWEPT = "swept", "Swept (simulated)"
        REVERSED = "reversed", "Reversed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roundup_entries"
    )
    source_transaction = models.OneToOneField(
        Transaction, on_delete=models.CASCADE, related_name="roundup_entry"
    )
    eligible_amount = models.DecimalField(max_digits=12, decimal_places=2)
    round_up_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    swept_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Round-up {self.round_up_amount} ({self.status})"


class PortfolioSnapshot(TimeStampedModel):
    """A simulated point-in-time view of contributions vs. market value.

    net_contributions and market_value are tracked separately so reports
    can always state performance = market_value - net_contributions for a
    given period, rather than conflating deposits with investment returns.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portfolio_snapshots"
    )
    pool = models.ForeignKey(
        Goal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="portfolio_snapshots",
        help_text="Which investable savings pool this snapshot belongs to. Null = the general/unassigned bucket.",
    )
    as_of = models.DateField()
    net_contributions = models.DecimalField(max_digits=12, decimal_places=2)
    market_value = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-as_of"]
        unique_together = [("user", "pool", "as_of")]

    def __str__(self) -> str:
        return f"Snapshot {self.as_of}: value={self.market_value}"

    @property
    def gain_loss(self):
        return self.market_value - self.net_contributions


class SimulatedOrder(TimeStampedModel):
    """A fake brokerage order used only to populate the order-status UI.

    Never represents a real trade. status transitions are driven entirely
    by in-app simulation logic, never by a live market or brokerage API.
    """

    class OrderType(models.TextChoices):
        BUY = "buy", "Buy"
        SELL = "sell", "Sell"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        FILLED = "filled", "Filled (simulated)"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class PriceSource(models.TextChoices):
        BUNDLED_SAMPLE = "bundled-sample", "Bundled sample"
        TWELVE_DATA = "twelve-data", "Twelve Data"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="simulated_orders"
    )
    pool = models.ForeignKey(
        Goal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="simulated_orders",
        help_text="Which investable savings pool this order is attributed to. Null = general/unassigned bucket.",
    )
    symbol = models.CharField(max_length=20, default="MOCK-ETF")
    order_type = models.CharField(max_length=10, choices=OrderType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    filled_at = models.DateTimeField(null=True, blank=True)
    demo_execution_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    demo_price_source = models.CharField(
        max_length=20,
        choices=PriceSource.choices,
        default=PriceSource.BUNDLED_SAMPLE,
    )
    demo_shares = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    demo_data_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.order_type} {self.amount} {self.symbol} ({self.status})"


class DemoInvestmentSuggestion(TimeStampedModel):
    """A rule-based demo recommendation generated from one market-data source."""

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting your decision"
        ACCEPTED = "accepted", "Accepted (simulated order)"
        DECLINED = "declined", "Declined"

    class DataSource(models.TextChoices):
        BUNDLED_SAMPLE = "bundled-sample", "Bundled sample"
        TWELVE_DATA = "twelve-data", "Twelve Data"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="demo_investment_suggestions",
    )
    symbol = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    data_date = models.DateField()
    data_source = models.CharField(
        max_length=20,
        choices=DataSource.choices,
        default=DataSource.BUNDLED_SAMPLE,
    )
    demo_execution_price = models.DecimalField(max_digits=14, decimal_places=4)
    historical_return_percent = models.DecimalField(max_digits=9, decimal_places=2)
    volatility_percent = models.DecimalField(max_digits=9, decimal_places=2)
    score = models.DecimalField(max_digits=9, decimal_places=2)
    explanation = models.CharField(max_length=300)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    simulated_order = models.OneToOneField(
        SimulatedOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="demo_suggestion",
    )

    class Meta:
        ordering = ["-score", "symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "symbol", "data_date", "data_source"],
                name="unique_demo_suggestion_user_symbol_date_source",
            )
        ]

    def __str__(self) -> str:
        return f"Demo suggestion {self.symbol} for {self.user}"


class MarketPrice(TimeStampedModel):
    """A source-verified daily OHLCV row for one symbol/date.

    Only verified rows are ever stored here — there is no fabricated or
    estimated data. Missing requested assets/dates simply have no row;
    see docs/demo-market-data.md for exactly what was and wasn't verified
    and why.
    """

    class AssetType(models.TextChoices):
        INDEX = "index", "Index"
        STOCK = "stock", "Stock"

    symbol = models.CharField(max_length=20)
    asset_name = models.CharField(max_length=80, blank=True, default="")
    asset_type = models.CharField(max_length=10, choices=AssetType.choices)
    date = models.DateField()
    open = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    high = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    low = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    close = models.DecimalField(max_digits=14, decimal_places=4)
    volume = models.BigIntegerField(null=True, blank=True)
    daily_change_percent = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    source_note = models.CharField(max_length=120, help_text='e.g. "Yahoo Finance historical data"')
    is_verified = models.BooleanField(
        default=True, help_text="Always true today: unverified rows are never inserted, only omitted."
    )
    is_demo_sample = models.BooleanField(
        default=False,
        help_text="This row came from the bundled Excel-backed demo dataset.",
    )
    is_twelve_data = models.BooleanField(
        default=False,
        help_text="This row was fetched from the Twelve Data API.",
    )

    class Meta:
        unique_together = [("symbol", "date")]
        ordering = ["symbol", "date"]

    def __str__(self) -> str:
        return f"{self.symbol} {self.date} close={self.close}"

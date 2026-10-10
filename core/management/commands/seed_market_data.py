"""Seed verified September 2026 market data (idempotent).

Every row below was supplied by the project owner from a source-verification
report citing Yahoo Finance historical data, StockAnalysis, and FRED/S&P Dow
Jones Indices. This is a deliberately PARTIAL dataset: the source report
covers five major U.S. indexes and five stocks, but only verified full OHLCV
rows for S&P 500 (partial dates) and four stocks (NVDA, GOOGL, MSFT, AAPL;
each only for the dates where a source page was actually checked). No row
below is estimated, interpolated, or fabricated — missing requested
assets/dates simply have no row. See docs/demo-market-data.md.

Usage: python manage.py seed_market_data [--reset]
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from investing.models import MarketPrice

YAHOO = "Yahoo Finance historical data"
STOCKANALYSIS = "StockAnalysis"
FRED = "FRED series SP500 / S&P Dow Jones Indices LLC (close only)"

# (symbol, asset_type, date, open, high, low, close, volume, change_pct, source)
ROWS = [
    # S&P 500 — full OHLCV rows (Yahoo Finance)
    ("S&P 500", "index", date(2026, 9, 11), Decimal("7636.75"), Decimal("7677.02"), Decimal("7636.75"), Decimal("7656.98"), 4_722_480_000, None, YAHOO),
    ("S&P 500", "index", date(2026, 9, 14), Decimal("7611.44"), Decimal("7647.99"), Decimal("7592.28"), Decimal("7619.98"), 4_963_750_000, None, YAHOO),
    ("S&P 500", "index", date(2026, 9, 15), Decimal("7612.30"), Decimal("7617.26"), Decimal("7572.69"), Decimal("7585.73"), 5_154_930_000, None, YAHOO),
    ("S&P 500", "index", date(2026, 9, 16), Decimal("7601.25"), Decimal("7626.79"), Decimal("7507.77"), Decimal("7551.81"), 5_307_920_000, None, YAHOO),
    ("S&P 500", "index", date(2026, 9, 17), Decimal("7631.44"), Decimal("7646.86"), Decimal("7611.81"), Decimal("7637.76"), 5_058_210_000, None, YAHOO),
    ("S&P 500", "index", date(2026, 9, 18), Decimal("7657.17"), Decimal("7657.17"), Decimal("7610.52"), Decimal("7650.50"), 8_858_350_000, None, YAHOO),
    # S&P 500 — close-only rows corroborated by FRED (no OHLV available)
    ("S&P 500", "index", date(2026, 9, 21), None, None, None, Decimal("7764.70"), None, None, FRED),
    ("S&P 500", "index", date(2026, 9, 22), None, None, None, Decimal("7764.64"), None, None, FRED),
    # NVIDIA (NVDA)
    ("NVDA", "stock", date(2026, 9, 25), Decimal("225.13"), Decimal("226.94"), Decimal("223.13"), Decimal("225.07"), 89_947_712, Decimal("0.22"), STOCKANALYSIS),
    ("NVDA", "stock", date(2026, 9, 28), Decimal("229.75"), Decimal("233.21"), Decimal("228.04"), Decimal("228.86"), 142_344_321, Decimal("1.68"), STOCKANALYSIS),
    ("NVDA", "stock", date(2026, 9, 29), Decimal("230.97"), Decimal("232.82"), Decimal("227.03"), Decimal("227.21"), 101_494_933, Decimal("-0.72"), STOCKANALYSIS),
    ("NVDA", "stock", date(2026, 9, 30), Decimal("229.27"), Decimal("232.37"), Decimal("228.17"), Decimal("228.38"), 121_732_188, Decimal("0.51"), STOCKANALYSIS),
    # Alphabet (GOOGL)
    ("GOOGL", "stock", date(2026, 9, 29), Decimal("341.95"), Decimal("342.84"), Decimal("338.02"), Decimal("340.92"), 21_066_900, Decimal("-0.53"), STOCKANALYSIS),
    ("GOOGL", "stock", date(2026, 9, 30), Decimal("344.15"), Decimal("352.60"), Decimal("340.99"), Decimal("344.08"), 37_373_739, Decimal("0.93"), STOCKANALYSIS),
    # Microsoft (MSFT)
    ("MSFT", "stock", date(2026, 9, 29), Decimal("508.31"), Decimal("513.64"), Decimal("502.40"), Decimal("508.96"), 21_341_832, Decimal("-0.05"), STOCKANALYSIS),
    ("MSFT", "stock", date(2026, 9, 30), Decimal("511.61"), Decimal("519.83"), Decimal("510.31"), Decimal("512.90"), 27_223_264, Decimal("0.77"), STOCKANALYSIS),
    # Apple (AAPL)
    ("AAPL", "stock", date(2026, 9, 15), Decimal("330.14"), Decimal("331.78"), Decimal("328.35"), Decimal("331.34"), 31_748_183, Decimal("-0.52"), STOCKANALYSIS),
    ("AAPL", "stock", date(2026, 9, 16), Decimal("332.53"), Decimal("335.48"), Decimal("330.70"), Decimal("332.41"), 35_981_000, Decimal("0.32"), STOCKANALYSIS),
]

# What was requested but has no verified row anywhere in this dataset —
# stated explicitly so the gap is documented, not silently absent.
NOT_VERIFIED = (
    "4 of the 5 requested major indexes (only S&P 500 was verified), "
    "1 of the 5 requested stocks, and every September weekday not listed "
    "above for the assets that were partially verified."
)


class Command(BaseCommand):
    help = "Seed verified September 2026 market data (idempotent, source-cited, no fabricated rows)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing MarketPrice rows first.")

    def handle(self, *args, **options):
        if options["reset"]:
            deleted, _ = MarketPrice.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Reset: deleted {deleted} existing MarketPrice row(s)."))

        created_count = 0
        for symbol, asset_type, the_date, o, h, l, c, vol, chg, source in ROWS:
            _, created = MarketPrice.objects.get_or_create(
                symbol=symbol,
                date=the_date,
                defaults={
                    "asset_type": asset_type,
                    "open": o, "high": h, "low": l, "close": c,
                    "volume": vol,
                    "daily_change_percent": chg,
                    "source_note": source,
                    "is_verified": True,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded {created_count} new verified market-data row(s) (existing rows left untouched)."))
        self.stdout.write(self.style.WARNING(f"NOT verified / not imported: {NOT_VERIFIED}"))

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from investing.models import MarketPrice


class Command(BaseCommand):
    help = "Load the supplied September 2026 sample market data for demo recommendations."

    def handle(self, *args, **options):
        path = (
            Path(settings.BASE_DIR)
            / "demo_data"
            / "september_2026_verified_market_data.csv"
        )
        if not path.is_file():
            raise CommandError(f"Demo market data file not found: {path}")

        loaded = 0
        with path.open(encoding="utf-8", newline="") as data_file:
            for row in csv.DictReader(data_file):
                ticker = row["ticker"].strip()
                MarketPrice.objects.update_or_create(
                    symbol=ticker,
                    date=date.fromisoformat(row["date"]),
                    defaults={
                        "asset_type": (
                            MarketPrice.AssetType.INDEX
                            if ticker.startswith("^")
                            else MarketPrice.AssetType.STOCK
                        ),
                        "open": Decimal(row["open"]) if row["open"] else None,
                        "high": Decimal(row["high"]) if row["high"] else None,
                        "low": Decimal(row["low"]) if row["low"] else None,
                        "close": Decimal(row["close"]),
                        "volume": int(row["volume"]) if row["volume"] else None,
                        "daily_change_percent": (
                            Decimal(row["daily_change_percent"])
                            if row["daily_change_percent"]
                            else None
                        ),
                        "source_note": row["source_note"][:120],
                        "is_verified": True,
                        "is_demo_sample": True,
                    },
                )
                loaded += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {loaded} rows from the supplied demo market dataset."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "These are sample historical prices for simulated trading only. "
                "They are not live prices or trade instructions."
            )
        )

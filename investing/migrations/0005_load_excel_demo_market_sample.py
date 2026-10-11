import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import migrations, models


def load_sample_market_data(apps, schema_editor):
    MarketPrice = apps.get_model("investing", "MarketPrice")
    database = schema_editor.connection.alias
    dataset_path = (
        Path(settings.BASE_DIR)
        / "demo_data"
        / "september_2026_verified_market_data.csv"
    )
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Bundled sample market data not found: {dataset_path}")

    with dataset_path.open(encoding="utf-8", newline="") as data_file:
        for row in csv.DictReader(data_file):
            symbol = row["ticker"].strip()
            MarketPrice.objects.using(database).update_or_create(
                symbol=symbol,
                date=date.fromisoformat(row["date"]),
                defaults={
                    "asset_name": row["asset"].strip()[:80],
                    "asset_type": "index" if symbol.startswith("^") else "stock",
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


def remove_sample_market_data(apps, schema_editor):
    MarketPrice = apps.get_model("investing", "MarketPrice")
    database = schema_editor.connection.alias
    dataset_path = (
        Path(settings.BASE_DIR)
        / "demo_data"
        / "september_2026_verified_market_data.csv"
    )
    with dataset_path.open(encoding="utf-8", newline="") as data_file:
        for row in csv.DictReader(data_file):
            MarketPrice.objects.using(database).filter(
                symbol=row["ticker"].strip(),
                date=date.fromisoformat(row["date"]),
                is_demo_sample=True,
            ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("investing", "0004_marketprice_is_demo_sample"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketprice",
            name="asset_name",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.RunPython(load_sample_market_data, remove_sample_market_data),
    ]

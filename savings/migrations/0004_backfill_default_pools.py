"""Give every existing user the three default pools and a savings plan.

Non-destructive and safe to re-run: existing goals, balances, and plans are
never modified, except that a user's oldest "Emergency fund" goal is adopted
as their Rainy Day pool (keeping its name and balance) instead of creating a
second emergency pool next to it.
"""

from decimal import Decimal

from django.conf import settings
from django.db import migrations

DEFAULT_POOLS = [
    ("rainy_day", "Rainy Day", "emergency", "#2f7d62", False),
    ("investment", "Investment", "other", "#c8963e", True),
    ("regular", "Regular Savings", "other", "#4f7cac", False),
]


def backfill(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Goal = apps.get_model("savings", "Goal")
    SavingsPlan = apps.get_model("savings", "SavingsPlan")
    for user in User.objects.all().iterator():
        have = set(Goal.objects.filter(user=user).exclude(pool_kind="").values_list("pool_kind", flat=True))
        for kind, name, category, color, investable in DEFAULT_POOLS:
            if kind in have:
                continue
            if kind == "rainy_day":
                existing = (
                    Goal.objects.filter(user=user, pool_kind="", category="emergency")
                    .order_by("created_at")
                    .first()
                )
                if existing is not None:
                    existing.pool_kind = kind
                    existing.save(update_fields=["pool_kind"])
                    continue
            Goal.objects.create(
                user=user,
                pool_kind=kind,
                name=name,
                category=category,
                color=color,
                is_investable=investable,
                target_amount=Decimal("0.00"),
                current_amount=Decimal("0.00"),
            )
        SavingsPlan.objects.get_or_create(user=user)


class Migration(migrations.Migration):
    dependencies = [
        ("savings", "0003_default_pools_and_savings_plan"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]

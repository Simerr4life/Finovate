"""Create the three default system pools for existing users who lack them."""

from decimal import Decimal

from django.db import migrations

STARTER_EMERGENCY_CAP = Decimal("1000.00")

DEFAULT_POOLS = (
    {
        "system_key": "rainy_day",
        "name": "Rainy Day",
        "category": "emergency",
        "color": "#2F6F4E",
        "is_investable": False,
        "target_amount": STARTER_EMERGENCY_CAP,
    },
    {
        "system_key": "investment",
        "name": "Investment",
        "category": "other",
        "color": "#1F3A5F",
        "is_investable": True,
        "target_amount": Decimal("10000.00"),
    },
    {
        "system_key": "regular",
        "name": "Regular Savings",
        "category": "other",
        "color": "#C4A35A",
        "is_investable": False,
        "target_amount": Decimal("5000.00"),
    },
)


def backfill_pools(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Goal = apps.get_model("savings", "Goal")
    for user in User.objects.all().iterator():
        for spec in DEFAULT_POOLS:
            key = spec["system_key"]
            if Goal.objects.filter(user=user, system_key=key).exists():
                continue
            adopted = Goal.objects.filter(user=user, system_key="", name=spec["name"]).first()
            if adopted is not None:
                adopted.system_key = key
                if key == "rainy_day":
                    adopted.category = "emergency"
                if key == "investment":
                    adopted.is_investable = True
                adopted.save(update_fields=["system_key", "category", "is_investable", "updated_at"])
                continue
            Goal.objects.create(
                user=user,
                name=spec["name"],
                system_key=key,
                category=spec["category"],
                color=spec["color"],
                is_investable=spec["is_investable"],
                target_amount=spec["target_amount"],
                current_amount=Decimal("0.00"),
            )


def noop_reverse(apps, schema_editor):
    # Do not delete pools or wipe balances on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("savings", "0003_savings_plan_engine"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(backfill_pools, noop_reverse),
    ]

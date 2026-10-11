"""Seed a demo user with clearly-labeled sample data.

Usage: python manage.py seed_demo [--username demo] [--reset]

Everything created here has source="demo" / is_demo=True so it's always
distinguishable from data a real user enters, and --reset only ever
touches that demo user's own rows.
"""

import os
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

PUBLISHED_LOCAL_PASSWORD = "demo-pass-1234"

from budgets.models import Budget, BudgetPeriod, IncomeSource, RecurringExpense
from investing.models import RoundUpSettings
from investing.services import create_roundup_for_transaction, sweep_pending_roundups
from savings.models import Goal
from savings.services import apply_contribution
from transactions.models import Category, Transaction
from transactions.services import record_transaction


class Command(BaseCommand):
    help = "Create (or reset) a demo user with clearly-labeled sample data."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="demo-pass-1234")
        parser.add_argument("--reset", action="store_true", help="Delete this demo user's existing data first.")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        if (
            not settings.DEBUG
            and password == PUBLISHED_LOCAL_PASSWORD
            and not os.environ.get("DEMO_ACCOUNT_PASSWORD")
        ):
            raise CommandError(
                "Refusing the published local demo password while DEBUG is false. "
                "Set DEMO_ACCOUNT_PASSWORD or pass --password."
            )
        if password == PUBLISHED_LOCAL_PASSWORD and os.environ.get("DEMO_ACCOUNT_PASSWORD"):
            password = os.environ["DEMO_ACCOUNT_PASSWORD"]

        user, created = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com"})
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created user '{username}'. The password is not written to the log."))
        elif options["reset"]:
            user.categories.all().delete()
            user.transactions.all().delete()
            user.budget_periods.all().delete()
            user.income_sources.all().delete()
            user.recurring_expenses.all().delete()
            user.goals.all().delete()
            self.stdout.write(self.style.WARNING(f"Reset existing data for '{username}'"))
        else:
            self.stdout.write(f"User '{username}' already exists; use --reset to repopulate demo data.")

        profile = user.profile
        profile.onboarding_completed = True
        profile.income_cadence = "biweekly"
        profile.cash_reserve_target = Decimal("500.00")
        profile.save()

        today = timezone.now().date()

        groceries = Category.objects.get_or_create(user=user, name="Groceries", kind="expense", defaults={"color": "#10b981", "is_demo": True})[0]
        dining = Category.objects.get_or_create(user=user, name="Dining out", kind="expense", defaults={"color": "#f59e0b", "is_demo": True})[0]
        transport = Category.objects.get_or_create(user=user, name="Transport", kind="expense", defaults={"color": "#6366f1", "is_demo": True})[0]
        subscriptions = Category.objects.get_or_create(user=user, name="Subscriptions", kind="expense", defaults={"color": "#f43f5e", "is_demo": True})[0]
        salary_cat = Category.objects.get_or_create(user=user, name="Salary", kind="income", defaults={"color": "#059669", "is_demo": True})[0]

        rs, _ = RoundUpSettings.objects.get_or_create(user=user)
        rs.enabled = True
        rs.is_paused = False
        rs.round_to = Decimal("1.00")
        rs.minimum_cash_reserve = Decimal("500.00")
        rs.save()

        # Two paychecks
        for weeks_ago in (0, 2):
            record_transaction(
                user, kind=Transaction.Kind.INCOME, amount=Decimal("1850.00"),
                occurred_on=today - timedelta(weeks=weeks_ago), category=salary_cat,
                description="Paycheck", source="demo", is_demo=True,
                external_id=f"demo-paycheck-{weeks_ago}",
            )

        demo_expenses = [
            (groceries, Decimal("54.35"), "Grocery run", 1),
            (groceries, Decimal("22.10"), "Grocery run", 6),
            (dining, Decimal("18.65"), "Lunch", 2),
            (dining, Decimal("31.20"), "Dinner out", 9),
            (transport, Decimal("40.00"), "Gas", 4),
            (subscriptions, Decimal("15.99"), "Streaming", 10),
        ]
        for category, amount, description, days_ago in demo_expenses:
            txn, _ = record_transaction(
                user, kind=Transaction.Kind.EXPENSE, amount=amount,
                occurred_on=today - timedelta(days=days_ago), category=category,
                description=description, source="demo", is_demo=True,
                external_id=f"demo-{description}-{days_ago}",
            )
            create_roundup_for_transaction(txn)

        sweep_pending_roundups(user, as_of=today)

        period, _ = BudgetPeriod.objects.get_or_create(
            user=user, name=today.strftime("%B %Y"),
            defaults={"start_date": today.replace(day=1), "end_date": today, "is_active": True},
        )
        for category, limit in [(groceries, Decimal("400.00")), (dining, Decimal("150.00")), (transport, Decimal("120.00"))]:
            Budget.objects.get_or_create(period=period, category=category, defaults={"user": user, "limit_amount": limit})

        IncomeSource.objects.get_or_create(user=user, name="Day job salary", defaults={"amount": Decimal("1850.00"), "cadence": "biweekly"})
        RecurringExpense.objects.get_or_create(user=user, name="Rent", defaults={"amount": Decimal("1200.00"), "cadence": "monthly"})
        RecurringExpense.objects.get_or_create(user=user, name="Streaming", category=subscriptions, defaults={"amount": Decimal("15.99"), "cadence": "monthly"})

        emergency_goal, _ = Goal.objects.get_or_create(
            user=user, name="Emergency fund",
            defaults={"category": "emergency", "target_amount": Decimal("2000.00"), "current_amount": Decimal("0.00"), "is_demo": True},
        )
        if not emergency_goal.contributions.exists():
            for days_ago, amount in [(60, Decimal("300.00")), (30, Decimal("250.00")), (5, Decimal("200.00"))]:
                c, _crossed = apply_contribution(emergency_goal, kind="contribution", amount=amount, note="Demo contribution", source="demo")
                c.created_at = timezone.now() - timedelta(days=days_ago)
                c.save(update_fields=["created_at"])

        travel_goal, _ = Goal.objects.get_or_create(
            user=user, name="Trip to Lisbon",
            defaults={"category": "travel", "target_amount": Decimal("1500.00"), "current_amount": Decimal("375.00"), "target_date": today + timedelta(days=200), "is_demo": True},
        )

        self.stdout.write(self.style.SUCCESS(f"Demo data ready for user '{username}'."))

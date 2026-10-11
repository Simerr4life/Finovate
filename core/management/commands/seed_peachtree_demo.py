"""Seed the fictional "Peachtree Student Banking" demo statement.

Usage: python manage.py seed_peachtree_demo [--username demo] [--reset]

Everything created here is clearly fictional — a made-up institution,
account holder, and transaction history used only to demonstrate how
Finovate imports, categorizes, budgets, and analyzes bank-style data. It
is NOT a real bank statement, does not represent a real person, and does
not connect to any real financial institution.

Idempotent: re-running without --reset leaves existing rows untouched
(transactions are deduped by external_id; the Account/goals/budgets/period
are fetched with get_or_create). --reset only ever deletes rows tied to
this specific demo Account (or these specific demo goal names) for the
named user — never another user's data, and never the unrelated seed_demo
dataset.
"""

import os
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from budgets.models import Budget, BudgetPeriod
from investing.models import RoundUpSettings
from investing.services import create_roundup_for_transaction
from savings.models import Goal
from savings.services import apply_contribution
from transactions.models import Account, Category, Transaction
from transactions.services import reconcile_account, record_transaction

STATEMENT_YEAR = 2026
STATEMENT_MONTH = 9

# (day, description, amount, direction, category_name, category_kind, is_earned_income)
# direction: "in" or "out"
TRANSACTIONS = [
    (2, "Campus café", Decimal("8.75"), "out", "Food: Cafés & Restaurants", "expense", None),
    (3, "Monthly income deposit", Decimal("3000.00"), "in", "Salary and Wages", "income", True),
    (3, "Monthly rent payment", Decimal("1000.00"), "out", "Housing: Rent", "expense", None),
    (4, "MARTA transit reload", Decimal("25.00"), "out", "Transportation", "expense", None),
    (5, "Grocery store", Decimal("68.42"), "out", "Food: Groceries", "expense", None),
    (6, "Venmo from Mom, shared groceries", Decimal("40.00"), "in", "Reimbursements", "income", False),
    (7, "Coffee shop", Decimal("6.50"), "out", "Food: Cafés & Restaurants", "expense", None),
    (9, "Mobile phone bill", Decimal("55.00"), "out", "Utilities: Mobile Phone", "expense", None),
    (10, "Restaurant, dinner", Decimal("24.80"), "out", "Food: Cafés & Restaurants", "expense", None),
    (11, "Venmo from Jordan, concert split", Decimal("18.50"), "in", "Reimbursements", "income", False),
    (12, "Textbooks and school supplies", Decimal("42.75"), "out", "Education", "expense", None),
    (14, "Grocery store", Decimal("51.20"), "out", "Food: Groceries", "expense", None),
    (15, "Streaming subscription", Decimal("12.99"), "out", "Personal: Subscriptions", "expense", None),
    (16, "Rideshare/local transportation", Decimal("21.40"), "out", "Transportation", "expense", None),
    (18, "Venmo to Maya, takeout split", Decimal("32.00"), "out", "Shared Expense Reimbursement", "expense", None),
    (19, "Campus bookstore", Decimal("19.95"), "out", "Education", "expense", None),
    (20, "Internet share", Decimal("35.00"), "out", "Utilities: Internet", "expense", None),
    (22, "Grocery store", Decimal("46.80"), "out", "Food: Groceries", "expense", None),
    (24, "Venmo from Dad, school support", Decimal("75.00"), "in", "Family Support / Gifts", "income", False),
    (25, "Restaurant, weekend meal", Decimal("31.60"), "out", "Food: Cafés & Restaurants", "expense", None),
    (27, "Laundry", Decimal("12.00"), "out", "Personal: Laundry", "expense", None),
    (28, "MARTA transit reload", Decimal("25.00"), "out", "Transportation", "expense", None),
    (30, "Utilities share", Decimal("48.00"), "out", "Utilities: Other", "expense", None),
]

# Illustrative category limits for a student living off-campus in Atlanta.
# These are demo assumptions, not figures derived from the bank statement.
PUBLISHED_LOCAL_PASSWORD = "demo-pass-1234"

DEMO_BUDGET_LIMITS = {
    "Housing: Rent": Decimal("1000.00"),
    "Food: Groceries": Decimal("250.00"),
    "Food: Cafés & Restaurants": Decimal("120.00"),
    "Transportation": Decimal("100.00"),
    "Utilities: Mobile Phone": Decimal("60.00"),
    "Utilities: Internet": Decimal("40.00"),
    "Utilities: Other": Decimal("60.00"),
    "Education": Decimal("100.00"),
    "Personal: Subscriptions": Decimal("20.00"),
    "Personal: Laundry": Decimal("20.00"),
}


class Command(BaseCommand):
    help = 'Seed the fictional "Peachtree Student Banking" demo statement (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="demo-pass-1234")
        parser.add_argument("--reset", action="store_true", help="Delete this demo account's transactions first.")

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

        user.profile.onboarding_completed = True
        user.profile.save()

        account, _ = Account.objects.get_or_create(
            user=user,
            masked_number="••••4821",
            institution_name="Peachtree Student Banking",
            defaults={
                "account_holder_name": "Sample GSU Student",
                "account_type": "Student checking account",
                "location": "Atlanta, Georgia",
                "is_demo": True,
                "statement_start_date": date(STATEMENT_YEAR, STATEMENT_MONTH, 1),
                "statement_end_date": date(STATEMENT_YEAR, STATEMENT_MONTH, 30),
                "opening_balance": Decimal("1245.80"),
                "stated_total_deposits": Decimal("3133.50"),
                "stated_total_withdrawals": Decimal("1567.16"),
                "stated_ending_balance": Decimal("2812.14"),
            },
        )

        if options["reset"]:
            deleted, _ = Transaction.objects.filter(user=user, account=account).delete()
            self.stdout.write(self.style.WARNING(f"Reset: deleted {deleted} transaction(s) on this demo account."))

        rs, _ = RoundUpSettings.objects.get_or_create(user=user)
        if not rs.enabled:
            rs.enabled = True
            rs.round_to = Decimal("1.00")
            rs.minimum_cash_reserve = Decimal("300.00")
            rs.save()

        categories = {}
        for _, _, _, _, cat_name, cat_kind, is_earned in TRANSACTIONS:
            key = (cat_name, cat_kind)
            if key in categories:
                continue
            defaults = {"color": _color_for(cat_name), "is_demo": True}
            if cat_kind == "income":
                defaults["is_earned_income"] = bool(is_earned)
            cat, _ = Category.objects.get_or_create(user=user, name=cat_name, kind=cat_kind, defaults=defaults)
            categories[key] = cat

        created_count = 0
        for day, description, amount, direction, cat_name, cat_kind, _ in TRANSACTIONS:
            slug = description.lower().replace(",", "").replace(" ", "-").replace("/", "-")
            txn, was_created = record_transaction(
                user,
                kind=Transaction.Kind.INCOME if direction == "in" else Transaction.Kind.EXPENSE,
                amount=amount,
                occurred_on=date(STATEMENT_YEAR, STATEMENT_MONTH, day),
                category=categories[(cat_name, cat_kind)],
                description=description,
                source="demo",
                external_id=f"peachtree-2026-09-{day:02d}-{slug}",
                is_demo=True,
                account=account,
            )
            if was_created:
                created_count += 1
                if txn.kind == Transaction.Kind.EXPENSE:
                    create_roundup_for_transaction(txn)

        self.stdout.write(self.style.SUCCESS(f"Seeded {created_count} new transaction(s) (already-existing ones were left untouched)."))

        period, _ = BudgetPeriod.objects.get_or_create(
            user=user,
            name="September 2026 — Peachtree Demo",
            defaults={
                "start_date": date(STATEMENT_YEAR, STATEMENT_MONTH, 1),
                "end_date": date(STATEMENT_YEAR, STATEMENT_MONTH, 30),
                "is_active": True,
            },
        )
        for cat_name, limit in DEMO_BUDGET_LIMITS.items():
            cat = categories.get((cat_name, "expense"))
            if cat:
                Budget.objects.get_or_create(
                    period=period, category=cat, defaults={"user": user, "limit_amount": limit}
                )

        general_savings, g_created = Goal.objects.get_or_create(
            user=user, name="General Savings (Peachtree demo)",
            defaults={"category": Goal.Category.OTHER, "target_amount": Decimal("500.00"), "is_demo": True},
        )
        if g_created:
            apply_contribution(general_savings, kind="contribution", amount=Decimal("100.00"), note="Demo contribution", source="demo")
            apply_contribution(general_savings, kind="contribution", amount=Decimal("50.00"), note="Demo contribution", source="demo")

        emergency_savings, e_created = Goal.objects.get_or_create(
            user=user, name="Emergency Savings (Peachtree demo)",
            defaults={"category": Goal.Category.EMERGENCY, "target_amount": Decimal("1000.00"), "is_demo": True},
        )
        if e_created:
            apply_contribution(emergency_savings, kind="contribution", amount=Decimal("200.00"), note="Demo contribution", source="demo")
            apply_contribution(emergency_savings, kind="contribution", amount=Decimal("100.00"), note="Demo contribution", source="demo")

        report = reconcile_account(account)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Reconciliation (computed from the ledger, not just copied from the source):"))
        self.stdout.write(f"  Opening balance:     ${report.opening_balance}")
        self.stdout.write(f"  Computed deposits:   ${report.computed_total_deposits}  (stated: ${report.stated_total_deposits}, match={report.deposits_match})")
        self.stdout.write(f"  Computed withdrawals:${report.computed_total_withdrawals}  (stated: ${report.stated_total_withdrawals}, match={report.withdrawals_match})")
        self.stdout.write(f"  Computed ending:     ${report.computed_ending_balance}  (stated: ${report.stated_ending_balance}, match={report.ending_balance_match})")
        if report.fully_reconciled:
            self.stdout.write(self.style.SUCCESS("  Fully reconciled (OK)"))
        else:
            self.stdout.write(self.style.ERROR("  NOT fully reconciled -- see docs/demo-peachtree-account.md"))

        self.stdout.write(self.style.SUCCESS(f"\nPeachtree demo ready for user '{username}'. View it at /statements/{account.pk}/"))


def _color_for(category_name: str) -> str:
    palette = {
        "Housing: Rent": "#f43f5e",
        "Food: Groceries": "#10b981",
        "Food: Cafés & Restaurants": "#f59e0b",
        "Transportation": "#6366f1",
        "Utilities: Mobile Phone": "#0ea5e9",
        "Utilities: Internet": "#0284c7",
        "Utilities: Other": "#64748b",
        "Education": "#8b5cf6",
        "Personal: Subscriptions": "#ec4899",
        "Personal: Laundry": "#94a3b8",
        "Shared Expense Reimbursement": "#a78bfa",
        "Salary and Wages": "#059669",
        "Reimbursements": "#22c55e",
        "Family Support / Gifts": "#14b8a6",
    }
    return palette.get(category_name, "#6366F1")

"""Default pool creation and finance-change recalculation signals."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase

from accounts.models import NotificationEvent
from budgets.models import IncomeSource, RecurringExpense

from .models import Goal, SavingsPlan
from .plan_engine import FALLBACK_INVEST, FALLBACK_RAINY, FALLBACK_REGULAR, ensure_default_pools, refresh_savings_plan


class DefaultPoolTests(TestCase):
    def test_new_user_gets_exactly_three_default_pools(self):
        user = User.objects.create_user(username="pool-new", password="x")
        keys = list(
            Goal.objects.filter(user=user)
            .exclude(system_key="")
            .order_by("system_key")
            .values_list("system_key", flat=True)
        )
        self.assertEqual(
            keys,
            [
                Goal.SystemKey.INVESTMENT,
                Goal.SystemKey.RAINY_DAY,
                Goal.SystemKey.REGULAR,
            ],
        )

    def test_ensure_default_pools_is_idempotent_and_preserves_balances(self):
        user = User.objects.create_user(username="pool-idem", password="x")
        rainy = Goal.objects.get(user=user, system_key=Goal.SystemKey.RAINY_DAY)
        rainy.current_amount = Decimal("123.45")
        rainy.save(update_fields=["current_amount", "updated_at"])
        first = ensure_default_pools(user)
        second = ensure_default_pools(user)
        self.assertEqual(Goal.objects.filter(user=user).exclude(system_key="").count(), 3)
        self.assertEqual(first[Goal.SystemKey.RAINY_DAY].pk, second[Goal.SystemKey.RAINY_DAY].pk)
        rainy.refresh_from_db()
        self.assertEqual(rainy.current_amount, Decimal("123.45"))

    def test_fallback_allocation_percentages(self):
        self.assertEqual(FALLBACK_RAINY + FALLBACK_INVEST + FALLBACK_REGULAR, Decimal("100"))
        self.assertEqual((FALLBACK_RAINY, FALLBACK_INVEST, FALLBACK_REGULAR), (
            Decimal("40"),
            Decimal("20"),
            Decimal("40"),
        ))


class RecalculationSignalTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="recalc-user", password="x")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()

    def test_income_change_recalculates_plan_without_duplicates(self):
        IncomeSource.objects.create(
            user=self.user, name="Pay", amount=Decimal("5000"), cadence="monthly"
        )
        RecurringExpense.objects.create(
            user=self.user,
            name="Housing (estimate)",
            amount=Decimal("1500"),
            cadence="monthly",
        )
        plan = SavingsPlan.objects.get(user=self.user)
        self.assertGreater(plan.safe_to_save, 0)
        first_fp = plan.fingerprint
        IncomeSource.objects.filter(user=self.user).update(amount=Decimal("5500"))
        # update() bypasses signals; touch via save to fire recalculation
        src = IncomeSource.objects.get(user=self.user)
        src.amount = Decimal("5500")
        src.save()
        plan.refresh_from_db()
        self.assertNotEqual(plan.fingerprint, first_fp)
        self.assertEqual(SavingsPlan.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Goal.objects.filter(user=self.user).exclude(system_key="").count(), 3)

    def test_shortfall_never_allocates_positive_savings(self):
        IncomeSource.objects.create(
            user=self.user, name="Pay", amount=Decimal("1000"), cadence="monthly"
        )
        RecurringExpense.objects.create(
            user=self.user,
            name="Housing (estimate)",
            amount=Decimal("2000"),
            cadence="monthly",
        )
        plan = refresh_savings_plan(self.user, reason="test", force=True)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.safe_to_save, Decimal("0.00"))
        self.assertEqual(plan.rainy_day_amount, Decimal("0.00"))
        self.assertEqual(plan.investment_amount, Decimal("0.00"))
        self.assertEqual(plan.regular_amount, Decimal("0.00"))
        self.assertTrue(
            NotificationEvent.objects.filter(
                user=self.user, event_type=NotificationEvent.EventType.SAVINGS_PLAN
            ).exists()
        )

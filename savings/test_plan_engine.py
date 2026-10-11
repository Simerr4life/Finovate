"""Scenario coverage for the personalized savings-plan engine."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from budgets.models import IncomeSource, RecurringExpense

from .models import DebtObligation, Goal, SavingsPlan
from .plan_engine import (
    analyze_finances,
    build_recommendation,
    choose_scenario,
    ensure_default_pools,
    refresh_savings_plan,
)


class DefaultPoolTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="plan-user", password="pw12345")

    def test_creates_exactly_three_system_pools_without_duplicating(self):
        first = ensure_default_pools(self.user)
        second = ensure_default_pools(self.user)
        self.assertEqual(set(first), set(second))
        self.assertEqual(Goal.objects.filter(user=self.user, system_key__gt="").count(), 3)
        rainy = first[Goal.SystemKey.RAINY_DAY]
        rainy.current_amount = Decimal("250.00")
        rainy.save()
        ensure_default_pools(self.user)
        rainy.refresh_from_db()
        self.assertEqual(rainy.current_amount, Decimal("250.00"))


class ScenarioEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scenario", password="pw12345")
        self.user.profile.cash_reserve_target = Decimal("300.00")
        self.user.profile.save()

    def _income(self, amount):
        IncomeSource.objects.create(user=self.user, name="Pay", amount=amount, cadence="monthly")

    def _expense(self, name, amount):
        RecurringExpense.objects.create(user=self.user, name=name, amount=amount, cadence="monthly")

    def test_no_income_negative_cash_flow_stabilization(self):
        self._expense("Housing (estimate)", Decimal("2000"))
        analysis = analyze_finances(self.user)
        self.assertEqual(choose_scenario(analysis), SavingsPlan.Scenario.STABILIZATION)
        rec = build_recommendation(analysis)
        self.assertEqual(analysis.safe_to_save, Decimal("0.00"))
        self.assertEqual(rec.rainy_day_amount + rec.investment_amount + rec.regular_amount, Decimal("0.00"))
        self.assertIn("limited room", rec.explanation.lower())

    def test_build_reserve_when_emergency_empty(self):
        self._income(Decimal("4000"))
        self._expense("Housing (estimate)", Decimal("1200"))
        self._expense("Groceries & household essentials (estimate)", Decimal("400"))
        self._expense("Subscriptions & recurring bills (estimate)", Decimal("50"))
        pools = ensure_default_pools(self.user)
        pools[Goal.SystemKey.RAINY_DAY].current_amount = Decimal("0")
        pools[Goal.SystemKey.RAINY_DAY].save()
        analysis = analyze_finances(self.user)
        self.assertGreater(analysis.safe_to_save, 0)
        self.assertEqual(choose_scenario(analysis), SavingsPlan.Scenario.BUILD_RESERVE)
        rec = build_recommendation(analysis)
        self.assertGreater(rec.rainy_day_percent, rec.investment_percent)
        self.assertLessEqual(
            rec.rainy_day_amount + rec.investment_amount + rec.regular_amount + rec.debt_extra_amount,
            analysis.safe_to_save,
        )

    def test_debt_focus_after_starter_reserve(self):
        self._income(Decimal("5000"))
        self._expense("Housing (estimate)", Decimal("1400"))
        self._expense("Utilities & internet (estimate)", Decimal("200"))
        pools = ensure_default_pools(self.user)
        pools[Goal.SystemKey.RAINY_DAY].current_amount = Decimal("1000")
        pools[Goal.SystemKey.RAINY_DAY].save()
        DebtObligation.objects.create(
            user=self.user,
            name="Card",
            balance=Decimal("3000"),
            minimum_payment=Decimal("100"),
            interest_rate_apr=Decimal("22.90"),
        )
        analysis = analyze_finances(self.user)
        self.assertEqual(choose_scenario(analysis), SavingsPlan.Scenario.DEBT_FOCUS)
        rec = build_recommendation(analysis)
        self.assertGreater(rec.debt_extra_amount, 0)
        total = rec.rainy_day_amount + rec.investment_amount + rec.regular_amount + rec.debt_extra_amount
        self.assertLessEqual(total, analysis.safe_to_save)

    def test_stable_uses_fallback_split(self):
        self._income(Decimal("6000"))
        self._expense("Housing (estimate)", Decimal("1500"))
        self._expense("Groceries & household essentials (estimate)", Decimal("400"))
        pools = ensure_default_pools(self.user)
        pools[Goal.SystemKey.RAINY_DAY].current_amount = Decimal("5000")
        pools[Goal.SystemKey.RAINY_DAY].target_amount = Decimal("4500")
        pools[Goal.SystemKey.RAINY_DAY].save()
        analysis = analyze_finances(self.user)
        # Force full target met by updating analysis path via high balance
        analysis.emergency_full_target = Decimal("4500")
        analysis.emergency_balance = Decimal("5000")
        analysis.emergency_starter_target = Decimal("1000")
        analysis.high_interest_debt_balance = Decimal("0")
        analysis.total_debt_balance = Decimal("0")
        # safe_to_save moderate → STABLE not STRONG
        analysis.safe_to_save = Decimal("400")
        analysis.monthly_income = Decimal("6000")
        self.assertEqual(choose_scenario(analysis), SavingsPlan.Scenario.STABLE)
        rec = build_recommendation(analysis)
        self.assertEqual(rec.rainy_day_percent, Decimal("40.00"))
        self.assertEqual(rec.investment_percent, Decimal("20.00"))
        self.assertEqual(rec.regular_percent, Decimal("40.00"))
        self.assertEqual(rec.rainy_day_percent + rec.investment_percent + rec.regular_percent, Decimal("100.00"))
        self.assertEqual(rec.rainy_day_amount, Decimal("160.00"))
        self.assertEqual(rec.investment_amount, Decimal("80.00"))
        self.assertEqual(rec.regular_amount, Decimal("160.00"))

    def test_strong_capacity(self):
        self._income(Decimal("8000"))
        self._expense("Housing (estimate)", Decimal("1500"))
        pools = ensure_default_pools(self.user)
        pools[Goal.SystemKey.RAINY_DAY].current_amount = Decimal("20000")
        pools[Goal.SystemKey.RAINY_DAY].save()
        analysis = analyze_finances(self.user)
        self.assertEqual(choose_scenario(analysis), SavingsPlan.Scenario.STRONG)

    def test_unrealistic_goal_is_flagged(self):
        self._income(Decimal("3000"))
        self._expense("Housing (estimate)", Decimal("2000"))
        Goal.objects.create(
            user=self.user,
            name="Yacht",
            target_amount=Decimal("50000"),
            current_amount=Decimal("0"),
            target_date=timezone.localdate() + timedelta(days=60),
        )
        analysis = analyze_finances(self.user)
        self.assertTrue(analysis.goal_advice)
        self.assertFalse(analysis.goal_advice[0].realistic)

    def test_refresh_is_idempotent_without_material_change(self):
        self._income(Decimal("4000"))
        self._expense("Housing (estimate)", Decimal("1000"))
        first = refresh_savings_plan(self.user, reason="initial", force=True)
        second = refresh_savings_plan(self.user, reason="noop")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.revisions.count(), 0)

    def test_never_allocates_more_than_safe_to_save(self):
        self._income(Decimal("2500"))
        self._expense("Housing (estimate)", Decimal("1800"))
        self._expense("Subscriptions & recurring bills (estimate)", Decimal("100"))
        analysis = analyze_finances(self.user)
        rec = build_recommendation(analysis)
        total = rec.rainy_day_amount + rec.investment_amount + rec.regular_amount + rec.debt_extra_amount
        self.assertLessEqual(total, analysis.safe_to_save)


class PlanViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="viewer", password="pw12345")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        self.client.login(username="viewer", password="pw12345")
        IncomeSource.objects.create(user=self.user, name="Pay", amount=Decimal("4000"), cadence="monthly")
        RecurringExpense.objects.create(
            user=self.user, name="Housing (estimate)", amount=Decimal("1200"), cadence="monthly"
        )

    def test_plan_page_shows_explanation(self):
        response = self.client.get(reverse("savings:plan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rainy Day")
        self.assertContains(response, "Recommendations only")
        plan = SavingsPlan.objects.get(user=self.user)
        self.assertTrue(plan.explanation)

    def test_savings_index_shows_plan_allocation(self):
        refresh_savings_plan(self.user, force=True)
        response = self.client.get(reverse("savings:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rainy Day")

    def test_pools_page_auto_creates_defaults(self):
        response = self.client.get(reverse("savings:pools"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rainy Day")
        self.assertContains(response, "Investment")
        self.assertContains(response, "Regular Savings")

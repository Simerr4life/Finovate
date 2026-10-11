"""Tests for automatic savings: capacity, allocation, default pools, and plans."""

from datetime import date
from decimal import Decimal
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import NotificationEvent
from budgets.models import Budget, BudgetPeriod, IncomeSource, RecurringExpense
from transactions.models import Category, Transaction

from .models import Contribution, Goal, SavingsPlan, SavingsPlanAllocation
from .planning import (
    allocate,
    compute_savings_capacity,
    ensure_default_pools,
    per_period,
    pool_plan_rows,
    recalculate_plan,
)

DEFAULTS = {"rainy_day": 40, "investment": 20, "regular": 40}


def _income(user, amount, cadence="monthly", name="Salary"):
    return IncomeSource.objects.create(user=user, name=name, amount=Decimal(amount), cadence=cadence)


def _expense(user, amount, name="Rent", cadence="monthly", category=None):
    return RecurringExpense.objects.create(
        user=user, name=name, amount=Decimal(amount), cadence=cadence, category=category
    )


class DefaultPoolCreationTests(TestCase):
    def test_new_user_gets_exactly_three_default_pools_and_one_plan(self):
        user = User.objects.create_user(username="new-user", password="x")
        pools = Goal.objects.filter(user=user).exclude(pool_kind="")
        self.assertEqual(
            sorted(pools.values_list("pool_kind", flat=True)), ["investment", "rainy_day", "regular"]
        )
        self.assertEqual(
            sorted(pools.values_list("name", flat=True)), ["Investment", "Rainy Day", "Regular Savings"]
        )
        self.assertTrue(pools.get(pool_kind="investment").is_investable)
        self.assertTrue(all(p.current_amount == 0 and p.target_amount == 0 for p in pools))
        self.assertEqual(SavingsPlan.objects.filter(user=user).count(), 1)

    def test_repeated_initialization_never_duplicates_pools(self):
        user = User.objects.create_user(username="repeat-user", password="x")
        for _ in range(3):
            ensure_default_pools(user)
            recalculate_plan(user)
        self.assertEqual(Goal.objects.filter(user=user).exclude(pool_kind="").count(), 3)
        self.assertEqual(SavingsPlan.objects.filter(user=user).count(), 1)
        self.assertEqual(SavingsPlanAllocation.objects.filter(plan__user=user).count(), 3)

    def test_existing_pools_and_balances_are_never_reset(self):
        user = User.objects.create_user(username="keep-user", password="x")
        rainy = Goal.objects.get(user=user, pool_kind="rainy_day")
        rainy.name = "My cushion"
        rainy.current_amount = Decimal("812.40")
        rainy.target_amount = Decimal("3000")
        rainy.save()
        ensure_default_pools(user)
        recalculate_plan(user)
        rainy.refresh_from_db()
        self.assertEqual(rainy.name, "My cushion")
        self.assertEqual(rainy.current_amount, Decimal("812.40"))
        self.assertEqual(rainy.target_amount, Decimal("3000.00"))

    def test_backfill_migration_adds_pools_for_existing_users_without_duplicates(self):
        user = User.objects.create_user(username="legacy-user", password="x")
        # Simulate an account created before default pools existed.
        Goal.objects.filter(user=user).delete()
        SavingsPlan.objects.filter(user=user).delete()
        emergency = Goal.objects.create(
            user=user, name="Emergency fund", category="emergency",
            target_amount=Decimal("5000"), current_amount=Decimal("1250"),
        )
        vacation = Goal.objects.create(user=user, name="Vacation", target_amount=Decimal("900"))
        backfill = import_module("savings.migrations.0004_backfill_default_pools").backfill

        backfill(django_apps, None)
        backfill(django_apps, None)  # re-running is harmless

        defaults = Goal.objects.filter(user=user).exclude(pool_kind="")
        self.assertEqual(defaults.count(), 3)
        emergency.refresh_from_db()
        self.assertEqual(emergency.pool_kind, "rainy_day")  # adopted, not duplicated
        self.assertEqual(emergency.current_amount, Decimal("1250.00"))
        self.assertEqual(emergency.name, "Emergency fund")
        vacation.refresh_from_db()
        self.assertEqual(vacation.pool_kind, "")
        self.assertEqual(SavingsPlan.objects.filter(user=user).count(), 1)


class AllocationTests(TestCase):
    def test_default_split_of_500(self):
        self.assertEqual(
            allocate(Decimal("500"), DEFAULTS),
            {"rainy_day": Decimal("200.00"), "investment": Decimal("100.00"), "regular": Decimal("200.00")},
        )

    def test_rounding_never_exceeds_available_and_uses_every_cent(self):
        for raw in ["0.01", "0.05", "1.00", "33.33", "100.01", "999.99", "1234.567", "77.77"]:
            available = Decimal(raw)
            shares = allocate(available, DEFAULTS)
            total = sum(shares.values())
            self.assertLessEqual(total, available, raw)
            self.assertEqual(total, available.quantize(Decimal("0.01"), rounding="ROUND_DOWN"), raw)
            for value in shares.values():
                self.assertEqual(value, value.quantize(Decimal("0.01")))
                self.assertGreaterEqual(value, 0)

    def test_leftover_cent_goes_to_largest_remainder(self):
        shares = allocate(Decimal("33.33"), DEFAULTS)
        # 13.332 / 6.666 / 13.332 -> 13.33 / 6.67 / 13.33
        self.assertEqual(shares, {"rainy_day": Decimal("13.33"), "investment": Decimal("6.67"), "regular": Decimal("13.33")})

    def test_zero_or_negative_available_allocates_nothing(self):
        self.assertEqual(set(allocate(Decimal("0"), DEFAULTS).values()), {Decimal("0.00")})
        self.assertEqual(set(allocate(Decimal("-250"), DEFAULTS).values()), {Decimal("0.00")})

    def test_custom_percentages_and_validation(self):
        self.assertEqual(
            allocate(Decimal("1000"), {"rainy_day": 50, "investment": 0, "regular": 50}),
            {"rainy_day": Decimal("500.00"), "investment": Decimal("0.00"), "regular": Decimal("500.00")},
        )
        with self.assertRaises(ValueError):
            allocate(Decimal("100"), {"rainy_day": 50, "investment": 20, "regular": 40})

    def test_weekly_cadence_rounds_down(self):
        self.assertEqual(per_period(Decimal("100.00"), "weekly"), Decimal("23.07"))
        self.assertEqual(per_period(Decimal("100.00"), "monthly"), Decimal("100.00"))


class SavingsCapacityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cap-user", password="x")

    def test_available_is_income_minus_costs_and_obligations(self):
        _income(self.user, "4000")
        _expense(self.user, "1500", "Rent")
        _expense(self.user, "200", "Car loan")
        groceries = Category.objects.create(user=self.user, name="Groceries", kind="expense")
        period = BudgetPeriod.objects.create(
            user=self.user, name="Now", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31)
        )
        Budget.objects.create(user=self.user, period=period, category=groceries, limit_amount=Decimal("300"))
        capacity = compute_savings_capacity(self.user)
        self.assertTrue(capacity.is_complete)
        self.assertEqual(capacity.monthly_income, Decimal("4000.00"))
        self.assertEqual(capacity.total_costs, Decimal("2000.00"))
        self.assertEqual(capacity.available, Decimal("2000.00"))
        self.assertEqual(capacity.shortfall, Decimal("0.00"))

    def test_budget_for_a_category_already_recurring_is_not_double_counted(self):
        utilities = Category.objects.create(user=self.user, name="Utilities", kind="expense")
        _income(self.user, "3000")
        _expense(self.user, "150", "Power", category=utilities)
        period = BudgetPeriod.objects.create(
            user=self.user, name="Now", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31)
        )
        Budget.objects.create(user=self.user, period=period, category=utilities, limit_amount=Decimal("200"))
        self.assertEqual(compute_savings_capacity(self.user).total_costs, Decimal("150.00"))

    def test_irregular_income_is_not_treated_as_available_cash(self):
        _income(self.user, "2000")
        _income(self.user, "5000", cadence="irregular", name="Possible bonus")
        _expense(self.user, "1000")
        capacity = compute_savings_capacity(self.user)
        self.assertEqual(capacity.monthly_income, Decimal("2000.00"))
        self.assertEqual(capacity.available, Decimal("1000.00"))
        self.assertEqual([line.label for line in capacity.excluded_lines], ["Possible bonus"])

    def test_weekly_income_normalized_to_monthly(self):
        _income(self.user, "1000", cadence="weekly")
        _expense(self.user, "2000")
        self.assertEqual(compute_savings_capacity(self.user).available, Decimal("2330.00"))

    def test_shortfall_never_produces_positive_savings(self):
        _income(self.user, "1000")
        _expense(self.user, "1500")
        capacity = compute_savings_capacity(self.user)
        self.assertEqual(capacity.available, Decimal("0.00"))
        self.assertEqual(capacity.shortfall, Decimal("500.00"))
        result = recalculate_plan(self.user)
        self.assertEqual(
            set(result.plan.allocations.values_list("recommended_monthly", flat=True)), {Decimal("0.00")}
        )
        self.assertIn("can't support savings", NotificationEvent.objects.get(user=self.user).message)

    def test_missing_data_asks_instead_of_inventing(self):
        capacity = compute_savings_capacity(self.user)
        self.assertFalse(capacity.is_complete)
        self.assertEqual(capacity.available, Decimal("0.00"))
        self.assertTrue(capacity.missing)

        _income(self.user, "3000")
        capacity = compute_savings_capacity(self.user)
        self.assertFalse(capacity.is_complete, "income without any expenses must not become 'all savings'")
        self.assertEqual(capacity.available, Decimal("0.00"))

    def test_zero_income_with_expenses_is_incomplete_not_negative(self):
        _expense(self.user, "900")
        capacity = compute_savings_capacity(self.user)
        self.assertFalse(capacity.is_complete)
        self.assertEqual(capacity.available, Decimal("0.00"))

    def test_recorded_transactions_are_used_when_nothing_is_declared(self):
        salary = Category.objects.create(user=self.user, name="Salary", kind="income")
        refund = Category.objects.create(user=self.user, name="Refund", kind="income", is_earned_income=False)
        for month in (7, 8, 9):
            Transaction.objects.create(user=self.user, kind="income", amount=Decimal("3000"), category=salary, occurred_on=date(2026, month, 1))
            Transaction.objects.create(user=self.user, kind="expense", amount=Decimal("2100"), occurred_on=date(2026, month, 5))
        Transaction.objects.create(user=self.user, kind="income", amount=Decimal("600"), category=refund, occurred_on=date(2026, 8, 3))
        # Current (incomplete) month is ignored.
        Transaction.objects.create(user=self.user, kind="expense", amount=Decimal("9999"), occurred_on=date(2026, 10, 2))
        capacity = compute_savings_capacity(self.user, today=date(2026, 10, 11))
        self.assertEqual(capacity.basis, "recorded")
        self.assertEqual(capacity.monthly_income, Decimal("3000.00"))
        self.assertEqual(capacity.total_costs, Decimal("2100.00"))
        self.assertEqual(capacity.available, Decimal("900.00"))


class PlanRecalculationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="plan-user", password="x")
        _income(self.user, "3000")
        self.rent = _expense(self.user, "2500")

    def _amounts(self):
        plan = SavingsPlan.objects.get(user=self.user)
        return {a.pool.pool_kind: a.recommended_monthly for a in plan.allocations.select_related("pool")}

    def test_initial_plan_uses_default_percentages(self):
        recalculate_plan(self.user)
        self.assertEqual(self._amounts(), {"rainy_day": Decimal("200.00"), "investment": Decimal("100.00"), "regular": Decimal("200.00")})

    def test_repeated_recalculation_is_idempotent(self):
        for _ in range(4):
            recalculate_plan(self.user)
        self.assertEqual(SavingsPlan.objects.filter(user=self.user).count(), 1)
        self.assertEqual(SavingsPlanAllocation.objects.filter(plan__user=self.user).count(), 3)
        self.assertEqual(NotificationEvent.objects.filter(user=self.user, event_type="savings_plan").count(), 1)
        # Recommendations are never deposits or transactions.
        self.assertFalse(Contribution.objects.filter(user=self.user).exists())
        self.assertEqual(Goal.objects.filter(user=self.user, current_amount__gt=0).count(), 0)

    def test_expense_change_recalculates_through_signal(self):
        recalculate_plan(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            self.rent.amount = Decimal("2000")
            self.rent.save()
        self.assertEqual(self._amounts()["rainy_day"], Decimal("400.00"))
        self.assertEqual(NotificationEvent.objects.filter(user=self.user, event_type="savings_plan").count(), 2)

    def test_income_change_recalculates_through_signal(self):
        recalculate_plan(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            _income(self.user, "500", name="Side job")
        self.assertEqual(SavingsPlan.objects.get(user=self.user).available_monthly, Decimal("1000.00"))

    def test_paused_and_disabled_plans(self):
        plan = recalculate_plan(self.user).plan
        plan.status = SavingsPlan.Status.PAUSED
        plan.save()
        recalculate_plan(self.user)
        self.assertTrue(all(row.recommended_monthly == 0 for row in pool_plan_rows(plan)))
        plan.status = SavingsPlan.Status.DISABLED
        plan.save()
        recalculate_plan(self.user)
        self.assertEqual(set(self._amounts().values()), {Decimal("0.00")})

    def test_completion_estimate_and_unreachable_target(self):
        recalculate_plan(self.user)
        rainy = Goal.objects.get(user=self.user, pool_kind="rainy_day")
        rainy.target_amount = Decimal("1000")
        rainy.current_amount = Decimal("100")
        rainy.target_date = date(2026, 11, 30)
        rainy.save()
        plan = SavingsPlan.objects.get(user=self.user)
        row = next(r for r in pool_plan_rows(plan, today=date(2026, 10, 11)) if r.pool == rainy)
        self.assertEqual(row.estimated_completion, date(2027, 3, 1))  # 900 / 200 -> 5 months
        self.assertTrue(row.target_unreachable)


class SavingsViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="view-user", password="x")
        self.other = User.objects.create_user(username="other-user", password="x")
        self.client.force_login(self.user)
        _income(self.user, "4000")
        _expense(self.user, "3500")

    def test_pools_page_shows_three_default_pools_with_recommendations(self):
        response = self.client.get(reverse("savings:pools"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row.pool.pool_kind for row in response.context["plan_rows"]], ["rainy_day", "investment", "regular"])
        self.assertContains(response, "$200.00")  # 40% of $500
        self.assertContains(response, "$100.00")  # 20% of $500

    def test_savings_center_explains_the_calculation(self):
        response = self.client.get(reverse("savings:index"))
        self.assertContains(response, "Available to save")
        self.assertContains(response, "$500.00")
        self.assertContains(response, "income − costs")

    def test_plan_update_rejects_percentages_that_dont_total_100(self):
        response = self.client.post(reverse("savings:plan_update"), {
            "rainy_day_percent": 50, "investment_percent": 30, "regular_percent": 30,
            "cadence": "monthly", "status": "active",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SavingsPlan.objects.get(user=self.user).rainy_day_percent, 40)

    def test_plan_update_saves_and_recalculates(self):
        response = self.client.post(reverse("savings:plan_update"), {
            "rainy_day_percent": 60, "investment_percent": 10, "regular_percent": 30,
            "cadence": "weekly", "status": "active",
        })
        self.assertRedirects(response, reverse("savings:pools") + "#plan", fetch_redirect_response=False)
        plan = SavingsPlan.objects.get(user=self.user)
        self.assertEqual((plan.rainy_day_percent, plan.cadence), (60, "weekly"))
        rainy = plan.allocations.get(pool__pool_kind="rainy_day")
        self.assertEqual(rainy.recommended_monthly, Decimal("300.00"))

    def test_plan_update_requires_post(self):
        self.assertEqual(self.client.get(reverse("savings:plan_update")).status_code, 405)

    def test_suggested_target_applies_three_months_of_costs(self):
        rainy = Goal.objects.get(user=self.user, pool_kind="rainy_day")
        self.client.post(reverse("savings:apply_suggested_target", args=[rainy.pk]))
        rainy.refresh_from_db()
        self.assertEqual(rainy.target_amount, Decimal("10500.00"))

    def test_cannot_touch_another_users_pool(self):
        theirs = Goal.objects.get(user=self.other, pool_kind="rainy_day")
        self.assertEqual(self.client.post(reverse("savings:apply_suggested_target", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("savings:goal_detail", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("savings:goal_detail", args=[theirs.pk]), {"kind": "contribution", "amount": "5"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("savings:goal_edit", args=[theirs.pk]), {"name": "x", "target_amount": "1"}).status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual((theirs.target_amount, theirs.current_amount), (Decimal("0.00"), Decimal("0.00")))

    def test_default_pool_cannot_be_deleted(self):
        rainy = Goal.objects.get(user=self.user, pool_kind="rainy_day")
        self.client.post(reverse("savings:goal_delete", args=[rainy.pk]))
        self.assertTrue(Goal.objects.filter(pk=rainy.pk).exists())

    def test_duplicate_deposit_submission_is_recorded_once(self):
        rainy = Goal.objects.get(user=self.user, pool_kind="rainy_day")
        data = {"kind": "contribution", "amount": "50.00", "note": "", "idempotency_key": "abc123"}
        self.client.post(reverse("savings:goal_detail", args=[rainy.pk]), data)
        self.client.post(reverse("savings:goal_detail", args=[rainy.pk]), data)
        rainy.refresh_from_db()
        self.assertEqual(rainy.current_amount, Decimal("50.00"))
        self.assertEqual(rainy.contributions.count(), 1)
        self.assertIsNone(rainy.achieved_at, "a pool without a target is never 'achieved'")

    def test_withdrawal_larger_than_balance_is_rejected(self):
        rainy = Goal.objects.get(user=self.user, pool_kind="rainy_day")
        response = self.client.post(reverse("savings:goal_detail", args=[rainy.pk]), {"kind": "withdrawal", "amount": "10.00"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You can withdraw at most")
        self.assertFalse(rainy.contributions.exists())

    def test_dashboard_shows_available_savings(self):
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Available to save")
        self.assertContains(response, "Savings plan")


class ManualSetupNotificationTests(TestCase):
    def test_one_setup_submission_produces_one_plan_notification(self):
        from accounts.manual_setup import apply_manual_setup

        user = User.objects.create_user(username="setup-user", password="x")
        with self.captureOnCommitCallbacks(execute=True):
            apply_manual_setup(user, {
                "take_home_income": Decimal("4200"), "housing": Decimal("1500"),
                "utilities": Decimal("180"), "groceries": Decimal("455"),
            })
        events = NotificationEvent.objects.filter(user=user, event_type="savings_plan")
        self.assertEqual(events.count(), 1)
        self.assertIn("$2,065.00/month", events.get().message)

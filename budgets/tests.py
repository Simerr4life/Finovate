from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from transactions.models import Category, Transaction

from .models import Budget, BudgetPeriod, IncomeSource, RecurringExpense
from .services import build_budget_plan, compute_budget_progress, monthly_equivalent, monthly_summary


class PerUserDataIsolationTests(TestCase):
    """A user must never be able to view or edit another user's records."""

    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pw12345")
        self.bob = User.objects.create_user(username="bob", password="pw12345")
        self.alice_txn = Transaction.objects.create(
            user=self.alice, kind=Transaction.Kind.EXPENSE, amount=Decimal("10.00"), occurred_on=date(2026, 1, 1)
        )

    def test_user_cannot_see_another_users_transaction_in_list(self):
        self.client.force_login(self.bob)
        response = self.client.get("/budgets/transactions/")
        self.assertNotContains(response, "10.00")

    def test_user_cannot_edit_another_users_transaction(self):
        self.client.force_login(self.bob)
        response = self.client.get(f"/budgets/transactions/{self.alice_txn.pk}/edit/")
        self.assertEqual(response.status_code, 404)


class MonthlyEquivalentTests(TestCase):
    def test_weekly_and_biweekly_scale_up(self):
        self.assertEqual(monthly_equivalent(Decimal("100"), "weekly"), Decimal("433.00"))
        self.assertEqual(monthly_equivalent(Decimal("100"), "biweekly"), Decimal("217.00"))
        self.assertEqual(monthly_equivalent(Decimal("100"), "monthly"), Decimal("100.00"))


class BudgetProgressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.category = Category.objects.create(user=self.user, name="Groceries", kind="expense")
        self.period = BudgetPeriod.objects.create(
            user=self.user, name="Test month", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
        )
        self.budget = Budget.objects.create(
            user=self.user, period=self.period, category=self.category,
            limit_amount=Decimal("100.00"), warning_threshold_percent=80,
        )

    def _spend(self, amount, on=date(2026, 1, 10)):
        Transaction.objects.create(
            user=self.user, category=self.category, kind=Transaction.Kind.EXPENSE,
            amount=amount, occurred_on=on,
        )

    def test_under_budget(self):
        self._spend(Decimal("50.00"))
        progress = compute_budget_progress(self.budget)
        self.assertEqual(progress.spent_amount, Decimal("50.00"))
        self.assertEqual(progress.remaining_amount, Decimal("50.00"))
        self.assertFalse(progress.is_warning)
        self.assertFalse(progress.is_over)

    def test_warning_threshold(self):
        self._spend(Decimal("85.00"))
        progress = compute_budget_progress(self.budget)
        self.assertTrue(progress.is_warning)
        self.assertFalse(progress.is_over)

    def test_over_budget(self):
        self._spend(Decimal("120.00"))
        progress = compute_budget_progress(self.budget)
        self.assertTrue(progress.is_over)

    def test_spending_outside_period_is_excluded(self):
        self._spend(Decimal("30.00"), on=date(2025, 12, 1))
        progress = compute_budget_progress(self.budget)
        self.assertEqual(progress.spent_amount, Decimal("0.00"))


class BudgetPlanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")

    def test_plan_combines_income_and_expenses(self):
        IncomeSource.objects.create(user=self.user, name="Job", amount=Decimal("1000"), cadence="monthly")
        RecurringExpense.objects.create(user=self.user, name="Rent", amount=Decimal("600"), cadence="monthly")
        plan = build_budget_plan(self.user, Decimal("100"))
        self.assertEqual(plan.monthly_income, Decimal("1000.00"))
        self.assertEqual(plan.monthly_recurring_expenses, Decimal("600.00"))
        self.assertEqual(plan.monthly_goal_target, Decimal("100.00"))
        self.assertEqual(plan.leftover_after_plan, Decimal("300.00"))

    def test_inactive_sources_are_excluded(self):
        IncomeSource.objects.create(user=self.user, name="Old job", amount=Decimal("500"), cadence="monthly", is_active=False)
        plan = build_budget_plan(self.user)
        self.assertEqual(plan.monthly_income, Decimal("0.00"))

    def test_plan_recalculates_when_inputs_change(self):
        src = IncomeSource.objects.create(user=self.user, name="Job", amount=Decimal("1000"), cadence="monthly")
        plan_before = build_budget_plan(self.user)
        src.amount = Decimal("1200")
        src.save()
        plan_after = build_budget_plan(self.user)
        self.assertEqual(plan_before.monthly_income, Decimal("1000.00"))
        self.assertEqual(plan_after.monthly_income, Decimal("1200.00"))


class MonthlySummaryTests(TestCase):
    """Covers the 'don't assume Venmo is a raise' requirement: earned
    income and transfers/reimbursements must never be summed together."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.wages = Category.objects.create(user=self.user, name="Wages", kind="income", is_earned_income=True)
        self.reimbursement = Category.objects.create(user=self.user, name="Reimbursement", kind="income", is_earned_income=False)
        self.groceries = Category.objects.create(user=self.user, name="Groceries", kind="expense")
        self.dining = Category.objects.create(user=self.user, name="Dining", kind="expense")

    def _txn(self, kind, amount, category, day=15):
        Transaction.objects.create(
            user=self.user, kind=kind, amount=amount, category=category, occurred_on=date(2026, 9, day)
        )

    def test_earned_and_transfer_income_are_kept_separate(self):
        self._txn(Transaction.Kind.INCOME, Decimal("3000.00"), self.wages)
        self._txn(Transaction.Kind.INCOME, Decimal("40.00"), self.reimbursement)
        summary = monthly_summary(self.user, 2026, 9)
        self.assertEqual(summary.earned_income, Decimal("3000.00"))
        self.assertEqual(summary.transfer_income, Decimal("40.00"))

    def test_expenses_grouped_by_category_without_double_counting(self):
        self._txn(Transaction.Kind.EXPENSE, Decimal("50.00"), self.groceries)
        self._txn(Transaction.Kind.EXPENSE, Decimal("30.00"), self.groceries)
        self._txn(Transaction.Kind.EXPENSE, Decimal("20.00"), self.dining)
        summary = monthly_summary(self.user, 2026, 9)
        totals = {row.category_name: row.total for row in summary.expense_by_category}
        self.assertEqual(totals["Groceries"], Decimal("80.00"))
        self.assertEqual(totals["Dining"], Decimal("20.00"))
        self.assertEqual(summary.total_expenses, Decimal("100.00"))

    def test_net_cash_flow_includes_transfers_but_labels_them_separately(self):
        self._txn(Transaction.Kind.INCOME, Decimal("1000.00"), self.wages)
        self._txn(Transaction.Kind.INCOME, Decimal("50.00"), self.reimbursement)
        self._txn(Transaction.Kind.EXPENSE, Decimal("200.00"), self.groceries)
        summary = monthly_summary(self.user, 2026, 9)
        self.assertEqual(summary.net_cash_flow, Decimal("850.00"))

    def test_transactions_outside_the_month_are_excluded(self):
        self._txn(Transaction.Kind.EXPENSE, Decimal("10.00"), self.groceries, day=1)
        other_month_txn = Transaction.objects.create(
            user=self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("999.00"),
            category=self.groceries, occurred_on=date(2026, 8, 31),
        )
        summary = monthly_summary(self.user, 2026, 9)
        self.assertEqual(summary.total_expenses, Decimal("10.00"))
        self.assertTrue(Transaction.objects.filter(pk=other_month_txn.pk).exists())

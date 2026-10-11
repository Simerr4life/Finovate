"""Regressions found in the codebase audit for the budgeting pages."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from transactions.models import Category, Transaction

from .forms import BudgetForm
from .models import BudgetPeriod, IncomeSource


class BudgetPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="budgeter", password="pw-12345-x")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        self.client.force_login(self.user)

    def test_duplicate_category_shows_an_error_instead_of_crashing(self):
        Category.objects.create(user=self.user, name="Groceries", kind="expense")
        response = self.client.post(
            reverse("budgets:category_add"),
            {"name": "groceries", "kind": "expense", "color": "#112233"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already have a category with that name")
        self.assertEqual(Category.objects.filter(user=self.user).count(), 1)

    def test_same_name_is_allowed_for_the_other_kind(self):
        Category.objects.create(user=self.user, name="Refunds", kind="expense")
        self.client.post(reverse("budgets:category_add"), {"name": "Refunds", "kind": "income", "color": "#112233"})
        self.assertEqual(Category.objects.filter(user=self.user, name="Refunds").count(), 2)

    def test_invalid_income_source_reports_why(self):
        response = self.client.post(
            reverse("budgets:income_add"),
            {"name": "Paycheck", "amount": "-100", "cadence": "monthly", "is_active": "on"},
            follow=True,
        )
        self.assertContains(response, "Couldn&#x27;t add that income source")
        self.assertContains(response, "greater than $0.00")
        self.assertFalse(IncomeSource.objects.filter(user=self.user).exists())

    def test_period_must_not_end_before_it_starts(self):
        response = self.client.post(
            reverse("budgets:period_add"),
            {"name": "Backwards", "start_date": "2026-10-31", "end_date": "2026-10-01", "is_active": "on"},
            follow=True,
        )
        self.assertContains(response, "on or after the start date")
        self.assertFalse(BudgetPeriod.objects.filter(user=self.user).exists())

    def test_new_budget_defaults_to_the_profile_warning_threshold(self):
        self.user.profile.budget_warning_threshold_percent = 65
        self.user.profile.save()
        form = BudgetForm(user=self.user)
        self.assertEqual(form.initial["warning_threshold_percent"], 65)

    def test_budget_threshold_and_limit_are_bounded(self):
        period = BudgetPeriod.objects.create(
            user=self.user, name="Oct", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31)
        )
        category = Category.objects.create(user=self.user, name="Dining", kind="expense")
        form = BudgetForm(
            {"period": period.pk, "category": category.pk, "limit_amount": "0", "warning_threshold_percent": "150"},
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("limit_amount", form.errors)
        self.assertIn("warning_threshold_percent", form.errors)


class TransactionFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="txn-user", password="pw-12345-x")
        self.client.force_login(self.user)

    def test_negative_amount_is_rejected(self):
        response = self.client.post(
            reverse("budgets:transaction_add"),
            {"kind": "expense", "amount": "-20", "description": "x", "occurred_on": "2026-10-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "greater than $0.00")
        self.assertFalse(Transaction.objects.exists())

    def test_category_must_match_kind(self):
        salary = Category.objects.create(user=self.user, name="Salary", kind="income")
        response = self.client.post(
            reverse("budgets:transaction_add"),
            {"kind": "expense", "category": salary.pk, "amount": "20", "occurred_on": "2026-10-01"},
        )
        self.assertContains(response, "income category")
        self.assertFalse(Transaction.objects.exists())

    def test_edit_page_links_to_delete(self):
        txn = Transaction.objects.create(
            user=self.user, kind="expense", amount=Decimal("5.00"), occurred_on=date(2026, 10, 1)
        )
        response = self.client.get(reverse("budgets:transaction_edit", args=[txn.pk]))
        self.assertContains(response, reverse("budgets:transaction_delete", args=[txn.pk]))
        self.client.post(reverse("budgets:transaction_delete", args=[txn.pk]))
        self.assertFalse(Transaction.objects.filter(pk=txn.pk).exists())

    def test_export_link_encodes_the_search(self):
        response = self.client.get(reverse("budgets:transaction_list"), {"q": "A&B"})
        self.assertContains(response, "?q=A%26B&amp;category=")

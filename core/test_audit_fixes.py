"""Regressions found in the codebase audit for dashboard and insights."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.display import add_months, cash_series, month_start
from core.templatetags.finovate import money
from transactions.models import Category, Transaction


class InsightsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="insightful", password="pw-12345-x")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        self.client.force_login(self.user)

    def test_category_with_no_spend_this_month_counts_as_a_decrease(self):
        dining = Category.objects.create(user=self.user, name="Dining", kind="expense")
        groceries = Category.objects.create(user=self.user, name="Groceries", kind="expense")
        today = timezone.now().date()
        last_month = add_months(month_start(today), -1)
        Transaction.objects.create(user=self.user, kind="expense", category=dining, amount=Decimal("200"), occurred_on=last_month)
        Transaction.objects.create(user=self.user, kind="expense", category=groceries, amount=Decimal("50"), occurred_on=last_month)
        Transaction.objects.create(user=self.user, kind="expense", category=groceries, amount=Decimal("60"), occurred_on=today)
        response = self.client.get(reverse("insights"))
        self.assertEqual(response.context["decreased"]["name"], "Dining")
        self.assertEqual(response.context["decreased"]["delta"], Decimal("-200.00"))
        self.assertEqual(response.context["increased"]["name"], "Groceries")


class ChartRangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="charter", password="pw-12345-x")

    def test_one_month_range_has_daily_points(self):
        today = timezone.now().date()
        Transaction.objects.create(user=self.user, kind="income", amount=Decimal("100"), occurred_on=today - timedelta(days=40))
        Transaction.objects.create(user=self.user, kind="expense", amount=Decimal("30"), occurred_on=today - timedelta(days=3))
        labels, points = cash_series(self.user, "1M")
        self.assertEqual(len(points), 30)
        self.assertEqual(len(labels), 30)
        self.assertEqual(points[0], Decimal("100.00"))
        self.assertEqual(points[-1], Decimal("70.00"))

    def test_week_range_is_unchanged(self):
        labels, points = cash_series(self.user, "1W")
        self.assertEqual(len(points), 7)
        self.assertTrue(all(labels))


class MoneyFilterTests(TestCase):
    def test_negative_amounts_put_the_sign_before_the_dollar(self):
        self.assertEqual(money(Decimal("-1234.5")), "-$1,234.50")
        self.assertEqual(money(Decimal("1234.5")), "$1,234.50")
        self.assertEqual(money(None), "$0.00")

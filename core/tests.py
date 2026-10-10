from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from core.services import quantize_money, round_up_to_nearest


class RoundUpMathTests(TestCase):
    def test_example_from_spec(self):
        # A $4.35 eligible purchase rounds up by $0.65 to the next dollar.
        self.assertEqual(round_up_to_nearest(Decimal("4.35"), Decimal("1.00")), Decimal("0.65"))

    def test_exact_multiple_rounds_up_to_zero(self):
        self.assertEqual(round_up_to_nearest(Decimal("5.00"), Decimal("1.00")), Decimal("0.00"))

    def test_custom_round_to_increment(self):
        # Rounding to the nearest quarter.
        self.assertEqual(round_up_to_nearest(Decimal("4.10"), Decimal("0.25")), Decimal("0.15"))

    def test_zero_round_to_returns_zero(self):
        self.assertEqual(round_up_to_nearest(Decimal("4.35"), Decimal("0")), Decimal("0.00"))

    def test_quantize_money_rounds_to_two_places(self):
        self.assertEqual(quantize_money(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(quantize_money(Decimal("1.004")), Decimal("1.00"))


class EmptyStateTests(TestCase):
    """The dashboard and related pages must not error for a brand-new
    account with no transactions, budgets, goals, or round-up history."""

    def setUp(self):
        self.user = User.objects.create_user(username="newbie", password="x")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        self.client.force_login(self.user)

    def test_dashboard_with_zero_transactions(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No transactions yet")

    def test_budgets_page_with_no_data(self):
        response = self.client.get("/budgets/")
        self.assertEqual(response.status_code, 200)

    def test_savings_page_with_no_goals(self):
        response = self.client.get("/savings/")
        self.assertEqual(response.status_code, 200)

    def test_investing_page_with_no_roundups(self):
        response = self.client.get("/investing/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No round-ups yet")

    def test_statement_list_with_no_accounts(self):
        response = self.client.get("/statements/")
        self.assertEqual(response.status_code, 200)

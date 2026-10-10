from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Contribution, Goal
from .services import apply_contribution, estimate_completion_date


class ContributionMilestoneTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.goal = Goal.objects.create(
            user=self.user, name="Emergency fund", target_amount=Decimal("100.00")
        )

    def test_contribution_increases_current_amount(self):
        apply_contribution(self.goal, kind=Contribution.Kind.CONTRIBUTION, amount=Decimal("25.00"))
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_amount, Decimal("25.00"))

    def test_crossing_25_percent_is_reported_once(self):
        _, crossed = apply_contribution(self.goal, kind=Contribution.Kind.CONTRIBUTION, amount=Decimal("25.00"))
        self.assertEqual(crossed, 25)
        # Adding $1 more shouldn't re-trigger the 25% milestone.
        _, crossed_again = apply_contribution(self.goal, kind=Contribution.Kind.CONTRIBUTION, amount=Decimal("1.00"))
        self.assertIsNone(crossed_again)

    def test_crossing_multiple_milestones_in_one_jump_reports_highest(self):
        _, crossed = apply_contribution(self.goal, kind=Contribution.Kind.CONTRIBUTION, amount=Decimal("80.00"))
        self.assertEqual(crossed, 75)

    def test_reaching_target_sets_achieved_at(self):
        apply_contribution(self.goal, kind=Contribution.Kind.CONTRIBUTION, amount=Decimal("100.00"))
        self.goal.refresh_from_db()
        self.assertIsNotNone(self.goal.achieved_at)

    def test_withdrawal_cannot_take_balance_negative(self):
        apply_contribution(self.goal, kind=Contribution.Kind.CONTRIBUTION, amount=Decimal("10.00"))
        apply_contribution(self.goal, kind=Contribution.Kind.WITHDRAWAL, amount=Decimal("50.00"))
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_amount, Decimal("0.00"))


class CompletionEstimateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.goal = Goal.objects.create(
            user=self.user, name="Trip", target_amount=Decimal("1000.00")
        )

    def test_no_contributions_yields_no_estimate(self):
        self.assertIsNone(estimate_completion_date(self.goal))

    def test_positive_pace_yields_an_estimate(self):
        apply_contribution(self.goal, kind=Contribution.Kind.CONTRIBUTION, amount=Decimal("100.00"))
        self.assertIsNotNone(estimate_completion_date(self.goal))

    def test_already_achieved_goal_has_no_estimate(self):
        apply_contribution(self.goal, kind=Contribution.Kind.CONTRIBUTION, amount=Decimal("1000.00"))
        self.assertIsNone(estimate_completion_date(self.goal))

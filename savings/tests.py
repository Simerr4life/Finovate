from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Contribution, Goal
from .services import apply_contribution, contribution_pace, estimate_completion_date


class PoolsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pool-user", password="test-password")
        self.client.force_login(self.user)

    def test_pools_page_shows_only_the_users_shared_savings_goals(self):
        goal = Goal.objects.create(
            user=self.user,
            name="Vacation",
            target_amount=Decimal("1000.00"),
            current_amount=Decimal("250.00"),
        )
        other_user = User.objects.create_user(username="other-pool-user", password="test-password")
        Goal.objects.create(
            user=other_user,
            name="Private goal",
            target_amount=Decimal("500.00"),
        )

        response = self.client.get(reverse("savings:pools"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["nav_active"], "pools")
        pool_goals = [row["goal"] for row in response.context["pool_rows"]]
        self.assertIn(goal, pool_goals)
        self.assertTrue(all(g.user_id == self.user.id for g in pool_goals))
        self.assertNotIn("Private goal", [g.name for g in pool_goals])
        # Default Rainy Day / Investment / Regular pools are auto-created at $0.
        self.assertEqual(response.context["saved_total"], Decimal("250.00"))
        self.assertGreaterEqual(len(pool_goals), 4)

    def test_creating_a_pool_uses_the_shared_savings_goal_and_returns_to_pools(self):
        response = self.client.post(
            f"{reverse('savings:goal_add')}?from=pools",
            {
                "from": "pools",
                "name": "New car",
                "category": Goal.Category.VEHICLE,
                "color": "#6366F1",
                "target_amount": "5000.00",
                "current_amount": "200.00",
                "target_date": "",
            },
        )

        self.assertRedirects(response, reverse("savings:pools"))
        goal = Goal.objects.get(user=self.user, name="New car")
        pools_response = self.client.get(reverse("savings:pools"))
        savings_response = self.client.get(reverse("savings:index"))
        self.assertContains(pools_response, "New car")
        self.assertEqual(pools_response.context["saved_total"], Decimal("200.00"))
        self.assertEqual(savings_response.context["saved_total"], Decimal("200.00"))
        self.assertEqual(goal.current_amount, Decimal("200.00"))


class FinancialGoalsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="goals-user", password="test-password")
        self.client.force_login(self.user)

    def test_goals_page_shows_deadline_based_contribution_plan_and_milestone(self):
        goal = Goal.objects.create(
            user=self.user,
            name="Vacation",
            target_amount=Decimal("1000.00"),
            current_amount=Decimal("250.00"),
            target_date=timezone.localdate() + timedelta(days=100),
        )

        response = self.client.get(reverse("savings:goals"))
        row = response.context["goal_rows"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(row["goal"], goal)
        self.assertEqual(row["next_milestone_percent"], 50)
        self.assertEqual(row["next_milestone_amount"], Decimal("250.00"))
        self.assertIsNotNone(row["pace"])
        self.assertContains(response, "Per week")
        self.assertContains(response, "Per month")
        self.assertContains(response, "Per year")
        self.assertContains(response, "Next milestone: 50%")

    def test_goals_without_deadlines_are_prompted_to_set_one(self):
        Goal.objects.create(
            user=self.user,
            name="Emergency fund",
            target_amount=Decimal("1000.00"),
        )

        response = self.client.get(reverse("savings:goals"))

        self.assertContains(response, "Set target date")
        self.assertContains(response, "Choose a target date")

    def test_overdue_goal_is_prompted_to_choose_a_new_target_date(self):
        Goal.objects.create(
            user=self.user,
            name="New laptop",
            target_amount=Decimal("1000.00"),
            target_date=timezone.localdate() - timedelta(days=1),
        )

        response = self.client.get(reverse("savings:goals"))
        row = response.context["goal_rows"][0]

        self.assertTrue(row["deadline_passed"])
        self.assertIsNone(row["pace"])
        self.assertContains(response, "Pick a new date")


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


class ContributionPaceTests(TestCase):
    def test_deadline_pace_returns_weekly_monthly_and_yearly_targets(self):
        pace = contribution_pace(
            Decimal("3650.00"), date(2027, 1, 1), today=date(2026, 1, 1)
        )

        self.assertEqual(pace["days_remaining"], 365)
        self.assertEqual(pace["yearly"], Decimal("3652.50"))
        self.assertEqual(pace["monthly"], Decimal("304.38"))
        self.assertEqual(pace["weekly"], Decimal("70.24"))

    def test_missing_or_elapsed_deadline_has_no_suggested_pace(self):
        self.assertIsNone(contribution_pace(Decimal("100.00"), None, today=date(2026, 1, 1)))
        self.assertIsNone(
            contribution_pace(Decimal("100.00"), date(2026, 1, 1), today=date(2026, 1, 1))
        )

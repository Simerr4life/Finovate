"""Regressions found in the codebase audit for goals, pools, and the plan."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from budgets.models import IncomeSource, RecurringExpense

from .models import Contribution, DebtObligation, Goal, SavingsPlan
from .plan_engine import ensure_default_pools, refresh_savings_plan
from .services import apply_contribution


class GoalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="saver", password="pw-12345-x")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        self.client.force_login(self.user)
        self.goal = Goal.objects.create(
            user=self.user, name="Trip", target_amount=Decimal("100"), current_amount=Decimal("40")
        )

    def test_default_pool_cannot_be_deleted(self):
        rainy = ensure_default_pools(self.user)[Goal.SystemKey.RAINY_DAY]
        Goal.objects.filter(pk=rainy.pk).update(current_amount=Decimal("300"))
        response = self.client.post(reverse("savings:goal_delete", args=[rainy.pk]), follow=True)
        self.assertContains(response, "can&#x27;t be deleted")
        rainy.refresh_from_db()
        self.assertEqual(rainy.current_amount, Decimal("300"))

    def test_custom_goal_can_still_be_deleted(self):
        response = self.client.post(reverse("savings:goal_delete", args=[self.goal.pk]))
        self.assertRedirects(response, reverse("savings:goals"))
        self.assertFalse(Goal.objects.filter(pk=self.goal.pk).exists())

    def test_withdrawing_more_than_the_balance_is_an_error(self):
        response = self.client.post(
            reverse("savings:goal_detail", args=[self.goal.pk]),
            {"kind": "withdrawal", "amount": "60", "note": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "withdraw at most $40.00")
        self.assertFalse(Contribution.objects.exists())

    def test_non_positive_contribution_is_an_error(self):
        response = self.client.post(
            reverse("savings:goal_detail", args=[self.goal.pk]),
            {"kind": "contribution", "amount": "-5", "note": ""},
        )
        self.assertContains(response, "greater than $0.00")
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_amount, Decimal("40"))

    def test_service_records_only_what_was_withdrawn(self):
        contribution, _ = apply_contribution(self.goal, "withdrawal", Decimal("75"))
        self.assertEqual(contribution.amount, Decimal("40.00"))
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_amount, Decimal("0.00"))

    def test_contribution_uses_the_latest_balance(self):
        stale = Goal.objects.get(pk=self.goal.pk)
        apply_contribution(self.goal, "contribution", Decimal("10"))
        apply_contribution(stale, "contribution", Decimal("10"))
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.current_amount, Decimal("60.00"))

    def test_editing_amounts_keeps_achieved_in_step(self):
        data = {"name": "Trip", "category": "travel", "color": "#123456", "target_amount": "100", "current_amount": "100"}
        self.client.post(reverse("savings:goal_edit", args=[self.goal.pk]), data)
        self.goal.refresh_from_db()
        self.assertIsNotNone(self.goal.achieved_at)
        data["target_amount"] = "500"
        self.client.post(reverse("savings:goal_edit", args=[self.goal.pk]), data)
        self.goal.refresh_from_db()
        self.assertIsNone(self.goal.achieved_at)

    def test_goal_target_must_be_positive(self):
        data = {"name": "Free", "category": "other", "color": "#123456", "target_amount": "0", "current_amount": "0"}
        response = self.client.post(reverse("savings:goal_add"), data)
        self.assertContains(response, "greater than $0.00")

    def test_saving_a_goal_returns_to_the_goals_page(self):
        data = {"name": "Car", "category": "vehicle", "color": "#123456", "target_amount": "900", "current_amount": "0"}
        response = self.client.post(reverse("savings:goal_add"), data)
        self.assertRedirects(response, reverse("savings:goals"))

    def test_assistant_goal_target_change_updates_achieved(self):
        from assistant.services import handle_incoming_message

        handle_incoming_message(self.user, "set my Trip goal to $30")
        handle_incoming_message(self.user, "yes")
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.target_amount, Decimal("30"))
        self.assertIsNotNone(self.goal.achieved_at)


class PlanStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="planner", password="pw-12345-x")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        self.client.force_login(self.user)
        IncomeSource.objects.create(user=self.user, name="Pay", amount=Decimal("4000"))
        RecurringExpense.objects.create(user=self.user, name="Housing (estimate)", amount=Decimal("1200"))
        self.plan = refresh_savings_plan(self.user, force=True)

    def test_disabled_plan_can_be_turned_back_on(self):
        self.client.post(reverse("savings:plan_status"), {"action": "disable"})
        response = self.client.get(reverse("savings:plan"))
        self.assertContains(response, "Turn recommendations back on")
        self.client.post(reverse("savings:plan_status"), {"action": "resume"})
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, SavingsPlan.Status.ACTIVE)

    def test_adding_a_debt_does_not_unpause_the_plan(self):
        self.client.post(reverse("savings:plan_status"), {"action": "pause"})
        self.client.post(
            reverse("savings:debt_add"),
            {"name": "Card", "balance": "900", "minimum_payment": "40", "interest_rate_apr": "24", "is_active": "on"},
        )
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, SavingsPlan.Status.PAUSED)
        self.assertTrue(DebtObligation.objects.filter(user=self.user).exists())

    def test_forced_recalculation_keeps_a_paused_plan_paused(self):
        self.client.post(reverse("savings:plan_status"), {"action": "pause"})
        self.client.post(reverse("savings:plan_refresh"))
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, SavingsPlan.Status.PAUSED)

    def test_small_change_refreshes_figures_without_a_revision(self):
        revisions = self.plan.revisions.count()
        IncomeSource.objects.filter(user=self.user).update(amount=Decimal("4010"))
        plan = refresh_savings_plan(self.user, reason="tiny")
        self.assertEqual(plan.monthly_income, Decimal("4010.00"))
        self.assertEqual(plan.revisions.count(), revisions)

    def test_material_change_records_a_revision(self):
        revisions = self.plan.revisions.count()
        IncomeSource.objects.filter(user=self.user).update(amount=Decimal("6000"))
        plan = refresh_savings_plan(self.user, reason="raise")
        self.assertEqual(plan.monthly_income, Decimal("6000.00"))
        self.assertEqual(plan.revisions.count(), revisions + 1)

    def test_debt_values_are_bounded(self):
        response = self.client.post(
            reverse("savings:debt_add"),
            {"name": "Bad", "balance": "-1", "minimum_payment": "0", "interest_rate_apr": "250"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DebtObligation.objects.filter(user=self.user).exists())

"""Regressions found in the codebase audit for simulated investing."""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from transactions.models import Transaction

from .models import PortfolioSnapshot, RoundUpLedgerEntry, RoundUpSettings, SimulatedOrder
from .services import approve_order, max_surplus_proposal, propose_surplus_investment


class RoundUpCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rounder", password="pw-12345-x")
        RoundUpSettings.objects.create(user=self.user, enabled=True, round_to=Decimal("1.00"))
        self.client.force_login(self.user)

    def test_manual_expense_creates_a_pending_roundup(self):
        self.client.post(
            reverse("budgets:transaction_add"),
            {"kind": "expense", "amount": "4.35", "description": "Coffee", "occurred_on": "2026-10-01"},
        )
        entry = RoundUpLedgerEntry.objects.get(user=self.user)
        self.assertEqual(entry.round_up_amount, Decimal("0.65"))
        self.assertEqual(entry.status, RoundUpLedgerEntry.Status.PENDING)

    def test_no_roundup_while_disabled_or_for_income(self):
        Transaction.objects.create(user=self.user, kind="income", amount=Decimal("10.50"), occurred_on=date(2026, 10, 1))
        RoundUpSettings.objects.filter(user=self.user).update(enabled=False)
        Transaction.objects.create(user=self.user, kind="expense", amount=Decimal("3.20"), occurred_on=date(2026, 10, 1))
        self.assertFalse(RoundUpLedgerEntry.objects.exists())

    def test_editing_the_amount_updates_a_pending_roundup(self):
        txn = Transaction.objects.create(user=self.user, kind="expense", amount=Decimal("4.35"), occurred_on=date(2026, 10, 1))
        txn.amount = Decimal("4.90")
        txn.save()
        entry = RoundUpLedgerEntry.objects.get(source_transaction=txn)
        self.assertEqual(entry.eligible_amount, Decimal("4.90"))
        self.assertEqual(entry.round_up_amount, Decimal("0.10"))

    def test_changing_to_income_reverses_the_pending_roundup(self):
        txn = Transaction.objects.create(user=self.user, kind="expense", amount=Decimal("4.35"), occurred_on=date(2026, 10, 1))
        txn.kind = Transaction.Kind.INCOME
        txn.save()
        entry = RoundUpLedgerEntry.objects.get(source_transaction=txn)
        self.assertEqual(entry.status, RoundUpLedgerEntry.Status.REVERSED)

    def test_swept_roundup_is_left_alone_on_edit(self):
        txn = Transaction.objects.create(user=self.user, kind="expense", amount=Decimal("4.35"), occurred_on=date(2026, 10, 1))
        RoundUpLedgerEntry.objects.filter(source_transaction=txn).update(status=RoundUpLedgerEntry.Status.SWEPT)
        txn.amount = Decimal("9.10")
        txn.save()
        entry = RoundUpLedgerEntry.objects.get(source_transaction=txn)
        self.assertEqual(entry.round_up_amount, Decimal("0.65"))


class OrderApprovalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="approver", password="pw-12345-x")
        self.client.force_login(self.user)

    def test_order_cannot_be_approved_twice(self):
        order = propose_surplus_investment(self.user, Decimal("50.00"))
        stale_copy = SimulatedOrder.objects.get(pk=order.pk)
        approve_order(order)
        with self.assertRaises(ValueError):
            approve_order(stale_copy)
        snapshot = PortfolioSnapshot.objects.get(user=self.user, pool=None)
        self.assertEqual(snapshot.net_contributions, Decimal("50.00"))


class SurplusProposalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="proposer", password="pw-12345-x")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        Transaction.objects.create(user=self.user, kind="income", amount=Decimal("500.00"), occurred_on=date(2026, 10, 1))
        self.client.force_login(self.user)

    def test_the_same_surplus_cannot_be_proposed_twice(self):
        self.assertEqual(max_surplus_proposal(self.user), Decimal("500.00"))
        self.client.post(reverse("investing:propose_surplus"), {"amount": "500.00"})
        self.client.post(reverse("investing:propose_surplus"), {"amount": "500.00"})
        orders = SimulatedOrder.objects.filter(user=self.user)
        self.assertEqual(orders.count(), 1)
        self.assertEqual(orders.get().amount, Decimal("500.00"))
        self.assertEqual(max_surplus_proposal(self.user), Decimal("0.00"))

    def test_unsafe_next_is_ignored(self):
        for target in ("/\\evil.example", "//evil.example", "https://evil.example"):
            response = self.client.post(reverse("investing:propose_surplus"), {"amount": "1", "next": target})
            self.assertRedirects(response, reverse("investing:index"), fetch_redirect_response=False)

    def test_safe_next_is_followed(self):
        response = self.client.post(reverse("investing:propose_surplus"), {"amount": "1", "next": "/savings/"})
        self.assertRedirects(response, "/savings/", fetch_redirect_response=False)

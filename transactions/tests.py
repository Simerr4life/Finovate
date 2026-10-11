from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Account, Transaction
from .services import compute_running_balances, reconcile_account, record_transaction


class IdempotentImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")

    def test_duplicate_external_id_does_not_double_count(self):
        txn1, created1 = record_transaction(
            self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("10.00"),
            occurred_on="2026-01-01", source="imported", external_id="bank-tx-1",
        )
        txn2, created2 = record_transaction(
            self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("10.00"),
            occurred_on="2026-01-01", source="imported", external_id="bank-tx-1",
        )
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(txn1.pk, txn2.pk)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_manual_entries_without_external_id_are_never_deduped(self):
        record_transaction(self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("5.00"), occurred_on="2026-01-01")
        record_transaction(self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("5.00"), occurred_on="2026-01-01")
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)

    def test_different_users_can_share_external_id(self):
        bob = User.objects.create_user(username="bob", password="x")
        record_transaction(self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("10.00"), occurred_on="2026-01-01", source="imported", external_id="shared-id")
        record_transaction(bob, kind=Transaction.Kind.EXPENSE, amount=Decimal("10.00"), occurred_on="2026-01-01", source="imported", external_id="shared-id")
        self.assertEqual(Transaction.objects.filter(external_id="shared-id").count(), 2)


class ReconciliationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.account = Account.objects.create(
            user=self.user, institution_name="Test Bank", account_holder_name="Alice",
            account_type="Checking", masked_number="••••0001",
            opening_balance=Decimal("100.00"),
        )

    def _txn(self, kind, amount, day):
        return Transaction.objects.create(
            user=self.user, account=self.account, kind=kind, amount=amount, occurred_on=f"2026-01-{day:02d}"
        )

    def test_running_balance_sequence_is_chronological(self):
        self._txn(Transaction.Kind.EXPENSE, Decimal("20.00"), 2)
        self._txn(Transaction.Kind.INCOME, Decimal("50.00"), 1)
        rows = compute_running_balances(self.account)
        # Jan 1 income first despite insertion order, then Jan 2 expense.
        self.assertEqual(rows[0].balance_after, Decimal("150.00"))
        self.assertEqual(rows[1].balance_after, Decimal("130.00"))

    def test_reconciliation_matches_when_stated_totals_are_correct(self):
        self._txn(Transaction.Kind.INCOME, Decimal("200.00"), 1)
        self._txn(Transaction.Kind.EXPENSE, Decimal("50.00"), 2)
        self.account.stated_total_deposits = Decimal("200.00")
        self.account.stated_total_withdrawals = Decimal("50.00")
        self.account.stated_ending_balance = Decimal("250.00")
        self.account.save()
        report = reconcile_account(self.account)
        self.assertTrue(report.fully_reconciled)
        self.assertEqual(report.computed_ending_balance, Decimal("250.00"))

    def test_reconciliation_flags_a_mismatch_rather_than_hiding_it(self):
        self._txn(Transaction.Kind.INCOME, Decimal("200.00"), 1)
        self.account.stated_ending_balance = Decimal("999.99")  # deliberately wrong
        self.account.save()
        report = reconcile_account(self.account)
        self.assertFalse(report.ending_balance_match)
        self.assertFalse(report.fully_reconciled)
        # The computed figure is still correct even though the stated one is wrong.
        self.assertEqual(report.computed_ending_balance, Decimal("300.00"))

    def test_peachtree_statement_reconciles_exactly(self):
        from django.core.management import call_command

        call_command("seed_peachtree_demo", password="test-only-pass-9876", username="recon-test")
        user = User.objects.get(username="recon-test")
        account = Account.objects.get(user=user)
        report = reconcile_account(account)
        self.assertEqual(report.computed_total_deposits, Decimal("3133.50"))
        self.assertEqual(report.computed_total_withdrawals, Decimal("1567.16"))
        self.assertEqual(report.computed_ending_balance, Decimal("2812.14"))
        self.assertTrue(report.fully_reconciled)


class PeachtreeSeedIdempotencyTests(TestCase):
    def test_running_twice_does_not_duplicate_transactions(self):
        from django.core.management import call_command

        call_command("seed_peachtree_demo", password="test-only-pass-9876", username="idempotent-test")
        first_count = Transaction.objects.filter(user__username="idempotent-test").count()
        call_command("seed_peachtree_demo", password="test-only-pass-9876", username="idempotent-test")
        second_count = Transaction.objects.filter(user__username="idempotent-test").count()
        self.assertEqual(first_count, 23)
        self.assertEqual(second_count, first_count)

    def test_reset_only_touches_this_demo_accounts_transactions(self):
        from django.core.management import call_command

        call_command("seed_peachtree_demo", password="test-only-pass-9876", username="reset-test")
        user = User.objects.get(username="reset-test")
        unrelated = Transaction.objects.create(
            user=user, kind=Transaction.Kind.EXPENSE, amount=Decimal("1.00"), occurred_on="2026-05-01"
        )
        call_command("seed_peachtree_demo", password="test-only-pass-9876", username="reset-test", reset=True)
        self.assertTrue(Transaction.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(Transaction.objects.filter(user=user, account__isnull=False).count(), 23)

    def test_does_not_touch_an_unrelated_users_data(self):
        from django.core.management import call_command

        other_user = User.objects.create_user(username="unrelated", password="x")
        Transaction.objects.create(
            user=other_user, kind=Transaction.Kind.EXPENSE, amount=Decimal("1.00"), occurred_on="2026-05-01"
        )
        call_command("seed_peachtree_demo", password="test-only-pass-9876", username="seed-target")
        self.assertEqual(Transaction.objects.filter(user=other_user).count(), 1)

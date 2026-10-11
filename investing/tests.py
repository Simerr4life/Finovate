from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from budgets.models import RecurringExpense
from savings.models import Goal
from transactions.models import Transaction

from .forms import VerifiedScenarioForm
from .models import (
    DemoInvestmentSuggestion,
    LiveMarketQuote,
    MarketPrice,
    PortfolioSnapshot,
    RoundUpLedgerEntry,
    RoundUpSettings,
    SimulatedOrder,
    TwelveDataUsageWindow,
)
from .services import (
    accept_demo_investment_suggestion,
    add_demo_investment_funds,
    approve_order,
    available_demo_investment_budget,
    compute_hypothetical_scenario,
    compute_investable_surplus,
    create_demo_market_order,
    create_roundup_for_transaction,
    decline_demo_investment_suggestion,
    generate_demo_investment_suggestions,
    investable_pools,
    pool_investment_summaries,
    propose_surplus_investment,
    reject_order,
    sweep_pending_roundups,
)
from .live_quotes import refresh_live_market_quotes


class RoundUpCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        RoundUpSettings.objects.create(user=self.user, enabled=True, round_to=Decimal("1.00"))

    def _expense(self, amount=Decimal("4.35")):
        return Transaction.objects.create(
            user=self.user, kind=Transaction.Kind.EXPENSE, amount=amount, occurred_on="2026-01-01"
        )

    def test_creates_pending_entry_for_eligible_expense(self):
        txn = self._expense()
        entry = create_roundup_for_transaction(txn)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.round_up_amount, Decimal("0.65"))
        self.assertEqual(entry.status, RoundUpLedgerEntry.Status.PENDING)

    def test_calling_twice_for_same_transaction_does_not_duplicate(self):
        txn = self._expense()
        first = create_roundup_for_transaction(txn)
        second = create_roundup_for_transaction(txn)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(RoundUpLedgerEntry.objects.filter(source_transaction=txn).count(), 1)

    def test_income_transactions_are_not_eligible(self):
        txn = Transaction.objects.create(
            user=self.user, kind=Transaction.Kind.INCOME, amount=Decimal("100.00"), occurred_on="2026-01-01"
        )
        self.assertIsNone(create_roundup_for_transaction(txn))

    def test_disabled_settings_skip_roundup(self):
        self.user.roundup_settings.enabled = False
        self.user.roundup_settings.save()
        txn = self._expense()
        self.assertIsNone(create_roundup_for_transaction(txn))

    def test_reversed_transaction_is_not_eligible(self):
        original = self._expense()
        refund = Transaction.objects.create(
            user=self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("4.35"),
            occurred_on="2026-01-02", reverses=original,
        )
        self.assertIsNone(create_roundup_for_transaction(refund))


class SweepTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        RoundUpSettings.objects.create(
            user=self.user, enabled=True, round_to=Decimal("1.00"),
            minimum_cash_reserve=Decimal("0.00"),
        )
        Transaction.objects.create(user=self.user, kind=Transaction.Kind.INCOME, amount=Decimal("1000.00"), occurred_on="2026-01-01")
        for amount in (Decimal("4.35"), Decimal("2.50")):
            txn = Transaction.objects.create(user=self.user, kind=Transaction.Kind.EXPENSE, amount=amount, occurred_on="2026-01-02")
            create_roundup_for_transaction(txn)

    def test_sweep_moves_pending_to_swept(self):
        result = sweep_pending_roundups(self.user)
        self.assertEqual(result["entries_swept"], 2)
        self.assertEqual(RoundUpLedgerEntry.objects.filter(status=RoundUpLedgerEntry.Status.PENDING).count(), 0)

    def test_sweep_respects_cash_reserve(self):
        rs = self.user.roundup_settings
        rs.minimum_cash_reserve = Decimal("100000.00")  # reserve far exceeds cash balance
        rs.save()
        result = sweep_pending_roundups(self.user)
        self.assertEqual(result["entries_swept"], 0)
        self.assertEqual(RoundUpLedgerEntry.objects.filter(status=RoundUpLedgerEntry.Status.PENDING).count(), 2)

    def test_sweep_respects_contribution_cap(self):
        rs = self.user.roundup_settings
        rs.contribution_cap_per_period = Decimal("0.40")
        rs.save()
        result = sweep_pending_roundups(self.user)
        # Pending entries are 0.65 and 0.50 — both exceed a 0.40 cap, so nothing fits.
        self.assertEqual(result["entries_swept"], 0)

    def test_sweep_when_paused_does_nothing(self):
        rs = self.user.roundup_settings
        rs.is_paused = True
        rs.save()
        result = sweep_pending_roundups(self.user)
        self.assertEqual(result["entries_swept"], 0)


class InvestableSurplusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        RoundUpSettings.objects.create(user=self.user, minimum_cash_reserve=Decimal("200.00"))
        Transaction.objects.create(user=self.user, kind=Transaction.Kind.INCOME, amount=Decimal("1000.00"), occurred_on="2026-01-01")

    def test_surplus_is_cash_minus_reserve_when_nothing_else_reserved(self):
        surplus = compute_investable_surplus(self.user)
        self.assertEqual(surplus.cash_balance, Decimal("1000.00"))
        self.assertEqual(surplus.investable_surplus, Decimal("800.00"))

    def test_goal_allocations_reduce_surplus(self):
        Goal.objects.create(user=self.user, name="Trip", target_amount=Decimal("500"), current_amount=Decimal("300.00"))
        surplus = compute_investable_surplus(self.user)
        self.assertEqual(surplus.goal_allocations, Decimal("300.00"))
        self.assertEqual(surplus.investable_surplus, Decimal("500.00"))  # 1000 - 200 reserve - 300 goal

    def test_recurring_bills_buffer_reduces_surplus(self):
        RecurringExpense.objects.create(user=self.user, name="Rent", amount=Decimal("400.00"), cadence="monthly")
        surplus = compute_investable_surplus(self.user)
        self.assertEqual(surplus.upcoming_bills_buffer, Decimal("400.00"))
        self.assertEqual(surplus.investable_surplus, Decimal("400.00"))  # 1000 - 200 - 400

    def test_surplus_never_goes_negative(self):
        RoundUpSettings.objects.filter(user=self.user).update(minimum_cash_reserve=Decimal("5000.00"))
        surplus = compute_investable_surplus(self.user)
        self.assertEqual(surplus.investable_surplus, Decimal("0.00"))

    def test_achieved_goals_do_not_reserve_funds(self):
        from django.utils import timezone

        Goal.objects.create(
            user=self.user, name="Done", target_amount=Decimal("100"), current_amount=Decimal("100"),
            achieved_at=timezone.now(),
        )
        surplus = compute_investable_surplus(self.user)
        self.assertEqual(surplus.goal_allocations, Decimal("0.00"))


class ProposeApproveRejectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")

    def test_proposed_order_starts_pending_and_does_not_touch_snapshot(self):
        order = propose_surplus_investment(self.user, Decimal("50.00"))
        self.assertEqual(order.status, SimulatedOrder.Status.PENDING)
        self.assertFalse(PortfolioSnapshot.objects.filter(user=self.user).exists())

    def test_approving_fills_order_and_updates_snapshot(self):
        order = propose_surplus_investment(self.user, Decimal("50.00"))
        approve_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, SimulatedOrder.Status.FILLED)
        snapshot = PortfolioSnapshot.objects.get(user=self.user)
        self.assertEqual(snapshot.net_contributions, Decimal("50.00"))
        self.assertEqual(snapshot.market_value, Decimal("50.00"))

    def test_rejecting_leaves_snapshot_untouched(self):
        order = propose_surplus_investment(self.user, Decimal("50.00"))
        reject_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, SimulatedOrder.Status.REJECTED)
        self.assertFalse(PortfolioSnapshot.objects.filter(user=self.user).exists())


class HypotheticalScenarioTests(TestCase):
    def test_basic_gain_calculation(self):
        scenario = compute_hypothetical_scenario(
            symbol="VTI", invest_date="2026-09-30", invest_price=Decimal("250.00"),
            valuation_date="2026-10-06", valuation_price=Decimal("260.00"),
            amount_invested=Decimal("100.00"),
        )
        self.assertEqual(scenario.shares, Decimal("0.400000"))
        self.assertEqual(scenario.value_at_valuation_date, Decimal("104.00"))
        self.assertEqual(scenario.gain_loss, Decimal("4.00"))

    def test_loss_scenario(self):
        scenario = compute_hypothetical_scenario(
            symbol="VTI", invest_date="2026-09-30", invest_price=Decimal("100.00"),
            valuation_date="2026-10-06", valuation_price=Decimal("90.00"),
            amount_invested=Decimal("100.00"),
        )
        self.assertEqual(scenario.gain_loss, Decimal("-10.00"))
        self.assertEqual(scenario.gain_loss_percent, Decimal("-10.00"))

    def test_zero_or_negative_price_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_hypothetical_scenario(
                symbol="VTI", invest_date="2026-09-30", invest_price=Decimal("0"),
                valuation_date="2026-10-06", valuation_price=Decimal("90.00"),
                amount_invested=Decimal("100.00"),
            )


class SavingsPoolTargetingTests(TestCase):
    """'Invest round-ups and surplus into a named Savings Pool'."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.pool = Goal.objects.create(
            user=self.user, name="Retirement nest egg", target_amount=Decimal("5000"), is_investable=True
        )
        RoundUpSettings.objects.create(user=self.user, enabled=True, round_to=Decimal("1.00"), target_pool=self.pool)
        Transaction.objects.create(user=self.user, kind=Transaction.Kind.INCOME, amount=Decimal("1000.00"), occurred_on="2026-01-01")
        txn = Transaction.objects.create(user=self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("4.35"), occurred_on="2026-01-02")
        create_roundup_for_transaction(txn)

    def test_sweep_attributes_order_and_snapshot_to_the_target_pool(self):
        result = sweep_pending_roundups(self.user)
        self.assertEqual(result["pool"], self.pool)
        order = result["order"]
        self.assertEqual(order.pool, self.pool)
        snapshot = PortfolioSnapshot.objects.get(user=self.user, pool=self.pool)
        self.assertEqual(snapshot.net_contributions, Decimal("0.65"))

    def test_sweep_ignores_a_pool_that_is_not_investable(self):
        self.pool.is_investable = False
        self.pool.save()
        result = sweep_pending_roundups(self.user)
        self.assertIsNone(result["pool"])
        self.assertTrue(PortfolioSnapshot.objects.filter(user=self.user, pool__isnull=True).exists())

    def test_general_bucket_snapshot_stays_separate_from_pool_snapshot(self):
        sweep_pending_roundups(self.user)  # goes to self.pool
        propose_surplus_investment(self.user, Decimal("10.00"), pool=None)
        general_order = SimulatedOrder.objects.get(pool__isnull=True)
        approve_order(general_order)
        general_snapshot = PortfolioSnapshot.objects.get(user=self.user, pool__isnull=True)
        pool_snapshot = PortfolioSnapshot.objects.get(user=self.user, pool=self.pool)
        self.assertEqual(general_snapshot.net_contributions, Decimal("10.00"))
        self.assertEqual(pool_snapshot.net_contributions, Decimal("0.65"))

    def test_propose_into_non_investable_pool_raises(self):
        other = Goal.objects.create(user=self.user, name="Not investable", target_amount=Decimal("100"))
        with self.assertRaises(ValueError):
            propose_surplus_investment(self.user, Decimal("10.00"), pool=other)

    def test_investable_pools_excludes_non_investable_goals(self):
        Goal.objects.create(user=self.user, name="Just a goal", target_amount=Decimal("100"))
        pools = list(investable_pools(self.user))
        self.assertEqual(pools, [self.pool])

    def test_pool_investment_summaries_reflects_invested_amount(self):
        sweep_pending_roundups(self.user)
        summaries = pool_investment_summaries(self.user)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["snapshot"].net_contributions, Decimal("0.65"))

    def test_pool_cash_balance_is_never_mixed_with_invested_amount(self):
        from savings.services import apply_contribution

        apply_contribution(self.pool, kind="contribution", amount=Decimal("200.00"))
        sweep_pending_roundups(self.user)
        self.pool.refresh_from_db()
        snapshot = PortfolioSnapshot.objects.get(user=self.user, pool=self.pool)
        self.assertEqual(self.pool.current_amount, Decimal("200.00"))
        self.assertEqual(snapshot.net_contributions, Decimal("0.65"))


class MarketDataSeedTests(TestCase):
    def test_seed_command_is_idempotent(self):
        from django.core.management import call_command

        self.assertEqual(MarketPrice.objects.filter(is_demo_sample=True).count(), 109)
        call_command("seed_market_data")
        first_count = MarketPrice.objects.count()
        call_command("seed_market_data")
        self.assertEqual(MarketPrice.objects.count(), first_count)
        self.assertEqual(MarketPrice.objects.filter(is_demo_sample=True).count(), 109)

    def test_verified_rows_are_never_fabricated_outside_the_given_set(self):
        from django.core.management import call_command

        call_command("seed_market_data")
        self.assertTrue(MarketPrice.objects.filter(symbol="AAPL", date="2026-09-16", close=Decimal("332.41")).exists())
        self.assertFalse(
            MarketPrice.objects.filter(
                symbol="AAPL", date="2026-09-17", is_demo_sample=False
            ).exists()
        )

    def test_reset_clears_rows_before_reseeding(self):
        from django.core.management import call_command

        call_command("seed_market_data")
        call_command("seed_market_data", reset=True)
        self.assertEqual(MarketPrice.objects.count(), 18)

    def test_excel_demo_seed_loads_109_rows_and_is_idempotent(self):
        from django.core.management import call_command

        call_command("seed_excel_demo_market")
        self.assertEqual(MarketPrice.objects.count(), 109)
        call_command("seed_excel_demo_market")
        self.assertEqual(MarketPrice.objects.count(), 109)
        self.assertTrue(
            MarketPrice.objects.filter(
                symbol="GOOGL",
                date="2026-09-30",
                close=Decimal("344.08"),
                is_demo_sample=True,
            ).exists()
        )


class DemoAISuggestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="demo-ai-user", password="test-password")
        self.other_user = User.objects.create_user(username="other-demo-ai", password="test-password")
        Transaction.objects.create(
            user=self.user,
            kind=Transaction.Kind.INCOME,
            amount=Decimal("100.00"),
            occurred_on="2026-09-01",
        )
        for symbol, closes, changes in (
            ("AAA", ("100.00", "110.00", "121.00"), ("10.00", "10.00", "10.00")),
            ("BBB", ("100.00", "105.00", "110.00"), ("5.00", "4.76", "4.76")),
            ("CCC", ("100.00", "95.00", "90.00"), ("-5.00", "-5.26", "-5.26")),
            ("^INDEX", ("100.00", "120.00", "130.00"), (None, None, None)),
        ):
            for day, close, change in zip(
                ("2026-09-01", "2026-09-02", "2026-09-03"), closes, changes
            ):
                MarketPrice.objects.create(
                    symbol=symbol,
                    asset_type=(
                        MarketPrice.AssetType.INDEX
                        if symbol.startswith("^")
                        else MarketPrice.AssetType.STOCK
                    ),
                    date=day,
                    close=Decimal(close),
                    daily_change_percent=Decimal(change) if change is not None else None,
                    source_note="Demo test sample",
                    is_verified=True,
                    is_demo_sample=True,
                )

    def test_recommendations_rank_sample_stocks_and_observe_surplus_cap(self):
        suggestions = generate_demo_investment_suggestions(self.user)

        self.assertEqual(len(suggestions), 3)
        self.assertEqual(suggestions[0].symbol, "AAA")
        self.assertEqual(sum((item.amount for item in suggestions), Decimal("0")), Decimal("75.00"))
        self.assertNotIn("^INDEX", [item.symbol for item in suggestions])
        self.assertIn("does not predict future results", suggestions[0].explanation)

    def test_non_demo_market_rows_do_not_influence_excel_recommendations(self):
        MarketPrice.objects.create(
            symbol="REAL-ROW",
            asset_type=MarketPrice.AssetType.STOCK,
            date="2026-09-30",
            close=Decimal("1000.00"),
            daily_change_percent=Decimal("50.00"),
            source_note="Other market dataset",
            is_verified=True,
            is_demo_sample=False,
        )
        MarketPrice.objects.create(
            symbol="REAL-ROW",
            asset_type=MarketPrice.AssetType.STOCK,
            date="2026-09-29",
            close=Decimal("500.00"),
            daily_change_percent=Decimal("50.00"),
            source_note="Other market dataset",
            is_verified=True,
            is_demo_sample=False,
        )

        suggestions = generate_demo_investment_suggestions(self.user)

        self.assertNotIn("REAL-ROW", [item.symbol for item in suggestions])

    def test_recommendations_are_idempotent_for_the_same_data_snapshot(self):
        first = generate_demo_investment_suggestions(self.user)
        second = generate_demo_investment_suggestions(self.user)

        self.assertEqual([item.pk for item in first], [item.pk for item in second])
        self.assertEqual(DemoInvestmentSuggestion.objects.filter(user=self.user).count(), 3)

    def test_accept_creates_a_pending_simulated_order_with_excel_price_metadata(self):
        suggestion = generate_demo_investment_suggestions(self.user)[0]

        order = accept_demo_investment_suggestion(self.user, suggestion)

        self.assertEqual(order.status, SimulatedOrder.Status.PENDING)
        self.assertEqual(order.symbol, suggestion.symbol)
        self.assertEqual(order.demo_execution_price, suggestion.demo_execution_price)
        self.assertEqual(order.demo_data_date, suggestion.data_date)
        self.assertGreater(order.demo_shares, Decimal("0"))
        self.assertFalse(PortfolioSnapshot.objects.filter(user=self.user).exists())
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, DemoInvestmentSuggestion.Status.ACCEPTED)
        self.assertEqual(suggestion.simulated_order, order)

    def test_decline_creates_no_order(self):
        suggestion = generate_demo_investment_suggestions(self.user)[0]

        decline_demo_investment_suggestion(self.user, suggestion)

        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, DemoInvestmentSuggestion.Status.DECLINED)
        self.assertFalse(SimulatedOrder.objects.filter(user=self.user).exists())

    def test_accept_rejects_if_available_surplus_dropped(self):
        suggestion = generate_demo_investment_suggestions(self.user)[0]
        Transaction.objects.filter(user=self.user, kind=Transaction.Kind.INCOME).update(
            amount=Decimal("10.00")
        )

        with self.assertRaisesMessage(ValueError, "current demo investing budget"):
            accept_demo_investment_suggestion(self.user, suggestion)

        self.assertFalse(SimulatedOrder.objects.filter(user=self.user).exists())

    def test_recommendations_never_exceed_small_surplus(self):
        Transaction.objects.filter(user=self.user, kind=Transaction.Kind.INCOME).update(
            amount=Decimal("0.02")
        )

        suggestions = generate_demo_investment_suggestions(self.user)

        self.assertEqual(len(suggestions), 2)
        self.assertEqual(sum((item.amount for item in suggestions), Decimal("0")), Decimal("0.02"))

    def test_suggestion_is_user_scoped(self):
        suggestion = generate_demo_investment_suggestions(self.user)[0]

        with self.assertRaises(DemoInvestmentSuggestion.DoesNotExist):
            accept_demo_investment_suggestion(self.other_user, suggestion)

    def test_pending_and_filled_simulated_orders_reduce_recommendation_budget(self):
        pending = propose_surplus_investment(self.user, Decimal("20.00"))
        self.assertEqual(available_demo_investment_budget(self.user), Decimal("80.00"))
        approve_order(pending)
        self.assertEqual(available_demo_investment_budget(self.user), Decimal("80.00"))
        pending.status = SimulatedOrder.Status.REJECTED
        pending.save()
        self.assertEqual(available_demo_investment_budget(self.user), Decimal("100.00"))

    def test_virtual_funds_add_to_demo_budget_and_enable_recommendations(self):
        Transaction.objects.filter(user=self.user).delete()

        add_demo_investment_funds(self.user, Decimal("60.00"))
        suggestions = generate_demo_investment_suggestions(self.user)

        self.assertEqual(available_demo_investment_budget(self.user), Decimal("60.00"))
        self.assertEqual(sum((item.amount for item in suggestions), Decimal("0")), Decimal("60.00"))
        self.assertEqual(
            Transaction.objects.filter(user=self.user).count(),
            0,
        )

    def test_investable_pool_cash_funds_demo_recommendations_and_orders(self):
        Transaction.objects.filter(user=self.user).delete()
        pool = Goal.objects.create(
            user=self.user,
            name="Investing pool",
            target_amount=Decimal("2000.00"),
            current_amount=Decimal("1000.00"),
            is_investable=True,
        )

        suggestions = generate_demo_investment_suggestions(self.user)
        order = create_demo_market_order(self.user, "AAA", Decimal("250.00"), pool)

        self.assertEqual(available_demo_investment_budget(self.user), Decimal("750.00"))
        self.assertGreater(len(suggestions), 0)
        self.assertEqual(order.pool, pool)
        self.assertEqual(order.amount, Decimal("250.00"))

    def test_virtual_funding_rejects_invalid_precision_and_amounts(self):
        for amount in (
            Decimal("0"),
            Decimal("-1.00"),
            Decimal("1.001"),
            Decimal("NaN"),
            Decimal("10000000000.00"),
        ):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    add_demo_investment_funds(self.user, amount)


class DemoAISuggestionViewTests(TestCase):
    def setUp(self):
        MarketPrice.objects.filter(is_demo_sample=True).delete()
        self.user = User.objects.create_user(username="demo-ai-view", password="test-password")
        self.client.force_login(self.user)
        Transaction.objects.create(
            user=self.user,
            kind=Transaction.Kind.INCOME,
            amount=Decimal("100.00"),
            occurred_on="2026-09-01",
        )
        for symbol, close in (("AAA", "100.00"), ("BBB", "200.00")):
            for day, price in (("2026-09-01", close), ("2026-09-02", str(Decimal(close) + 1))):
                MarketPrice.objects.create(
                    symbol=symbol,
                    asset_type=MarketPrice.AssetType.STOCK,
                    date=day,
                    close=Decimal(price),
                    daily_change_percent=Decimal("1.00"),
                    source_note="Demo test sample",
                    is_verified=True,
                    is_demo_sample=True,
                )

    def test_index_prominently_discloses_demo_ai(self):
        response = self.client.get("/investing/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FINOVATE DEMO AI")
        self.assertContains(response, "no brokerage")

    def test_generate_accept_and_decline_are_explicit_post_actions(self):
        response = self.client.post("/investing/demo-ai/generate/")
        self.assertRedirects(response, "/investing/")
        suggestions = list(DemoInvestmentSuggestion.objects.filter(user=self.user))
        self.assertEqual(len(suggestions), 2)

        response = self.client.post(
            f"/investing/demo-ai/{suggestions[0].pk}/accept/",
            {"pool": ""},
        )
        self.assertRedirects(response, "/investing/")
        suggestions[0].refresh_from_db()
        self.assertEqual(suggestions[0].status, DemoInvestmentSuggestion.Status.ACCEPTED)
        self.assertEqual(SimulatedOrder.objects.filter(user=self.user).count(), 1)

        response = self.client.post(
            f"/investing/demo-ai/{suggestions[1].pk}/decline/"
        )
        self.assertRedirects(response, "/investing/")
        suggestions[1].refresh_from_db()
        self.assertEqual(suggestions[1].status, DemoInvestmentSuggestion.Status.DECLINED)
        self.assertEqual(SimulatedOrder.objects.filter(user=self.user).count(), 1)


class DemoMarketExplorerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="market-explorer-user", password="test-password"
        )
        self.client.force_login(self.user)
        RoundUpSettings.objects.update_or_create(
            user=self.user,
            defaults={"minimum_cash_reserve": Decimal("0.00")},
        )
        Transaction.objects.create(
            user=self.user,
            kind=Transaction.Kind.INCOME,
            amount=Decimal("100.00"),
            occurred_on="2026-09-01",
        )

    def test_migration_loaded_sample_data_is_visible_in_a_friendly_explorer(self):
        response = self.client.get("/investing/market-data/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MarketPrice.objects.filter(is_demo_sample=True).count(), 109)
        self.assertContains(response, "Explore sample market data")
        self.assertContains(response, "Apple")
        self.assertContains(response, "S&amp;P 500")
        self.assertContains(response, "View all 18 sample price days")
        self.assertContains(response, "Available demo budget")
        self.assertContains(response, "Create demo order")
        self.assertContains(response, "data-market-view=\"chart\"")
        self.assertContains(response, "data-market-view=\"table\"")
        self.assertContains(response, "data-chart-slider")
        self.assertContains(response, "Up from prior sample date")
        self.assertContains(response, "Down from prior sample date")
        self.assertContains(response, "market-charts.js")

    def test_explore_tab_shows_full_width_charts_by_default(self):
        response = self.client.get("/investing/?tab=explore")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explore price movement")
        self.assertContains(response, "market-asset-card-wide")
        self.assertContains(response, 'data-default-view="chart"')
        self.assertContains(response, "Move through sample dates")
        self.assertEqual(len(response.context["market_assets"]), 8)
        self.assertEqual(response.context["demo_budget"], Decimal("100.00"))

    def test_user_can_add_virtual_funds_then_generate_ideas_and_create_orders(self):
        Transaction.objects.filter(user=self.user).delete()

        response = self.client.post(
            "/investing/demo-budget/add/",
            {"amount": "60.00"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Added $60.00 in virtual demo funds")
        self.assertContains(response, "Demo investing budget")
        self.assertEqual(available_demo_investment_budget(self.user), Decimal("60.00"))
        self.assertFalse(Transaction.objects.filter(user=self.user).exists())

        response = self.client.post("/investing/demo-ai/generate/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            DemoInvestmentSuggestion.objects.filter(
                user=self.user,
                status=DemoInvestmentSuggestion.Status.PENDING,
            ).count(),
            3,
        )

        response = self.client.post(
            "/investing/market-data/invest/",
            {"symbol": "AAPL", "amount": "20.00"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(available_demo_investment_budget(self.user), Decimal("40.00"))

    def test_add_virtual_funds_rejects_invalid_amount(self):
        response = self.client.post(
            "/investing/demo-budget/add/",
            {"amount": "1.001"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no more than two decimal places")
        self.assertEqual(available_demo_investment_budget(self.user), Decimal("100.00"))

    def test_my_investments_shows_approved_holdings_but_not_pending_orders(self):
        approved_order = create_demo_market_order(self.user, "AAPL", Decimal("35.00"))
        approve_order(approved_order)
        create_demo_market_order(self.user, "MSFT", Decimal("20.00"))
        latest_price = MarketPrice.objects.filter(
            symbol="AAPL", is_demo_sample=True
        ).latest("date")

        response = self.client.get("/investing/?tab=holdings")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My investments")
        self.assertContains(response, "AAPL")
        self.assertContains(response, "MSFT")
        self.assertContains(response, "These are not part of your holdings yet.")
        self.assertContains(response, "live-holdings.js")
        self.assertContains(response, "data-live-quotes-status")
        self.assertEqual(len(response.context["holdings"]), 1)
        self.assertEqual(response.context["holdings"][0]["symbol"], "AAPL")
        self.assertEqual(
            response.context["holdings_market_value"],
            approved_order.demo_shares * latest_price.close,
        )
        self.assertGreater(len(response.context["portfolio_series"]), 1)

    def test_user_can_create_pending_order_from_a_selected_sample_asset(self):
        pool = Goal.objects.create(
            user=self.user,
            name="Travel pool",
            target_amount=Decimal("500.00"),
            is_investable=True,
        )
        latest_price = MarketPrice.objects.filter(
            symbol="AAPL", is_demo_sample=True
        ).latest("date")

        response = self.client.post(
            "/investing/market-data/invest/",
            {"symbol": "AAPL", "amount": "35.00", "pool": str(pool.pk)},
        )

        self.assertEqual(response.status_code, 302)
        order = SimulatedOrder.objects.get(user=self.user)
        self.assertEqual(order.symbol, "AAPL")
        self.assertEqual(order.amount, Decimal("35.00"))
        self.assertEqual(order.pool, pool)
        self.assertEqual(order.status, SimulatedOrder.Status.PENDING)
        self.assertEqual(order.demo_execution_price, latest_price.close)
        self.assertEqual(order.demo_data_date, latest_price.date)
        self.assertGreater(order.demo_shares, Decimal("0"))
        self.assertFalse(PortfolioSnapshot.objects.filter(user=self.user).exists())

    def test_order_cannot_exceed_available_demo_budget(self):
        response = self.client.post(
            "/investing/market-data/invest/",
            {"symbol": "AAPL", "amount": "101.00"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(SimulatedOrder.objects.filter(user=self.user).exists())
        self.assertContains(
            self.client.get("/investing/market-data/"),
            "above your available demo investing budget",
            status_code=200,
        )

    def test_order_cannot_use_a_non_sample_market_row(self):
        MarketPrice.objects.create(
            symbol="OTHER",
            asset_type=MarketPrice.AssetType.STOCK,
            date="2026-09-30",
            close=Decimal("25.00"),
            source_note="Other source",
            is_verified=True,
            is_demo_sample=False,
        )

        response = self.client.post(
            "/investing/market-data/invest/",
            {"symbol": "OTHER", "amount": "10.00"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(SimulatedOrder.objects.filter(user=self.user).exists())


class LiveMarketQuoteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="live-quote-user")
        self.client.force_login(self.user)
        RoundUpSettings.objects.update_or_create(
            user=self.user,
            defaults={"minimum_cash_reserve": Decimal("0.00")},
        )
        Transaction.objects.create(
            user=self.user,
            kind=Transaction.Kind.INCOME,
            amount=Decimal("100.00"),
            occurred_on="2026-09-01",
        )

    @override_settings(TWELVE_DATA_API_KEY="test-api-key")
    @patch("investing.live_quotes._fetch_twelve_data_price")
    def test_quotes_are_shared_and_cached_for_five_minutes(self, fetch_price):
        fetch_price.return_value = Decimal("250.1234")

        quotes, errors = refresh_live_market_quotes(["AAPL"])
        cached_quotes, cached_errors = refresh_live_market_quotes(["AAPL"])

        self.assertEqual(errors, {})
        self.assertEqual(cached_errors, {})
        self.assertEqual(quotes["AAPL"].price, Decimal("250.1234"))
        self.assertEqual(cached_quotes["AAPL"].price, Decimal("250.1234"))
        fetch_price.assert_called_once_with("AAPL")
        self.assertEqual(
            TwelveDataUsageWindow.objects.get(provider="twelve-data").daily_credits,
            1,
        )

    @override_settings(TWELVE_DATA_API_KEY="test-api-key")
    @patch("investing.live_quotes._fetch_twelve_data_price")
    def test_shared_free_tier_minute_quota_is_enforced(self, fetch_price):
        now = timezone.now()
        TwelveDataUsageWindow.objects.create(
            provider="twelve-data",
            minute_bucket=now.replace(second=0, microsecond=0),
            minute_credits=8,
            usage_date=now.date(),
            daily_credits=8,
        )

        quotes, errors = refresh_live_market_quotes(["AAPL"])

        self.assertEqual(quotes, {})
        self.assertEqual(errors, {"AAPL": "minute-limit"})
        fetch_price.assert_not_called()

    @override_settings(TWELVE_DATA_API_KEY="test-api-key")
    @patch("investing.views._is_us_regular_session", return_value=True)
    @patch("investing.live_quotes._fetch_twelve_data_price")
    def test_live_quotes_update_only_the_signed_in_users_filled_holdings(
        self, fetch_price, _market_open
    ):
        fetch_price.return_value = Decimal("250.00")
        order = create_demo_market_order(self.user, "AAPL", Decimal("20.00"))
        approve_order(order)

        response = self.client.get("/investing/live-quotes/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        quote = payload["quotes"]["AAPL"]
        self.assertEqual(
            Decimal(payload["portfolio_value"]),
            order.demo_shares * Decimal("250.00"),
        )
        self.assertEqual(Decimal(quote["price"]), Decimal("250.00"))
        self.assertEqual(payload["errors"], {})
        fetch_price.assert_called_once_with("AAPL")

    def test_live_quotes_require_server_side_api_key(self):
        order = create_demo_market_order(self.user, "AAPL", Decimal("20.00"))
        approve_order(order)

        with override_settings(TWELVE_DATA_API_KEY=""):
            response = self.client.get("/investing/live-quotes/")

        self.assertEqual(response.status_code, 503)
        self.assertIn("TWELVE_DATA_API_KEY", response.json()["error"])

    def test_holdings_without_filled_orders_do_not_start_quote_polling(self):
        response = self.client.get("/investing/?tab=holdings")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-live-quotes-status")
        self.assertNotContains(response, "live-holdings.js")

    @override_settings(TWELVE_DATA_API_KEY="test-api-key")
    @patch("investing.views._is_us_regular_session", return_value=False)
    @patch("investing.live_quotes._fetch_twelve_data_price")
    def test_market_closed_uses_cache_without_spending_provider_credits(
        self, fetch_price, _market_open
    ):
        order = create_demo_market_order(self.user, "AAPL", Decimal("20.00"))
        approve_order(order)
        LiveMarketQuote.objects.create(
            symbol="AAPL",
            price=Decimal("200.00"),
            fetched_at=timezone.now() - timedelta(hours=1),
        )

        response = self.client.get("/investing/live-quotes/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["market_open"])
        self.assertEqual(response.json()["quotes"]["AAPL"]["price"], "200.0000")
        fetch_price.assert_not_called()
        self.assertEqual(TwelveDataUsageWindow.objects.count(), 0)
        self.assertIn("no-store", response["Cache-Control"])


class VerifiedScenarioFormTests(TestCase):
    def setUp(self):
        from django.core.management import call_command

        call_command("seed_market_data")
        self.sep15 = MarketPrice.objects.get(symbol="AAPL", date="2026-09-15")
        self.sep16 = MarketPrice.objects.get(symbol="AAPL", date="2026-09-16")
        self.nvda = MarketPrice.objects.get(symbol="NVDA", date="2026-09-25")

    def test_same_symbol_before_after_is_valid(self):
        form = VerifiedScenarioForm(data={
            "invest_row": self.sep15.pk, "valuation_row": self.sep16.pk, "amount_invested": "100",
        })
        self.assertTrue(form.is_valid())

    def test_mismatched_symbols_is_invalid(self):
        form = VerifiedScenarioForm(data={
            "invest_row": self.sep15.pk, "valuation_row": self.nvda.pk, "amount_invested": "100",
        })
        self.assertFalse(form.is_valid())

    def test_valuation_before_investment_is_invalid(self):
        form = VerifiedScenarioForm(data={
            "invest_row": self.sep16.pk, "valuation_row": self.sep15.pk, "amount_invested": "100",
        })
        self.assertFalse(form.is_valid())

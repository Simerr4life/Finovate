import hashlib
import hmac
import json
import time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from budgets.models import Budget, BudgetPeriod
from investing.services import get_or_create_settings
from savings.models import Goal
from transactions.models import Category, Transaction

from .models import ConversationMessage, PendingConfirmation
from .services import handle_incoming_message


class ImmediateIntentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")

    def test_unrecognized_text_gives_fallback(self):
        reply = handle_incoming_message(self.user, "asdkfjasldkfj")
        self.assertIn("didn't understand", reply)

    def test_help_lists_commands(self):
        reply = handle_incoming_message(self.user, "help")
        self.assertIn("budget", reply.lower())

    def test_market_status_is_honest_about_no_live_feed(self):
        reply = handle_incoming_message(self.user, "how is the market today")
        self.assertIn("don't have a live market data connection", reply)

    def test_budget_status_with_no_active_period(self):
        reply = handle_incoming_message(self.user, "how's my budget")
        self.assertIn("don't have an active budget period", reply)

    def test_budget_status_reports_each_category(self):
        period = BudgetPeriod.objects.create(
            user=self.user, name="Oct", start_date="2026-10-01", end_date="2026-10-31", is_active=True
        )
        cat = Category.objects.create(user=self.user, name="Groceries", kind="expense")
        Budget.objects.create(user=self.user, period=period, category=cat, limit_amount=Decimal("100"))
        Transaction.objects.create(user=self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("30"), category=cat, occurred_on="2026-10-05")
        reply = handle_incoming_message(self.user, "budget status please")
        self.assertIn("Groceries: $30.00/$100.00", reply)

    def test_pause_roundups_is_immediate_no_confirmation(self):
        reply = handle_incoming_message(self.user, "pause round-ups")
        self.assertIn("paused", reply)
        self.assertTrue(get_or_create_settings(self.user).is_paused)
        self.assertFalse(PendingConfirmation.objects.filter(user=self.user).exists())

    def test_portfolio_performance_with_no_activity(self):
        reply = handle_incoming_message(self.user, "how's my portfolio doing")
        self.assertIn("No simulated investment activity yet", reply)


class ConfirmationFlowTests(TestCase):
    """Any state-changing intent must require an explicit confirm."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")

    def test_report_income_requires_confirmation_before_creating_a_transaction(self):
        reply = handle_incoming_message(self.user, "I got paid $500")
        self.assertIn("Record $500", reply)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

        reply2 = handle_incoming_message(self.user, "yes")
        self.assertIn("Recorded $500", reply2)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_cancelling_a_confirmation_does_nothing(self):
        handle_incoming_message(self.user, "I got paid $500")
        reply = handle_incoming_message(self.user, "no")
        self.assertIn("cancelled", reply)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

    def test_unrelated_reply_while_pending_reminds_instead_of_acting(self):
        handle_incoming_message(self.user, "I got paid $500")
        reply = handle_incoming_message(self.user, "what's the weather")
        self.assertIn("Record $500", reply)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)

    def test_confirming_with_nothing_pending_says_so(self):
        reply = handle_incoming_message(self.user, "yes")
        self.assertIn("nothing pending", reply)

    def test_set_risk_comfort_requires_confirmation(self):
        handle_incoming_message(self.user, "set my risk to high")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.risk_comfort, "unspecified")
        handle_incoming_message(self.user, "yes")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.risk_comfort, "high")

    def test_resume_roundups_requires_confirmation(self):
        rs = get_or_create_settings(self.user)
        rs.is_paused = True
        rs.save()
        handle_incoming_message(self.user, "resume round-ups")
        rs.refresh_from_db()
        self.assertTrue(rs.is_paused)
        handle_incoming_message(self.user, "yes")
        rs.refresh_from_db()
        self.assertFalse(rs.is_paused)

    def test_pending_confirmation_is_fresh_not_stale_cached_relation(self):
        """Regression test: a OneToOne reverse accessor caches on the
        instance. handle_incoming_message must re-query rather than reuse
        a stale cached object across calls with the same user instance."""
        handle_incoming_message(self.user, "I got paid $500")
        handle_incoming_message(self.user, "yes")  # resolves and deletes the pending row
        reply = handle_incoming_message(self.user, "how is the market today")
        self.assertNotIn("Record $500", reply)
        self.assertIn("live market data", reply)


class GoalTargetIntentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")

    def test_single_goal_is_found_by_name_fragment(self):
        goal = Goal.objects.create(user=self.user, name="Trip to Lisbon", target_amount=Decimal("1000"))
        handle_incoming_message(self.user, "set my trip goal to $2000")
        handle_incoming_message(self.user, "yes")
        goal.refresh_from_db()
        self.assertEqual(goal.target_amount, Decimal("2000"))

    def test_ambiguous_goal_name_asks_for_clarification(self):
        Goal.objects.create(user=self.user, name="Trip to Lisbon", target_amount=Decimal("1000"))
        Goal.objects.create(user=self.user, name="Trip to Rome", target_amount=Decimal("500"))
        reply = handle_incoming_message(self.user, "set my trip goal to $2000")
        self.assertIn("more than one goal", reply)
        self.assertFalse(PendingConfirmation.objects.filter(user=self.user).exists())

    def test_sole_goal_is_used_even_without_a_name_match(self):
        goal = Goal.objects.create(user=self.user, name="Emergency fund", target_amount=Decimal("1000"))
        handle_incoming_message(self.user, "update my goal to $3000")
        handle_incoming_message(self.user, "yes")
        goal.refresh_from_db()
        self.assertEqual(goal.target_amount, Decimal("3000"))


class ConversationLogTests(TestCase):
    def test_both_directions_are_logged(self):
        user = User.objects.create_user(username="alice", password="x")
        handle_incoming_message(user, "help")
        self.assertEqual(ConversationMessage.objects.filter(user=user, direction="inbound").count(), 1)
        self.assertEqual(ConversationMessage.objects.filter(user=user, direction="outbound").count(), 1)


class PhotonWebhookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.user.profile.photon_chat_id = "chat-abc"
        self.user.profile.save()
        self.client = Client()
        self.url = reverse("assistant:photon_webhook")

    @override_settings(DEBUG=True)
    def test_valid_payload_routes_to_the_right_user_and_replies(self):
        response = self.client.post(
            self.url, data=json.dumps({"guid": "g1", "text": "help", "chatId": "chat-abc"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("reply", response.json())

    @override_settings(DEBUG=True)
    def test_unknown_chat_id_does_not_error_or_leak_info(self):
        response = self.client.post(
            self.url, data=json.dumps({"guid": "g1", "text": "help", "chatId": "no-such-chat"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("isn't linked", response.json()["reply"])

    @override_settings(DEBUG=True)
    def test_missing_fields_returns_400(self):
        response = self.client.post(
            self.url, data=json.dumps({"chatId": "chat-abc"}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(DEBUG=True)
    def test_malformed_json_returns_400(self):
        response = self.client.post(self.url, data=b"not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @override_settings(DEBUG=False, IMESSAGE_WEBHOOK_SECRET="", PHOTON_WEBHOOK_SECRET="")
    def test_unsigned_request_is_rejected_when_debug_is_off(self):
        response = self.client.post(
            self.url, data=json.dumps({"text": "help", "chatId": "chat-abc"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("help", response.content.decode().lower())

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    @override_settings(PHOTON_WEBHOOK_SECRET="s3cret")
    def test_secret_mismatch_is_rejected(self):
        response = self.client.post(
            self.url, data=json.dumps({"text": "help", "chatId": "chat-abc"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(PHOTON_WEBHOOK_SECRET="s3cret")
    def test_correct_secret_is_accepted(self):
        response = self.client.post(
            self.url, data=json.dumps({"text": "help", "chatId": "chat-abc"}),
            content_type="application/json", HTTP_X_PHOTON_WEBHOOK_SECRET="s3cret",
        )
        self.assertEqual(response.status_code, 200)

    def _signed(self, body: str, secret: str = "whsec_test", timestamp: str | None = None):
        timestamp = timestamp or str(int(time.time()))
        digest = hmac.new(secret.encode(), f"v0:{timestamp}:{body}".encode(), hashlib.sha256).hexdigest()
        return timestamp, "v0=" + digest

    @override_settings(IMESSAGE_WEBHOOK_SECRET="whsec_test", DEBUG=False)
    def test_spectrum_messages_event_is_verified_and_not_marked_delivered(self):
        body = json.dumps({
            "event": "messages",
            "space": {"id": "chat-abc", "platform": "iMessage", "type": "dm"},
            "message": {
                "id": "spc-msg-1",
                "direction": "inbound",
                "sender": {"id": "+15550100", "platform": "iMessage"},
                "content": {"type": "text", "text": "help"},
            },
        })
        timestamp, signature = self._signed(body)
        response = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_SPECTRUM_SIGNATURE=signature,
            HTTP_X_SPECTRUM_TIMESTAMP=timestamp,
            HTTP_X_SPECTRUM_WEBHOOK_ID="wh-1",
            HTTP_X_SPECTRUM_EVENT="messages",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("budget", payload["reply"].lower())
        self.assertFalse(payload["delivered"])

        again = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_SPECTRUM_SIGNATURE=signature,
            HTTP_X_SPECTRUM_TIMESTAMP=timestamp,
            HTTP_X_SPECTRUM_WEBHOOK_ID="wh-1",
            HTTP_X_SPECTRUM_EVENT="messages",
        )
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["duplicate"])
        self.assertEqual(ConversationMessage.objects.filter(user=self.user, direction="inbound").count(), 1)

    @override_settings(IMESSAGE_WEBHOOK_SECRET="whsec_test", DEBUG=False)
    def test_stale_spectrum_timestamp_is_rejected(self):
        body = json.dumps({"event": "messages", "space": {"id": "chat-abc"}, "message": {"id": "m", "direction": "inbound", "content": {"type": "text", "text": "help"}}})
        timestamp, signature = self._signed(body, timestamp=str(int(time.time()) - 3600))
        response = self.client.post(
            self.url, data=body, content_type="application/json",
            HTTP_X_SPECTRUM_SIGNATURE=signature, HTTP_X_SPECTRUM_TIMESTAMP=timestamp,
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(IMESSAGE_WEBHOOK_SECRET="whsec_test", DEBUG=False)
    def test_bad_spectrum_signature_is_rejected(self):
        body = json.dumps({"event": "messages", "space": {"id": "chat-abc"}, "message": {"id": "m2", "direction": "inbound", "content": {"type": "text", "text": "help"}}})
        timestamp, _signature = self._signed(body)
        response = self.client.post(
            self.url, data=body, content_type="application/json",
            HTTP_X_SPECTRUM_SIGNATURE="v0=" + ("ab" * 32), HTTP_X_SPECTRUM_TIMESTAMP=timestamp,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(ConversationMessage.objects.count(), 0)

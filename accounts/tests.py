import time
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from authlib.jose import JsonWebKey, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from auth0_server_python.error import ApiError
from transactions.models import Transaction

from finovate.settings import _postgres_config_from_url

from budgets.models import IncomeSource, RecurringExpense
from budgets.services import build_budget_plan

from .auth0 import auth0_configured, get_auth0_client
from .identity import safe_next, sync_profile_from_claims
from .manual_setup import TAKE_HOME_INCOME_NAME, apply_manual_setup, has_manual_estimate, initial_from_existing
from .models import NotificationEvent, Profile


@override_settings(
    AUTH0_AUDIENCE="",
    AUTH0_DOMAIN="",
    AUTH0_CLIENT_ID="",
    AUTH0_CLIENT_SECRET="",
    AUTH0_SECRET="",
)
class Auth0UnconfiguredFallbackTests(TestCase):
    """With no Auth0 env vars set (the test default), the app must behave
    exactly as it did before this integration existed."""

    def test_auth0_configured_is_false_by_default(self):
        self.assertFalse(auth0_configured())

    def test_get_auth0_client_returns_none(self):
        self.assertIsNone(get_auth0_client())

    def test_auth0_login_falls_back_to_local_login_with_a_message(self):
        response = self.client.get(reverse("accounts:auth0_login"), follow=True)
        self.assertRedirects(response, reverse("accounts:login"))
        messages = list(response.context["messages"])
        self.assertTrue(any("isn't configured" in str(m) for m in messages))

    def test_signup_creates_a_local_account_when_auth0_is_off(self):
        cache.clear()
        response = self.client.post(reverse("accounts:signup"), {
            "username": "localuser",
            "email": "local@example.com",
            "password1": "a-strong-pass-123",
            "password2": "a-strong-pass-123",
        })
        self.assertRedirects(response, reverse("accounts:onboarding"))
        user = User.objects.get(username="localuser")
        self.assertTrue(user.has_usable_password())
        self.assertIsNone(user.profile.auth0_sub)

    def test_login_page_offers_only_the_local_form(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(response, "Continue with Auth0")
        self.assertContains(response, 'type="password"')

    def test_local_login_and_wrong_password(self):
        cache.clear()
        User.objects.create_user(username="localuser", password="a-strong-pass-123")
        bad = self.client.post(reverse("accounts:login"), {"username": "localuser", "password": "nope"})
        self.assertEqual(bad.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        good = self.client.post(reverse("accounts:login"), {"username": "localuser", "password": "a-strong-pass-123"})
        self.assertRedirects(good, reverse("accounts:onboarding"))

    def test_local_login_ignores_an_off_site_next(self):
        cache.clear()
        user = User.objects.create_user(username="localuser", password="a-strong-pass-123")
        user.profile.onboarding_completed = True
        user.profile.save()
        response = self.client.post(reverse("accounts:login"), {
            "username": "localuser", "password": "a-strong-pass-123", "next": "https://evil.example/",
        })
        self.assertRedirects(response, reverse("dashboard"))

    def test_login_page_shows_the_logo_and_no_demo_banner(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "brand/Finovate_Logo.svg")
        self.assertContains(response, 'rel="icon"')
        self.assertContains(response, "Finovate | Log in")
        self.assertNotContains(response, "Demo mode")
        self.assertNotContains(response, "phone number")


@override_settings(
    AUTH0_AUDIENCE="",
    AUTH0_DOMAIN="test.auth0.com",
    AUTH0_CLIENT_ID="cid",
    AUTH0_CLIENT_SECRET="secret",
    AUTH0_SECRET="test-secret",
    APP_BASE_URL="http://127.0.0.1:8000",
)
class Auth0ConfiguredTests(TestCase):
    def test_auth0_configured_is_true(self):
        self.assertTrue(auth0_configured())

    def test_login_page_shows_auth0_button(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "Continue with Auth0 (recommended)")
        self.assertContains(response, 'type="password"')

    def test_local_account_still_works_when_auth0_is_configured(self):
        cache.clear()
        response = self.client.post(reverse("accounts:signup"), {
            "method": "local",
            "username": "localuser",
            "password1": "a-strong-pass-123",
            "password2": "a-strong-pass-123",
        })
        self.assertRedirects(response, reverse("accounts:onboarding"))
        self.client.post(reverse("accounts:logout"))
        response = self.client.post(reverse("accounts:login"), {
            "method": "local", "username": "localuser", "password": "a-strong-pass-123",
        })
        self.assertRedirects(response, reverse("accounts:onboarding"))
        self.assertEqual(self.client.get(reverse("accounts:onboarding")).status_code, 200)

    def test_auth0_user_cannot_log_in_with_a_local_password(self):
        cache.clear()
        profile, _ = sync_profile_from_claims({"sub": "auth0|x", "email": "x@example.com", "email_verified": True})
        response = self.client.post(reverse("accounts:login"), {
            "method": "local", "username": profile.user.username, "password": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def _client(self, result=None, error=None):
        if isinstance(result, dict):
            user = (result.get("state_data") or {}).get("user")
            if isinstance(user, dict) and user.get("sub"):
                user.setdefault("email_verified", True)
        mock_client = MagicMock()
        if error is not None:
            mock_client.complete_interactive_login = AsyncMock(side_effect=error)
        else:
            mock_client.complete_interactive_login = AsyncMock(return_value=result)
        mock_client.logout = AsyncMock(
            return_value="https://test.auth0.com/v2/logout?client_id=cid"
        )
        return mock_client

    @patch("accounts.views.get_auth0_client")
    def test_successful_callback_creates_a_user_mapped_by_sub(self, mock_get_client):
        mock_get_client.return_value = self._client({
            "state_data": {"user": {"sub": "auth0|abc123", "email": "newbie@example.com"}}
        })

        response = self.client.get(reverse("accounts:auth0_callback"))
        self.assertEqual(response.status_code, 302)

        profile = Profile.objects.get(auth0_sub="auth0|abc123")
        self.assertEqual(profile.user.email, "newbie@example.com")

    @patch("accounts.views.get_auth0_client")
    def test_repeat_login_with_same_sub_does_not_duplicate_the_user(self, mock_get_client):
        mock_get_client.return_value = self._client({
            "state_data": {"user": {"sub": "auth0|repeat", "email": "x@example.com"}}
        })

        self.client.get(reverse("accounts:auth0_callback"))
        self.client.logout()
        self.client.get(reverse("accounts:auth0_callback"))

        self.assertEqual(Profile.objects.filter(auth0_sub="auth0|repeat").count(), 1)

    @patch("accounts.views.get_auth0_client")
    def test_two_different_auth0_accounts_sharing_an_email_are_not_merged(self, mock_get_client):
        mock_client = self._client({
            "state_data": {"user": {"sub": "auth0|first", "email": "shared@example.com"}}
        })
        mock_get_client.return_value = mock_client
        self.client.get(reverse("accounts:auth0_callback"))
        self.client.logout()

        mock_client.complete_interactive_login = AsyncMock(return_value={
            "state_data": {"user": {"sub": "auth0|second", "email": "shared@example.com"}}
        })
        self.client.get(reverse("accounts:auth0_callback"))

        self.assertEqual(User.objects.filter(email="shared@example.com").count(), 2)

    @patch("accounts.views.get_auth0_client")
    def test_token_exchange_failure_does_not_create_a_user(self, mock_get_client):
        mock_get_client.return_value = self._client(error=Exception("boom"))

        response = self.client.get(reverse("accounts:auth0_callback"), follow=True)
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertEqual(User.objects.count(), 0)

    @patch("accounts.views.get_auth0_client")
    def test_missing_sub_claim_does_not_create_a_user(self, mock_get_client):
        mock_get_client.return_value = self._client({
            "state_data": {"user": {"email": "no-sub@example.com"}}
        })

        response = self.client.get(reverse("accounts:auth0_callback"), follow=True)
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertEqual(User.objects.count(), 0)

    @patch("accounts.views.get_auth0_client")
    def test_new_auth0_user_is_sent_to_onboarding(self, mock_get_client):
        mock_get_client.return_value = self._client({
            "state_data": {"user": {"sub": "auth0|onboard-me", "email": "o@example.com"}}
        })

        response = self.client.get(reverse("accounts:auth0_callback"), follow=True)
        self.assertRedirects(response, reverse("accounts:onboarding"))

    @patch("accounts.views.get_auth0_client")
    def test_logout_after_auth0_login_redirects_to_auth0_federated_logout(self, mock_get_client):
        mock_get_client.return_value = self._client({
            "state_data": {"user": {"sub": "auth0|logout-test", "email": "l@example.com"}}
        })
        self.client.get(reverse("accounts:auth0_callback"))

        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("test.auth0.com/v2/logout", response.url)


class LocalLogoutUnaffectedTests(TestCase):
    """A user who never touched Auth0 just gets a normal local logout."""

    def test_local_user_logout_redirects_to_landing_not_auth0(self):
        user = User.objects.create_user(username="localonly", password="x")
        client = Client()
        client.force_login(user)
        response = client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("landing"))


class ThemeSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="theme-user", password="test-password-123"
        )
        self.client.force_login(self.user)

    def test_settings_page_exposes_saved_theme_choice(self):
        response = self.client.get(reverse("accounts:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Color theme")
        self.assertContains(response, '<option value="dark">Dark</option>')
        self.assertContains(response, 'data-theme="system"')

    def test_dark_theme_setting_is_saved_and_applied_to_pages(self):
        response = self.client.post(reverse("accounts:settings"), {
            "income_cadence": "monthly",
            "risk_comfort": "unspecified",
            "cash_reserve_target": "0.00",
            "budget_warning_threshold_percent": "80",
            "notify_budget_warnings": "on",
            "notify_goal_milestones": "on",
            "theme": "dark",
        })

        self.assertRedirects(response, reverse("accounts:settings"))
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.theme, "dark")
        self.assertContains(self.client.get(reverse("accounts:settings")), 'data-theme="dark"')


class PostgresUrlParsingTests(TestCase):
    def test_parses_a_supabase_style_connection_string(self):
        config = _postgres_config_from_url(
            "postgresql://postgres.myproj:p%40ss@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "postgres")
        self.assertEqual(config["USER"], "postgres.myproj")
        self.assertEqual(config["HOST"], "aws-0-us-east-1.pooler.supabase.com")
        self.assertEqual(config["PORT"], 6543)
        self.assertEqual(config["OPTIONS"], {"sslmode": "require"})

    def test_percent_encoded_special_characters_in_password_are_decoded(self):
        config = _postgres_config_from_url(
            "postgresql://user:p%40ss%3Aword@localhost:5432/mydb"
        )
        self.assertEqual(config["PASSWORD"], "p@ss:word")


class SafeRedirectTests(TestCase):
    def test_off_site_targets_are_rejected(self):
        self.assertEqual(safe_next("https://evil.example/phish"), "")
        self.assertEqual(safe_next("//evil.example"), "")
        self.assertEqual(safe_next("/\\evil.example"), "")
        self.assertEqual(safe_next("/dashboard/"), "/dashboard/")


@override_settings(
    AUTH0_AUDIENCE="",
    AUTH0_DOMAIN="test.auth0.com",
    AUTH0_CLIENT_ID="cid",
    AUTH0_CLIENT_SECRET="secret",
    AUTH0_SECRET="test-secret",
    APP_BASE_URL="http://127.0.0.1:8000",
)
class Auth0RegistrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def _client(self, result):
        user = (result.get("state_data") or {}).get("user")
        if isinstance(user, dict) and user.get("sub"):
            user.setdefault("email_verified", True)
        mock_client = MagicMock()
        mock_client.complete_interactive_login = AsyncMock(return_value=result)
        mock_client.start_interactive_login = AsyncMock(
            return_value="https://test.auth0.com/authorize?screen_hint=signup"
        )
        mock_client.logout = AsyncMock(return_value="https://test.auth0.com/v2/logout?client_id=cid")
        return mock_client

    @patch("accounts.views.get_auth0_client")
    def test_signup_redirects_to_auth0_and_creates_no_user(self, mock_get_client):
        mock_get_client.return_value = self._client({})
        response = self.client.post(reverse("accounts:signup"), {
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "phone": "+1 (555) 010-2030",
            "password1": "should-not-be-stored",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("test.auth0.com/authorize", response.url)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(self.client.session["auth_status"], "registration_started")
        self.assertNotContains(response, "should-not-be-stored", status_code=302)

    @patch("accounts.views.get_auth0_client")
    def test_unverified_user_cannot_open_the_dashboard(self, mock_get_client):
        mock_get_client.return_value = self._client({
            "state_data": {"user": {
                "sub": "auth0|pending",
                "email": "pending@example.com",
                "email_verified": False,
            }}
        })
        response = self.client.get(reverse("accounts:auth0_callback"), follow=True)
        self.assertRedirects(response, reverse("accounts:verify"))
        self.assertContains(response, "Verification pending")
        self.assertContains(response, "Status: verification_pending")
        self.assertContains(response, "not fully verified")
        profile = Profile.objects.get(auth0_sub="auth0|pending")
        self.assertFalse(profile.email_verified)
        self.assertFalse(profile.user.has_usable_password())
        dashboard = self.client.get(reverse("dashboard"))
        self.assertRedirects(dashboard, reverse("accounts:verify"), fetch_redirect_response=False)

    @patch("accounts.views.get_auth0_client")
    def test_callback_ignores_an_off_site_next_url(self, mock_get_client):
        mock_client = self._client({
            "state_data": {"user": {"sub": "auth0|next", "email": "next@example.com"}},
            "app_state": {"next": "https://evil.example/phish"},
        })
        mock_get_client.return_value = mock_client
        self.client.get(reverse("accounts:auth0_callback"))
        profile = Profile.objects.get(auth0_sub="auth0|next")
        profile.onboarding_completed = True
        profile.save(update_fields=["onboarding_completed", "updated_at"])
        self.client.logout()
        response = self.client.get(reverse("accounts:auth0_callback"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example", response.url)
        self.assertEqual(response.url, reverse("dashboard"))

    @patch("accounts.views.get_auth0_client")
    def test_logout_ignores_a_posted_return_url(self, mock_get_client):
        mock_get_client.return_value = self._client({
            "state_data": {"user": {"sub": "auth0|bye", "email": "bye@example.com"}}
        })
        self.client.get(reverse("accounts:auth0_callback"))
        response = self.client.post(reverse("accounts:logout"), {"return_to": "https://evil.example"})
        self.assertIn("test.auth0.com/v2/logout", response.url)
        self.assertNotIn("evil.example", response.url)

    @patch("accounts.identity.attempt_messaging_welcome", side_effect=OSError("provider down"))
    def test_profile_sync_is_idempotent_when_welcome_delivery_fails(self, _send):
        claims = {
            "sub": "auth0|welcome",
            "email": "welcome@example.com",
            "email_verified": True,
            "name": "Welcome User",
        }
        first, created = sync_profile_from_claims(claims, {"phone": "+15550102030"})
        second, created_again = sync_profile_from_claims(claims, {"phone": "+15550102030"})
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Profile.objects.filter(auth0_sub="auth0|welcome").count(), 1)
        self.assertEqual(
            NotificationEvent.objects.filter(user=first.user, event_type="welcome").count(),
            1,
        )
        self.assertEqual(
            NotificationEvent.objects.filter(user=first.user, event_type="account_created").count(),
            1,
        )
        self.assertFalse(first.user.has_usable_password())
        self.assertFalse(first.phone_verified)
        self.assertEqual(first.phone_number, "+15550102030")

    @patch("accounts.views.get_auth0_client")
    def test_blocked_login_creates_no_profile(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.complete_interactive_login = AsyncMock(
            side_effect=ApiError("unauthorized", "user is blocked")
        )
        mock_get_client.return_value = mock_client
        response = self.client.get(reverse("accounts:auth0_callback"), follow=True)
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertContains(response, "blocked or disabled")
        self.assertEqual(User.objects.count(), 0)

    def test_signup_rate_limit_does_not_create_users(self):
        with patch("accounts.views.get_auth0_client") as mock_get_client:
            mock_get_client.return_value = self._client({})
            last = None
            for _ in range(11):
                last = self.client.post(reverse("accounts:signup"), {
                    "name": "Rate Limit",
                    "email": "rate@example.com",
                })
        self.assertEqual(last.status_code, 429)
        self.assertEqual(User.objects.count(), 0)
        self.assertNotContains(last, "already", status_code=429)


@override_settings(
    AUTH0_DOMAIN="test.auth0.com",
    AUTH0_CLIENT_ID="cid",
    AUTH0_CLIENT_SECRET="secret",
    AUTH0_SECRET="test-secret",
    AUTH0_AUDIENCE="https://finovate.biz/api",
    APP_BASE_URL="http://127.0.0.1:8000",
)
class AccessTokenApiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        key = JsonWebKey.import_key(pem, {"kid": "test-key", "use": "sig"})
        cls.private = key
        cls.jwks = {"keys": [key.as_dict(is_private=False)]}

    def setUp(self):
        cache.clear()
        self.jwks_patch = patch("accounts.tokens._jwks", return_value=self.jwks)
        self.jwks_patch.start()
        self.alice = self._profile("auth0|alice", verified=True)
        self.bob = self._profile("auth0|bob", verified=True)
        Transaction.objects.create(
            user=self.bob.user,
            kind=Transaction.Kind.EXPENSE,
            amount=Decimal("10.00"),
            occurred_on=date(2026, 1, 1),
        )

    def tearDown(self):
        self.jwks_patch.stop()

    def _profile(self, sub, verified):
        user = User.objects.create(username=sub.replace("|", "_"))
        user.set_unusable_password()
        user.save()
        profile = user.profile
        profile.auth0_sub = sub
        profile.email_verified = verified
        profile.identity_status = "verification_completed" if verified else "verification_pending"
        profile.onboarding_completed = True
        profile.save()
        return profile

    def _token(self, sub, audience="https://finovate.biz/api", exp_delta=600):
        now = int(time.time())
        payload = {
            "iss": "https://test.auth0.com/",
            "aud": audience,
            "sub": sub,
            "exp": now + exp_delta,
            "iat": now,
        }
        return jwt.encode({"alg": "RS256", "kid": "test-key"}, payload, self.private).decode()

    def test_missing_token_is_rejected(self):
        self.client.force_login(self.alice.user)
        response = self.client.get(reverse("api_me"))
        self.assertEqual(response.status_code, 401)

    def test_id_token_audience_is_rejected(self):
        token = self._token("auth0|alice", audience="cid")
        response = self.client.get(reverse("api_me"), HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 401)

    def test_expired_token_is_rejected(self):
        token = self._token("auth0|alice", exp_delta=-120)
        response = self.client.get(reverse("api_me"), HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 401)

    def test_access_token_returns_only_that_users_records(self):
        alice = self.client.get(
            reverse("api_me"),
            HTTP_AUTHORIZATION=f"Bearer {self._token('auth0|alice')}",
        )
        bob = self.client.get(
            reverse("api_me"),
            HTTP_AUTHORIZATION=f"Bearer {self._token('auth0|bob')}",
        )
        self.assertEqual(alice.status_code, 200)
        self.assertEqual(alice.json()["transaction_count"], 0)
        self.assertEqual(bob.json()["transaction_count"], 1)

    def test_unverified_access_token_does_not_return_financial_data(self):
        pending = self._profile("auth0|pending", verified=False)
        token = self._token(pending.auth0_sub)
        response = self.client.get(reverse("api_me"), HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("transaction_count", response.json())
        self.assertEqual(response.json()["identity_status"], "verification_pending")


@override_settings(
    AUTH0_AUDIENCE="",
    AUTH0_DOMAIN="test.auth0.com",
    AUTH0_CLIENT_ID="cid",
    AUTH0_CLIENT_SECRET="secret",
    AUTH0_SECRET="test-secret",
    APP_BASE_URL="http://127.0.0.1:8000",
)
class ExpiredAuth0SessionTests(TestCase):
    @patch("accounts.views.get_auth0_client")
    def test_expired_session_is_logged_out_before_the_dashboard(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.complete_interactive_login = AsyncMock(return_value={
            "state_data": {"user": {
                "sub": "auth0|expired",
                "email": "expired@example.com",
                "email_verified": True,
            }}
        })
        mock_get_client.return_value = mock_client
        self.client.get(reverse("accounts:auth0_callback"))
        profile = Profile.objects.get(auth0_sub="auth0|expired")
        profile.onboarding_completed = True
        profile.save(update_fields=["onboarding_completed", "updated_at"])
        session = self.client.session
        session["auth0_access_exp"] = 1
        session.save()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        follow = self.client.get(reverse("dashboard"))
        self.assertNotEqual(follow.status_code, 200)


class ManualFinancialSetupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="manual-user", password="pw12345")
        self.client.force_login(self.user)

    def test_minimum_fields_only_creates_one_income_and_one_expense_row(self):
        response = self.client.post(reverse("accounts:manual_setup"), {
            "take_home_income": "4000.00",
            "total_monthly_expenses": "3000.00",
        })
        self.assertRedirects(response, reverse("accounts:manual_setup_summary"))
        self.assertEqual(IncomeSource.objects.filter(user=self.user, is_active=True).count(), 1)
        self.assertEqual(RecurringExpense.objects.filter(user=self.user, is_active=True).count(), 1)
        plan = build_budget_plan(self.user)
        self.assertEqual(plan.monthly_income, Decimal("4000.00"))
        self.assertEqual(plan.monthly_recurring_expenses, Decimal("3000.00"))
        self.assertEqual(plan.leftover_after_plan, Decimal("1000.00"))

    def test_no_fields_required_a_single_field_is_enough(self):
        response = self.client.post(reverse("accounts:manual_setup"), {"minimum_cash_reserve": "500.00"})
        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.cash_reserve_target, Decimal("500.00"))

    def test_breakdown_takes_precedence_over_lump_total_never_both(self):
        self.client.post(reverse("accounts:manual_setup"), {
            "total_monthly_expenses": "3000.00",
            "housing": "1200.00",
            "groceries": "400.00",
        })
        active_expenses = RecurringExpense.objects.filter(user=self.user, is_active=True)
        self.assertEqual(active_expenses.count(), 2)
        total = sum((e.amount for e in active_expenses), Decimal("0"))
        self.assertEqual(total, Decimal("1600.00"))
        plan = build_budget_plan(self.user)
        self.assertEqual(plan.monthly_recurring_expenses, Decimal("1600.00"))

    def test_negative_amount_is_rejected(self):
        response = self.client.post(reverse("accounts:manual_setup"), {"take_home_income": "-100.00"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(IncomeSource.objects.filter(user=self.user).count(), 0)

    def test_negative_surplus_is_a_shortfall_not_hidden(self):
        self.client.post(reverse("accounts:manual_setup"), {
            "take_home_income": "1000.00",
            "total_monthly_expenses": "3000.00",
        })
        response = self.client.get(reverse("accounts:manual_setup_summary"))
        plan = response.context["plan"]
        self.assertEqual(plan.leftover_after_plan, Decimal("-2000.00"))
        self.assertContains(response, "shortfall")

    def test_current_savings_and_goal_persist_across_sessions(self):
        self.client.post(reverse("accounts:manual_setup"), {
            "current_savings_balance": "1500.00",
            "monthly_savings_goal": "200.00",
        })
        self.client.logout()
        self.client.force_login(self.user)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.manual_savings_balance, Decimal("1500.00"))
        self.assertEqual(self.user.profile.manual_monthly_savings_goal, Decimal("200.00"))
        self.assertIsNotNone(self.user.profile.manual_savings_balance_updated_at)

    def test_resubmitting_the_form_updates_rather_than_duplicates(self):
        apply_manual_setup(self.user, {"take_home_income": Decimal("4000.00")})
        apply_manual_setup(self.user, {"take_home_income": Decimal("4500.00")})
        rows = IncomeSource.objects.filter(user=self.user, name=TAKE_HOME_INCOME_NAME)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().amount, Decimal("4500.00"))

    def test_manual_estimate_never_fabricates_transactions(self):
        apply_manual_setup(self.user, {"take_home_income": Decimal("4000.00"), "total_monthly_expenses": Decimal("3000.00")})
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)
        self.assertTrue(has_manual_estimate(self.user))

    def test_initial_from_existing_prefills_the_form_for_editing(self):
        apply_manual_setup(self.user, {"take_home_income": Decimal("4000.00"), "minimum_cash_reserve": Decimal("300.00")})
        initial = initial_from_existing(self.user)
        self.assertEqual(initial["take_home_income"], Decimal("4000.00"))
        self.assertEqual(initial["minimum_cash_reserve"], Decimal("300.00"))

    def test_manual_setup_does_not_overwrite_an_existing_live_balance(self):
        # cash_reserve_target is also used by live-connection logic elsewhere;
        # submitting the form only touches it when the field was filled in.
        self.user.profile.cash_reserve_target = Decimal("999.00")
        self.user.profile.save(update_fields=["cash_reserve_target", "updated_at"])
        apply_manual_setup(self.user, {"take_home_income": Decimal("1000.00")})
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.cash_reserve_target, Decimal("999.00"))

    def test_other_user_cannot_see_or_affect_this_users_manual_estimate(self):
        apply_manual_setup(self.user, {"take_home_income": Decimal("4000.00")})
        other = User.objects.create_user(username="other-user", password="pw12345")
        self.client.force_login(other)
        self.assertFalse(has_manual_estimate(other))
        response = self.client.get(reverse("accounts:manual_setup_summary"))
        plan = response.context["plan"]
        self.assertEqual(plan.monthly_income, Decimal("0"))

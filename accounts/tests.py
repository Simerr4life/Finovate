from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from finovate.settings import _postgres_config_from_url

from .auth0 import auth0_configured, get_auth0_client
from .models import Profile


@override_settings(
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

    def test_local_signup_still_works(self):
        response = self.client.post(reverse("accounts:signup"), {
            "username": "newlocaluser", "password1": "a-strong-pass-123", "password2": "a-strong-pass-123",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newlocaluser").exists())

    def test_login_page_does_not_show_auth0_button(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(response, "Log in with Auth0")

    def test_login_page_shows_the_logo_and_no_demo_banner(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "brand/Finovate_Logo.svg")
        self.assertNotContains(response, "Demo mode")


@override_settings(
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
        self.assertContains(response, "Log in with Auth0")

    def _client(self, result=None, error=None):
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

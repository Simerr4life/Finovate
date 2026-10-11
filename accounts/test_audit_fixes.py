"""Regressions found in the codebase audit: webhook auth, rate limiting,
backup timestamp parsing, and server-side validation of profile settings."""

from datetime import UTC, datetime

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .auth0_backup import _parse_created, upsert_from_auth0_event
from .models import Auth0UserBackup
from .views import _client_ip


@override_settings(AUTH0_ACTION_SECRET="action-secret")
class SignupWebhookTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_wrong_secret_of_same_length_is_rejected(self):
        response = self.client.post(
            reverse("accounts:auth0_signup_webhook"),
            data='{"user":{"user_id":"auth0|x"}}',
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer action-secreT",
        )
        self.assertEqual(response.status_code, 401)

    def test_epoch_created_at_is_stored_instead_of_failing(self):
        # Django 5 removed django.utils.timezone.utc; this used to raise.
        record = upsert_from_auth0_event(
            {"user": {"user_id": "auth0|epoch", "created_at": 1760000000}}
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.sync_status, Auth0UserBackup.SyncStatus.SYNCED)
        self.assertEqual(record.signup_created_at, datetime.fromtimestamp(1760000000, tz=UTC))

    def test_naive_timestamps_are_read_as_utc(self):
        parsed = _parse_created("2026-10-01T12:00:00")
        self.assertEqual(parsed, datetime(2026, 10, 1, 12, tzinfo=UTC))
        self.assertEqual(_parse_created(datetime(2026, 10, 1, 12)), datetime(2026, 10, 1, 12, tzinfo=UTC))


class ClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(ON_VERCEL=False)
    def test_forwarded_header_is_ignored_off_vercel(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(_client_ip(request), "10.0.0.1")

    @override_settings(ON_VERCEL=True)
    def test_forwarded_header_is_used_behind_vercel(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(_client_ip(request), "1.2.3.4")

    @override_settings(ON_VERCEL=False, SUPABASE_URL="", SUPABASE_PUBLIC_KEY="", AUTH0_DOMAIN="")
    def test_rotating_forwarded_for_cannot_dodge_the_login_limit(self):
        cache.clear()
        last = None
        for attempt in range(21):
            last = self.client.post(reverse("accounts:login"), HTTP_X_FORWARDED_FOR=f"9.9.9.{attempt}")
        self.assertEqual(last.status_code, 429)


class ProfileSettingsValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="settings-user", password="pw-12345-x")
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        self.client.force_login(self.user)

    def _post(self, **overrides):
        data = {
            "income_cadence": "monthly",
            "risk_comfort": "unspecified",
            "cash_reserve_target": "0",
            "budget_warning_threshold_percent": "80",
            "theme": "system",
        }
        data.update(overrides)
        return self.client.post(reverse("accounts:settings"), data)

    def test_out_of_range_threshold_is_rejected(self):
        for value in ("0", "250"):
            response = self._post(budget_warning_threshold_percent=value)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "from 1 to 100")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.budget_warning_threshold_percent, 80)

    def test_negative_cash_reserve_is_rejected(self):
        response = self._post(cash_reserve_target="-50")
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.cash_reserve_target, 0)

    def test_valid_settings_still_save(self):
        response = self._post(budget_warning_threshold_percent="65", cash_reserve_target="250")
        self.assertRedirects(response, reverse("accounts:settings"))
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.budget_warning_threshold_percent, 65)

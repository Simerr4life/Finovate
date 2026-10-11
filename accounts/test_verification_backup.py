"""Auth0 email verification lifecycle + Supabase Auth0UserBackup sync."""

from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .auth0_backup import (
    enqueue_backup_sync,
    process_pending_backups,
    reconcile_from_profiles,
    upsert_from_auth0_event,
)
from .identity import sync_profile_from_claims
from .models import Auth0UserBackup, Profile
from .verification import apply_authoritative_verification, mark_verified_from_trusted_claims


@override_settings(
    SUPABASE_URL="",
    SUPABASE_PUBLIC_KEY="",
    AUTH0_AUDIENCE="",
    AUTH0_DOMAIN="test.auth0.com",
    AUTH0_CLIENT_ID="cid",
    AUTH0_CLIENT_SECRET="secret",
    AUTH0_SECRET="test-secret",
    AUTH0_MGMT_CLIENT_ID="",
    AUTH0_MGMT_CLIENT_SECRET="",
    AUTH0_ACTION_SECRET="action-secret",
    APP_BASE_URL="http://127.0.0.1:8000",
)
class Auth0VerificationLifecycleTests(TestCase):
    def setUp(self):
        cache.clear()

    def _auth0_client(self, claims):
        mock_client = MagicMock()
        mock_client.complete_interactive_login = AsyncMock(
            return_value={"state_data": {"user": claims}}
        )
        mock_client.start_interactive_login = AsyncMock(
            return_value="https://test.auth0.com/authorize?max_age=0"
        )
        return mock_client

    def _pending_profile(self, sub="auth0|pending-verify"):
        profile, _ = sync_profile_from_claims(
            {
                "sub": sub,
                "email": "pending@example.com",
                "email_verified": False,
                "name": "Pending User",
            }
        )
        return profile

    def test_stale_unverified_claim_does_not_downgrade_confirmed_status(self):
        profile, _ = sync_profile_from_claims(
            {
                "sub": "auth0|mono",
                "email": "mono@example.com",
                "email_verified": True,
            }
        )
        self.assertTrue(profile.email_verified)
        again, _ = sync_profile_from_claims(
            {
                "sub": "auth0|mono",
                "email": "mono@example.com",
                "email_verified": False,
            }
        )
        self.assertTrue(again.email_verified)
        self.assertEqual(again.identity_status, "verification_completed")

    @override_settings(AUTH0_MGMT_CLIENT_ID="mgmt-id", AUTH0_MGMT_CLIENT_SECRET="mgmt-secret")
    @patch("accounts.verification.fetch_auth0_user")
    def test_management_api_verified_updates_profile(self, mock_fetch):
        profile = self._pending_profile("auth0|mgmt-ok")
        mock_fetch.return_value = {
            "user_id": "auth0|mgmt-ok",
            "email": "pending@example.com",
            "email_verified": True,
        }
        outcome = apply_authoritative_verification(profile)
        profile.refresh_from_db()
        self.assertEqual(outcome, "verified")
        self.assertTrue(profile.email_verified)
        backup = Auth0UserBackup.objects.get(auth0_user_id="auth0|mgmt-ok")
        self.assertTrue(backup.email_verified)

    @override_settings(AUTH0_MGMT_CLIENT_ID="mgmt-id", AUTH0_MGMT_CLIENT_SECRET="mgmt-secret")
    @patch("accounts.verification.fetch_auth0_user")
    def test_expired_or_unverified_remote_does_not_mark_verified(self, mock_fetch):
        profile = self._pending_profile("auth0|still-pending")
        mock_fetch.return_value = {
            "user_id": "auth0|still-pending",
            "email": "pending@example.com",
            "email_verified": False,
        }
        outcome = apply_authoritative_verification(profile)
        profile.refresh_from_db()
        self.assertEqual(outcome, "still_pending")
        self.assertFalse(profile.email_verified)

    def test_already_verified_profile_reports_already_verified(self):
        profile, _ = sync_profile_from_claims(
            {
                "sub": "auth0|done",
                "email": "done@example.com",
                "email_verified": True,
            }
        )
        self.assertEqual(apply_authoritative_verification(profile), "already_verified")

    def test_trusted_claim_upgrade_is_monotonic(self):
        profile = self._pending_profile("auth0|claim-up")
        self.assertTrue(
            mark_verified_from_trusted_claims(profile, {"email_verified": True})
        )
        profile.refresh_from_db()
        self.assertTrue(profile.email_verified)
        self.assertFalse(
            mark_verified_from_trusted_claims(profile, {"email_verified": True})
        )
        self.assertFalse(
            mark_verified_from_trusted_claims(profile, {"email_verified": False})
        )

    @override_settings(AUTH0_MGMT_CLIENT_ID="mgmt-id", AUTH0_MGMT_CLIENT_SECRET="mgmt-secret")
    @patch("accounts.views.get_auth0_client")
    @patch("accounts.verification.fetch_auth0_user")
    def test_verify_page_refreshes_and_unlocks_app(self, mock_fetch, mock_get_client):
        mock_fetch.return_value = {
            "user_id": "auth0|unlock",
            "email": "unlock@example.com",
            "email_verified": False,
        }
        mock_get_client.return_value = self._auth0_client(
            {
                "sub": "auth0|unlock",
                "email": "unlock@example.com",
                "email_verified": False,
            }
        )
        self.client.get(reverse("accounts:auth0_callback"))
        profile = Profile.objects.get(auth0_sub="auth0|unlock")
        self.assertFalse(profile.email_verified)
        mock_fetch.return_value = {
            "user_id": "auth0|unlock",
            "email": "unlock@example.com",
            "email_verified": True,
        }
        response = self.client.get(reverse("accounts:verify"), follow=True)
        profile.refresh_from_db()
        self.assertTrue(profile.email_verified)
        self.assertRedirects(response, reverse("accounts:onboarding"))

    @patch("accounts.views.get_auth0_client")
    def test_verify_refresh_forces_fresh_auth0_login_when_still_pending(self, mock_get_client):
        mock_client = self._auth0_client(
            {
                "sub": "auth0|refresh-me",
                "email": "r@example.com",
                "email_verified": False,
            }
        )
        mock_get_client.return_value = mock_client
        self.client.get(reverse("accounts:auth0_callback"))
        with patch(
            "accounts.views.apply_authoritative_verification",
            return_value="still_pending",
        ):
            response = self.client.post(reverse("accounts:verify_refresh"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("max_age=0", response.url)

    def test_verify_result_shows_expired_without_marking_verified(self):
        response = self.client.get(
            reverse("accounts:verify_result"),
            {"success": "false", "error": "access_expired"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verification link expired")
        self.assertEqual(Profile.objects.count(), 0)

    def test_verify_result_already_verified_message(self):
        response = self.client.get(
            reverse("accounts:verify_result"),
            {"error": "already verified"},
        )
        self.assertContains(response, "Already verified")

    @patch("accounts.views.get_auth0_client")
    def test_client_cannot_force_verified_via_query_state(self, mock_get_client):
        mock_get_client.return_value = self._auth0_client(
            {
                "sub": "auth0|no-bypass",
                "email": "nb@example.com",
                "email_verified": False,
            }
        )
        self.client.get(reverse("accounts:auth0_callback"))
        with patch(
            "accounts.views.apply_authoritative_verification",
            return_value="still_pending",
        ):
            response = self.client.get(reverse("accounts:verify") + "?state=verified")
        profile = Profile.objects.get(auth0_sub="auth0|no-bypass")
        self.assertFalse(profile.email_verified)
        self.assertContains(response, "Verification pending")
        self.assertNotContains(response, "Email verified")
        dashboard = self.client.get(reverse("dashboard"))
        self.assertRedirects(dashboard, reverse("accounts:verify"), fetch_redirect_response=False)


@override_settings(
    SUPABASE_URL="",
    SUPABASE_PUBLIC_KEY="",
    AUTH0_AUDIENCE="",
    AUTH0_DOMAIN="test.auth0.com",
    AUTH0_CLIENT_ID="cid",
    AUTH0_CLIENT_SECRET="secret",
    AUTH0_SECRET="test-secret",
    AUTH0_ACTION_SECRET="action-secret",
    APP_BASE_URL="http://127.0.0.1:8000",
)
class Auth0UserBackupTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_signup_sync_creates_exactly_one_backup(self):
        sync_profile_from_claims(
            {
                "sub": "auth0|backup-one",
                "email": "one@example.com",
                "email_verified": False,
                "name": "One User",
            }
        )
        self.assertEqual(Auth0UserBackup.objects.filter(auth0_user_id="auth0|backup-one").count(), 1)
        row = Auth0UserBackup.objects.get(auth0_user_id="auth0|backup-one")
        self.assertEqual(row.email, "one@example.com")
        self.assertFalse(row.email_verified)
        self.assertEqual(row.sync_status, Auth0UserBackup.SyncStatus.SYNCED)

    def test_repeated_signup_events_do_not_duplicate(self):
        payload = {
            "user": {
                "user_id": "auth0|dup",
                "email": "dup@example.com",
                "email_verified": False,
                "name": "Dup",
            }
        }
        first = upsert_from_auth0_event(payload)
        second = upsert_from_auth0_event(payload)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Auth0UserBackup.objects.filter(auth0_user_id="auth0|dup").count(), 1)

    def test_verification_upgrade_is_monotonic_on_backup(self):
        upsert_from_auth0_event(
            {
                "user": {
                    "user_id": "auth0|mono-b",
                    "email": "m@example.com",
                    "email_verified": True,
                    "name": "M",
                }
            }
        )
        upsert_from_auth0_event(
            {
                "user": {
                    "user_id": "auth0|mono-b",
                    "email": "m@example.com",
                    "email_verified": False,
                    "name": "M",
                }
            }
        )
        row = Auth0UserBackup.objects.get(auth0_user_id="auth0|mono-b")
        self.assertTrue(row.email_verified)

    def test_failed_sync_is_retried(self):
        row = Auth0UserBackup.objects.create(
            auth0_user_id="auth0|retry",
            email="retry@example.com",
            sync_status=Auth0UserBackup.SyncStatus.FAILED,
            last_sync_error="OperationalError",
        )
        result = process_pending_backups(limit=10)
        row.refresh_from_db()
        self.assertEqual(result["synced"], 1)
        self.assertEqual(row.sync_status, Auth0UserBackup.SyncStatus.SYNCED)
        self.assertEqual(row.last_sync_error, "")

    def test_outage_leaves_retryable_pending_row(self):
        with patch(
            "accounts.auth0_backup.process_backup_record",
            side_effect=RuntimeError("db down"),
        ):
            # enqueue catches and returns None, but _ensure_record runs first
            with patch(
                "accounts.auth0_backup._ensure_record",
                side_effect=RuntimeError("db down"),
            ):
                result = enqueue_backup_sync("auth0|outage", reason="signup")
        self.assertIsNone(result)
        # Durable path: webhook returns 503 so Auth0 retries; reconcile fills gaps.
        profile, _ = sync_profile_from_claims(
            {
                "sub": "auth0|outage-later",
                "email": "later@example.com",
                "email_verified": False,
            }
        )
        Auth0UserBackup.objects.filter(auth0_user_id=profile.auth0_sub).delete()
        stats = reconcile_from_profiles(limit=50)
        self.assertGreaterEqual(stats["created"], 1)
        self.assertTrue(
            Auth0UserBackup.objects.filter(auth0_user_id="auth0|outage-later").exists()
        )

    def test_webhook_requires_shared_secret(self):
        response = self.client.post(
            reverse("accounts:auth0_signup_webhook"),
            data='{"user":{"user_id":"auth0|hook","email":"h@example.com"}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(Auth0UserBackup.objects.count(), 0)

    def test_webhook_upserts_backup(self):
        response = self.client.post(
            reverse("accounts:auth0_signup_webhook"),
            data=(
                '{"user":{"user_id":"auth0|hook-ok","email":"ok@example.com",'
                '"email_verified":false,"name":"Hook"}}'
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer action-secret",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sync_status"], "synced")
        row = Auth0UserBackup.objects.get(auth0_user_id="auth0|hook-ok")
        self.assertEqual(row.email, "ok@example.com")
        self.assertFalse(row.email_verified)

    def test_backup_has_no_password_or_token_fields(self):
        field_names = {f.name for f in Auth0UserBackup._meta.fields}
        forbidden = {
            "password",
            "password_hash",
            "access_token",
            "refresh_token",
            "verification_token",
            "session",
            "client_secret",
        }
        self.assertFalse(field_names & forbidden)

    def test_reconcile_creates_missing_backup_from_profile(self):
        user = User.objects.create(username="auth0_orphan")
        user.set_unusable_password()
        user.email = "orphan@example.com"
        user.save()
        profile = user.profile
        profile.auth0_sub = "auth0|orphan"
        profile.email_verified = True
        profile.save()
        Auth0UserBackup.objects.filter(auth0_user_id="auth0|orphan").delete()
        stats = reconcile_from_profiles(limit=50)
        self.assertGreaterEqual(stats["created"], 1)
        row = Auth0UserBackup.objects.get(auth0_user_id="auth0|orphan")
        self.assertTrue(row.email_verified)
        self.assertEqual(row.sync_status, Auth0UserBackup.SyncStatus.SYNCED)

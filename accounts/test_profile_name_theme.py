"""Display-name editing and theme persistence."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .identity import sync_profile_from_claims

JSON = {"HTTP_ACCEPT": "application/json"}


class DisplayNameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="name-user", email="name@example.com", password="pw-123456!", first_name="Old", last_name="Name"
        )
        self.user.profile.onboarding_completed = True
        self.user.profile.save()
        self.client.force_login(self.user)

    def test_settings_prepopulates_current_name(self):
        response = self.client.get(reverse("accounts:settings"))
        self.assertContains(response, 'value="Old Name"')
        self.assertContains(response, "data-name-form")

    def test_json_update_persists_and_returns_new_name(self):
        response = self.client.post(reverse("accounts:update_name"), {"name": "  Ada   Lovelace  "}, **JSON)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "name": "Ada Lovelace", "initials": "AL"})
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Ada", "Lovelace"))
        # Nothing else about the account changes.
        self.assertEqual(self.user.email, "name@example.com")
        self.assertEqual(self.user.username, "name-user")
        self.assertTrue(self.user.check_password("pw-123456!"))
        self.assertIsNotNone(self.user.profile.name_customized_at)

    def test_new_name_appears_across_the_app(self):
        self.client.post(reverse("accounts:update_name"), {"name": "Grace Hopper"})
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, "Grace Hopper", count=None)
        self.assertContains(dashboard, ">GH<")
        self.assertContains(self.client.get(reverse("savings:pools")), "Grace Hopper")

    def test_form_post_without_javascript_redirects_with_message(self):
        response = self.client.post(reverse("accounts:update_name"), {"name": "Single"}, follow=True)
        self.assertContains(response, "Your name was updated.")
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Single", ""))

    def test_empty_or_whitespace_name_is_rejected(self):
        for bad in ["", "    ", "\t"]:
            response = self.client.post(reverse("accounts:update_name"), {"name": bad}, **JSON)
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json()["ok"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Old")

    def test_control_characters_and_overlong_names_are_rejected(self):
        self.assertEqual(self.client.post(reverse("accounts:update_name"), {"name": "Bad\x07Name"}, **JSON).status_code, 400)
        self.assertEqual(self.client.post(reverse("accounts:update_name"), {"name": "x" * 151}, **JSON).status_code, 400)

    def test_requires_login_and_post(self):
        self.assertEqual(self.client.get(reverse("accounts:update_name")).status_code, 405)
        self.client.logout()
        response = self.client.post(reverse("accounts:update_name"), {"name": "Hacker"})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Old")

    def test_custom_name_survives_signing_in_again(self):
        claims = {"sub": "auth0|name-test", "email": "a0@example.com", "email_verified": True, "name": "Provider Name"}
        profile, _ = sync_profile_from_claims(claims)
        user = profile.user
        self.assertEqual(user.first_name, "Provider")
        self.client.force_login(user)
        self.client.post(reverse("accounts:update_name"), {"name": "Chosen Name"})
        profile, _ = sync_profile_from_claims(claims)  # signs in again
        profile.user.refresh_from_db()
        self.assertEqual((profile.user.first_name, profile.user.last_name), ("Chosen", "Name"))


class ThemeToggleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="toggle-user", password="x")
        self.client.force_login(self.user)

    def test_toggle_endpoint_persists_preference(self):
        response = self.client.post(reverse("accounts:update_theme"), {"theme": "dark"}, **JSON)
        self.assertEqual(response.json(), {"ok": True, "theme": "dark"})
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.theme, "dark")
        page = self.client.get(reverse("accounts:settings"))
        self.assertContains(page, 'data-theme="dark" data-theme-pref="dark"')

    def test_invalid_theme_is_rejected(self):
        response = self.client.post(reverse("accounts:update_theme"), {"theme": "neon"}, **JSON)
        self.assertEqual(response.status_code, 400)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.theme, "system")

    def test_every_page_has_toggle_and_preload_script(self):
        page = self.client.get(reverse("savings:pools"))
        # Desktop topbar, mobile header, and the (CSS-hidden) signed-out header.
        self.assertContains(page, "data-theme-toggle", count=3)
        self.assertContains(page, "prefers-color-scheme: dark")
        self.assertContains(page, 'data-theme-endpoint="/accounts/settings/theme/"')

    def test_guests_follow_system_preference_by_default(self):
        self.client.logout()
        page = self.client.get(reverse("accounts:login"))
        self.assertContains(page, 'data-theme="system"')
        self.assertContains(page, "data-theme-toggle")
        self.assertNotContains(page, "data-theme-endpoint")

    def test_anonymous_cannot_change_a_theme(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("accounts:update_theme"), {"theme": "dark"}).status_code, 302)

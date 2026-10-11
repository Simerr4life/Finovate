from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.auth0_logout, name="logout"),
    path("verify/", views.verification_pending, name="verify"),
    path("verify/resend/", views.verification_resend, name="verify_resend"),
    path("verify/refresh/", views.verification_refresh, name="verify_refresh"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/preferences/", views.onboarding_preferences, name="onboarding_preferences"),
    path("manual-setup/", views.manual_setup, name="manual_setup"),
    path("manual-setup/summary/", views.manual_setup_summary, name="manual_setup_summary"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/messaging/link/", views.messaging_link_issue, name="messaging_link"),
    path("settings/messaging/unlink/", views.messaging_unlink, name="messaging_unlink"),
    path("auth0/login/", views.auth0_login, name="auth0_login"),
    path("auth0/callback/", views.auth0_callback, name="auth0_callback"),
]

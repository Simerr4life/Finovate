from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", views.auth0_logout, name="logout"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("onboarding/preferences/", views.onboarding_preferences, name="onboarding_preferences"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/messaging/link/", views.messaging_link_issue, name="messaging_link"),
    path("settings/messaging/unlink/", views.messaging_unlink, name="messaging_unlink"),
    path("auth0/login/", views.auth0_login, name="auth0_login"),
    path("auth0/callback/", views.auth0_callback, name="auth0_callback"),
]

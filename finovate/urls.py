from django.contrib import admin
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from accounts import views as account_views
from accounts.api import api_me
from core import views as core_views

urlpatterns = [
    # Browsers and iOS request these root paths directly for the tab and
    # home-screen icons, even when the page declares <link rel="icon">.
    path("favicon.ico", RedirectView.as_view(url=static("brand/favicon.ico"), permanent=True)),
    path("apple-touch-icon.png", RedirectView.as_view(url=static("brand/apple-touch-icon.png"), permanent=True)),
    path("apple-touch-icon-precomposed.png", RedirectView.as_view(url=static("brand/apple-touch-icon.png"), permanent=True)),
    path("admin/", admin.site.urls),
    path("api/me/", api_me, name="api_me"),
    path("callback/", account_views.auth0_callback, name="auth0_callback"),
    path("", core_views.landing, name="landing"),
    path("dashboard/", core_views.dashboard, name="dashboard"),
    path("insights/", core_views.insights, name="insights"),
    path("accounts/", include("accounts.urls")),
    path("statements/", include("transactions.urls")),
    path("imports/", include("imports.urls")),
    path("budgets/", include("budgets.urls")),
    path("savings/", include("savings.urls")),
    path("investing/", include("investing.urls")),
    path("assistant/", include("assistant.urls")),
]

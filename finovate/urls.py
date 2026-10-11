from django.contrib import admin
from django.urls import include, path

from accounts import views as account_views
from accounts.api import api_me
from core import views as core_views

urlpatterns = [
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

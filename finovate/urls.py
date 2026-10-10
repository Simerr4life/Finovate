from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", core_views.landing, name="landing"),
    path("dashboard/", core_views.dashboard, name="dashboard"),
    path("insights/", core_views.insights, name="insights"),
    path("accounts/", include("accounts.urls")),
    path("statements/", include("transactions.urls")),
    path("budgets/", include("budgets.urls")),
    path("savings/", include("savings.urls")),
    path("investing/", include("investing.urls")),
]

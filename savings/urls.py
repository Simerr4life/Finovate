from django.urls import path

from . import views

app_name = "savings"

urlpatterns = [
    path("", views.index, name="index"),
    path("plan/", views.plan_detail, name="plan"),
    path("plan/refresh/", views.plan_refresh, name="plan_refresh"),
    path("plan/status/", views.plan_status, name="plan_status"),
    path("plan/allocations/", views.plan_allocations, name="plan_allocations"),
    path("debts/", views.debt_list, name="debts"),
    path("debts/add/", views.debt_add, name="debt_add"),
    path("debts/<int:pk>/edit/", views.debt_edit, name="debt_edit"),
    path("pools/", views.pools, name="pools"),
    path("goals/", views.goals, name="goals"),
    path("add/", views.goal_add, name="goal_add"),
    path("<int:pk>/", views.goal_detail, name="goal_detail"),
    path("<int:pk>/edit/", views.goal_edit, name="goal_edit"),
    path("<int:pk>/delete/", views.goal_delete, name="goal_delete"),
]

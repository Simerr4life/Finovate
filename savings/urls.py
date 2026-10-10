from django.urls import path

from . import views

app_name = "savings"

urlpatterns = [
    path("", views.index, name="index"),
    path("pools/", views.pools, name="pools"),
    path("goals/", views.goals, name="goals"),
    path("add/", views.goal_add, name="goal_add"),
    path("<int:pk>/", views.goal_detail, name="goal_detail"),
    path("<int:pk>/edit/", views.goal_edit, name="goal_edit"),
    path("<int:pk>/delete/", views.goal_delete, name="goal_delete"),
]

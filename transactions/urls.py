from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    path("", views.statement_list, name="statement_list"),
    path("<int:pk>/", views.statement_detail, name="statement_detail"),
]

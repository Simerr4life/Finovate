from django.urls import path

from . import views

app_name = "budgets"

urlpatterns = [
    path("", views.index, name="index"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/add/", views.transaction_add, name="transaction_add"),
    path("transactions/<int:pk>/edit/", views.transaction_edit, name="transaction_edit"),
    path("transactions/<int:pk>/delete/", views.transaction_delete, name="transaction_delete"),
    path("categories/add/", views.category_add, name="category_add"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("periods/add/", views.period_add, name="period_add"),
    path("limits/add/", views.budget_add, name="budget_add"),
    path("limits/<int:pk>/delete/", views.budget_delete, name="budget_delete"),
    path("income/add/", views.income_add, name="income_add"),
    path("income/<int:pk>/delete/", views.income_delete, name="income_delete"),
    path("expenses/add/", views.expense_add, name="expense_add"),
    path("expenses/<int:pk>/delete/", views.expense_delete, name="expense_delete"),
]

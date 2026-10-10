from django.urls import path

from . import views

app_name = "investing"

urlpatterns = [
    path("", views.index, name="index"),
    path("sweep/", views.sweep_now, name="sweep_now"),
    path("surplus/propose/", views.propose_surplus, name="propose_surplus"),
    path("orders/<int:pk>/approve/", views.approve_order_view, name="approve_order"),
    path("orders/<int:pk>/reject/", views.reject_order_view, name="reject_order"),
    path("historical-demo/", views.historical_demo, name="historical_demo"),
    path("market-data/", views.market_data, name="market_data"),
]

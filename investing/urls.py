from django.urls import path

from . import views

app_name = "investing"

urlpatterns = [
    path("", views.index, name="index"),
    path("demo-ai/generate/", views.generate_demo_suggestions_view, name="generate_demo_suggestions"),
    path("demo-ai/<int:pk>/accept/", views.accept_demo_suggestion_view, name="accept_demo_suggestion"),
    path("demo-ai/<int:pk>/decline/", views.decline_demo_suggestion_view, name="decline_demo_suggestion"),
    path("sweep/", views.sweep_now, name="sweep_now"),
    path("surplus/propose/", views.propose_surplus, name="propose_surplus"),
    path("orders/<int:pk>/approve/", views.approve_order_view, name="approve_order"),
    path("orders/<int:pk>/reject/", views.reject_order_view, name="reject_order"),
    path("historical-demo/", views.historical_demo, name="historical_demo"),
    path("market-data/", views.market_data, name="market_data"),
    path("market-data/invest/", views.buy_demo_market_asset, name="buy_demo_market_asset"),
]

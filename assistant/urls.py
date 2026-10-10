from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("photon-webhook/", views.photon_webhook, name="photon_webhook"),
]

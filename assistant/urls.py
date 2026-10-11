from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("photon-webhook/", views.photon_webhook, name="photon_webhook"),
    path("bridge/", views.spectrum_bridge, name="spectrum_bridge"),
]

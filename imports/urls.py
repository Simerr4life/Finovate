from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("", views.history, name="history"),
    path("upload/", views.upload, name="upload"),
    path("<int:pk>/account/", views.choose_account, name="choose_account"),
    path("<int:pk>/preview/", views.preview, name="preview"),
    path("<int:pk>/", views.batch_detail, name="batch_detail"),
    path("<int:pk>/retry/", views.retry, name="retry"),
    path("<int:pk>/delete/", views.delete_batch, name="delete"),
]

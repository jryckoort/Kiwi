from django.urls import path

from . import views

app_name = "imports_app"

urlpatterns = [
    path("", views.upload, name="upload"),
    path("<int:pk>/mapping/", views.map_columns, name="map_columns"),
    path("<int:pk>/preview/", views.preview, name="preview"),
]

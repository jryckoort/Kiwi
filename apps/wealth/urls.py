from django.urls import path

from . import views

app_name = "wealth"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("actifs/nouveau/", views.real_asset_create, name="real_asset_create"),
    path("dettes/nouvelle/", views.liability_create, name="liability_create"),
    path("titres/nouvelle-operation/", views.security_transaction_create, name="security_transaction_create"),
]

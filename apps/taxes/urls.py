from django.urls import path

from . import views

app_name = "taxes"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("plus-value/", views.plus_value_calculator, name="plus_value_calculator"),
    path("tob/", views.tob_calculator, name="tob_calculator"),
    path("precompte-mobilier/", views.precompte_calculator, name="precompte_calculator"),
]

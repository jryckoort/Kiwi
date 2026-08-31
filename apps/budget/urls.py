from django.urls import path

from . import views

app_name = "budget"

urlpatterns = [
    path("comptes/", views.account_list, name="account_list"),
    path("comptes/nouveau/", views.account_create, name="account_create"),
    path("comptes/<int:pk>/", views.account_detail, name="account_detail"),
    path("transactions/nouvelle/", views.transaction_create, name="transaction_create"),
    path("transactions/<int:pk>/modifier/", views.transaction_edit, name="transaction_edit"),
    path("transactions/<int:pk>/supprimer/", views.transaction_delete, name="transaction_delete"),
    path("categories/", views.category_list, name="category_list"),
]

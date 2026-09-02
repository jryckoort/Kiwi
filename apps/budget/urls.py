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
    path("recurrentes/", views.recurring_list, name="recurring_list"),
    path("recurrentes/nouvelle/", views.recurring_create, name="recurring_create"),
    path("recurrentes/<int:pk>/modifier/", views.recurring_edit, name="recurring_edit"),
    path("recurrentes/<int:pk>/supprimer/", views.recurring_delete, name="recurring_delete"),
    path("budgets/", views.budget_overview, name="budget_overview"),
    path("budgets/reprendre/", views.budget_copy_previous, name="budget_copy_previous"),
    path("budgets/ligne/<int:pk>/supprimer/", views.budget_line_delete, name="budget_line_delete"),
]

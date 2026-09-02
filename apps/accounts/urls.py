from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("household/create/", views.household_create, name="household_create"),
    path("household/settings/", views.household_settings, name="household_settings"),
    path(
        "household/<int:household_id>/switch/",
        views.household_switch,
        name="household_switch",
    ),
    path("invites/<str:token>/", views.invite_accept, name="invite_accept"),
    path("magic-login/", views.magic_link_request, name="magic_link_request"),
    path("magic-login/<str:token>/", views.magic_link_consume, name="magic_link_consume"),
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url="/accounts/password-change/done/",
        ),
        name="password_change",
    ),
    path(
        "password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html"
        ),
        name="password_change_done",
    ),
]

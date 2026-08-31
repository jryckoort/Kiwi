from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("budget/", include("apps.budget.urls")),
    path("patrimoine/", include("apps.wealth.urls")),
    path("fiscalite/", include("apps.taxes.urls")),
    path("imports/", include("apps.imports_app.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

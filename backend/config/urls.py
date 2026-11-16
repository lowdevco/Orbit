from django.contrib import admin
from django.urls import include, path

from apps.projects.views import shared

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("settings/", include("apps.accounts.urls")),
    path("projects/", include("apps.projects.urls")),
    path("notes/", include("apps.notes.urls")),
    path("github/", include("apps.insights.urls")),
    path("p/<str:token>/", shared, name="shared"),
    path("", include("apps.core.urls")),
]

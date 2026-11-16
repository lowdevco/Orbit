from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("search/", views.search, name="search"),
    path("search.json", views.search_json, name="search_json"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("calendar/add/", views.calendar_add, name="calendar_add"),
    path("preview/", views.markdown_preview, name="markdown_preview"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
]

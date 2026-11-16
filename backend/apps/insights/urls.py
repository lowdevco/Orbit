from django.urls import path

from . import views

app_name = "insights"

urlpatterns = [
    path("", views.profile, name="profile"),
    path("analytics/", views.analytics, name="analytics"),
    path("inbox/", views.inbox, name="inbox"),
    path("activity/", views.activity, name="activity"),
    path("refresh/", views.refresh, name="refresh"),
]

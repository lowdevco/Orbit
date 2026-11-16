from django.urls import path

from . import views

urlpatterns = [
    path("", views.settings_view, name="settings"),
    path("keys/", views.keys_view, name="keys"),
    path("keys/delete/", views.key_delete, name="key_delete"),
    path("export.json", views.export_json, name="export_json"),
    path("appearance/", views.appearance_view, name="appearance"),
    path("delete-account/", views.delete_account, name="delete_account"),
]

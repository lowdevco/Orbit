from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("new/", views.project_create, name="create"),
    path("import/", views.project_import, name="import"),
    path("timer/stop/", views.timer_stop, name="timer_stop"),
    path("<slug:slug>/", views.project_detail, name="detail"),
    path("<slug:slug>/edit/", views.project_edit, name="edit"),
    path("<slug:slug>/delete/", views.project_delete, name="delete"),
    path("<slug:slug>/updates/add/", views.update_add, name="update_add"),
    path("<slug:slug>/updates/<int:pk>/delete/", views.update_delete, name="update_delete"),
    path("<slug:slug>/sync/", views.github_sync, name="sync"),
    path("<slug:slug>/issue/", views.issue_create, name="issue_create"),
    path("<slug:slug>/tasks/add/", views.task_add, name="task_add"),
    path("<slug:slug>/tasks/<int:pk>/edit/", views.task_edit, name="task_edit"),
    path("<slug:slug>/tasks/<int:pk>/move/", views.task_move, name="task_move"),
    path("<slug:slug>/tasks/<int:pk>/toggle/", views.task_toggle, name="task_toggle"),
    path("<slug:slug>/tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("<slug:slug>/milestones/add/", views.milestone_add, name="milestone_add"),
    path("<slug:slug>/milestones/<int:pk>/edit/", views.milestone_edit, name="milestone_edit"),
    path("<slug:slug>/milestones/<int:pk>/delete/", views.milestone_delete, name="milestone_delete"),
    path("<slug:slug>/links/add/", views.link_add, name="link_add"),
    path("<slug:slug>/links/<int:pk>/delete/", views.link_delete, name="link_delete"),
    path("<slug:slug>/timer/start/", views.timer_start, name="timer_start"),
    path("<slug:slug>/time/<int:pk>/delete/", views.time_delete, name="time_delete"),
    path("<slug:slug>/share/", views.share_toggle, name="share"),
    path("<slug:slug>/export.md", views.export_markdown, name="export"),
]

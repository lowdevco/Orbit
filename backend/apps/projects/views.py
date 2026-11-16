from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db.models import Count, Max, Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.models import Profile
from apps.core.ratelimit import hit, ratelimit, too_many
from apps.insights import client
from apps.insights.client import GitHubError, NoGitHubToken

from .forms import ImportForm, IssueForm, LinkForm, MilestoneForm, ProjectForm, QuickTaskForm, TaskForm, UpdateForm
from .models import Milestone, Project, ProjectLink, ProjectUpdate, Task, TimeEntry

SYNC_EVERY = timedelta(minutes=15)


def _project(request, slug):
    # Every lookup is scoped to the signed-in owner: other users get a 404, never someone else's data.
    return get_object_or_404(Project, owner=request.user, slug=slug)


def _back(request, default):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return redirect(nxt)
    return redirect(default)


def sync_commits(project, force=False):
    """Pull new commits from the linked repo into the project timeline."""
    if not project.github_repo:
        return 0
    if not force and project.github_synced_at and timezone.now() - project.github_synced_at < SYNC_EVERY:
        return 0
    token = client.get_token(project.owner)
    commits = client.recent_commits(token, project.github_repo, since=project.github_synced_at)
    updates = []
    for c in commits:
        message = c["commit"]["message"].strip()
        title, _, body = message.partition("\n")
        updates.append(
            ProjectUpdate(
                project=project,
                title=title[:200],
                body=body.strip(),
                source="github",
                github_sha=c["sha"],
                url=c["html_url"],
                created_at=datetime.fromisoformat(c["commit"]["author"]["date"]),
            )
        )
    ProjectUpdate.objects.bulk_create(updates, ignore_conflicts=True)
    project.github_synced_at = timezone.now()
    Project.objects.filter(pk=project.pk).update(github_synced_at=project.github_synced_at)
    return len(updates)


def project_list(request):
    archived = request.GET.get("archived") == "1"
    status = request.GET.get("status", "")
    projects = request.user.projects.filter(archived=archived)
    if status:
        projects = projects.filter(status=status)
    projects = projects.annotate(
        task_total=Count("tasks"), task_done=Count("tasks", filter=Q(tasks__status="done"))
    ).prefetch_related("milestones__tasks")
    return render(
        request,
        "projects/list.html",
        {"projects": projects, "status": status, "archived": archived, "statuses": Project.STATUS_CHOICES},
    )


def project_create(request):
    form = ProjectForm(request.POST or None, accent=Profile.for_user(request.user).accent_hex)
    if form.is_valid():
        project = form.save(commit=False)
        project.owner = request.user
        project.save()
        messages.success(request, "Project created.")
        return redirect(project)
    return render(request, "projects/form.html", {"form": form})


def project_edit(request, slug):
    project = _project(request, slug)
    old_repo = project.github_repo
    form = ProjectForm(request.POST or None, instance=project, accent=Profile.for_user(request.user).accent_hex)
    if form.is_valid():
        project = form.save(commit=False)
        if project.github_repo != old_repo:
            project.github_synced_at = None
        project.save()
        messages.success(request, "Project saved.")
        return redirect(project)
    return render(request, "projects/form.html", {"form": form, "project": project})


@require_POST
def project_delete(request, slug):
    project = _project(request, slug)
    # GitHub-style: the exact project name must be typed (checked server-side, not just in the browser).
    if request.POST.get("confirm", "").strip() != project.name:
        messages.error(request, "Type the project name exactly to delete it.")
        return redirect(reverse("projects:edit", args=[project.slug]) + "#delete")
    name = project.name
    project.delete()
    messages.success(request, f"Deleted '{name}'.")
    return redirect("projects:list")


def project_detail(request, slug):
    project = _project(request, slug)
    tab = request.GET.get("tab", "overview")
    ctx = {"project": project, "tab": tab}

    if tab == "overview":
        if project.github_repo:
            try:
                sync_commits(project)
                ctx["repo_items"] = client.repo_activity(request.user, project.github_repo)
            except GitHubError as e:
                ctx["github_error"] = str(e)
        ctx.update(
            updates=project.updates.all()[:50],
            milestones=project.milestones.prefetch_related("tasks"),
            update_form=UpdateForm(),
            link_form=LinkForm(),
            issue_form=IssueForm(),
        )
    elif tab == "board":
        tasks = list(project.tasks.select_related("milestone"))
        ctx["columns"] = [(key, label, [t for t in tasks if t.status == key]) for key, label in Task.STATUS_CHOICES]
        ctx["task_form"] = QuickTaskForm(project=project)
    elif tab == "milestones":
        ctx["milestones"] = project.milestones.prefetch_related("tasks")
        ctx["milestone_form"] = MilestoneForm()
        ctx["unassigned"] = project.tasks.filter(milestone__isnull=True).exclude(status="done").count()
    elif tab == "time":
        entries = project.time_entries.all()
        ctx.update(entries=entries, total=sum(e.seconds for e in entries))

    ctx["task_total"] = project.tasks.count()
    ctx["task_done"] = project.tasks.filter(status="done").count()
    return render(request, "projects/detail.html", ctx)


# --- timeline updates ---

@require_POST
def update_add(request, slug):
    project = _project(request, slug)
    form = UpdateForm(request.POST)
    if form.is_valid():
        update = form.save(commit=False)
        update.project = project
        update.save()
        project.save(update_fields=["updated_at"])
    else:
        messages.error(request, "An update needs a title.")
    return redirect(project)


@require_POST
def update_delete(request, slug, pk):
    project = _project(request, slug)
    get_object_or_404(ProjectUpdate, pk=pk, project=project).delete()
    return redirect(project)


@require_POST
@ratelimit("gh-sync", 10)
def github_sync(request, slug):
    project = _project(request, slug)
    try:
        n = sync_commits(project, force=True)
        messages.success(request, f"Synced {n} commit(s) from GitHub.")
    except GitHubError as e:
        messages.error(request, str(e))
    return redirect(project)


@require_POST
@ratelimit("gh-issue", 5)
def issue_create(request, slug):
    project = _project(request, slug)
    form = IssueForm(request.POST)
    if project.github_repo and form.is_valid():
        try:
            issue = client.create_issue(request.user, project.github_repo, **form.cleaned_data)
            ProjectUpdate.objects.create(
                project=project, title=f"Opened issue #{issue['number']}: {issue['title']}"[:200],
                source="github", url=issue["html_url"],
            )
            # Drop the cached issue list so the new one shows right away.
            request.user.github_cache.filter(key=f"repo:{project.github_repo}").delete()
            messages.success(request, f"Issue #{issue['number']} created on GitHub.")
        except GitHubError as e:
            messages.error(request, str(e))
    return redirect(project)


# --- tasks / kanban ---

@require_POST
def task_add(request, slug):
    project = _project(request, slug)
    form = QuickTaskForm(request.POST, project=project)
    if form.is_valid():
        task = form.save(commit=False)
        task.project = project
        task.order = (project.tasks.filter(status="todo").aggregate(m=Max("order"))["m"] or 0) + 1
        task.save()
    else:
        messages.error(request, "Couldn't add that task. Check the title and fields.")
    return _back(request, f"{project.get_absolute_url()}?tab=board")


def task_edit(request, slug, pk):
    project = _project(request, slug)
    task = get_object_or_404(Task, pk=pk, project=project)
    old_status = task.status
    form = TaskForm(request.POST or None, instance=task, project=project)
    if form.is_valid():
        task = form.save(commit=False)
        new_status, task.status = task.status, old_status
        task.set_status(new_status)  # keeps completed_at in sync
        task.save()
        messages.success(request, "Task saved.")
        return _back(request, f"{project.get_absolute_url()}?tab=board")
    return render(request, "projects/task_form.html", {"form": form, "project": project, "task": task})


# --- milestones ---

@require_POST
def milestone_add(request, slug):
    project = _project(request, slug)
    form = MilestoneForm(request.POST)
    if form.is_valid():
        milestone = form.save(commit=False)
        milestone.project = project
        milestone.save()
        messages.success(request, f"Milestone '{milestone.title}' added.")
    else:
        messages.error(request, "A milestone needs a title.")
    return redirect(f"{project.get_absolute_url()}?tab=milestones")


def milestone_edit(request, slug, pk):
    project = _project(request, slug)
    milestone = get_object_or_404(Milestone, pk=pk, project=project)
    form = MilestoneForm(request.POST or None, instance=milestone)
    if form.is_valid():
        form.save()
        messages.success(request, "Milestone saved.")
        return redirect(f"{project.get_absolute_url()}?tab=milestones")
    return render(request, "projects/milestone_form.html", {"form": form, "project": project, "milestone": milestone})


@require_POST
def milestone_delete(request, slug, pk):
    project = _project(request, slug)
    get_object_or_404(Milestone, pk=pk, project=project).delete()  # tasks stay, just unassigned
    messages.success(request, "Milestone deleted. Its tasks were kept.")
    return redirect(f"{project.get_absolute_url()}?tab=milestones")


@require_POST
def task_move(request, slug, pk):
    task = get_object_or_404(Task, pk=pk, project__owner=request.user, project__slug=slug)
    status = request.POST.get("status")
    if status not in dict(Task.STATUS_CHOICES):
        return HttpResponseBadRequest("bad status")
    try:
        index = int(request.POST.get("index", 0))
    except ValueError:
        return HttpResponseBadRequest("bad index")
    task.set_status(status)
    column = list(task.project.tasks.filter(status=status).exclude(pk=task.pk))
    column.insert(max(0, min(index, len(column))), task)
    for i, t in enumerate(column):
        t.order = i
    task.save()
    Task.objects.bulk_update(column, ["order"])
    return JsonResponse({"ok": True, "progress": task.project.progress})


@require_POST
def task_toggle(request, slug, pk):
    task = get_object_or_404(Task, pk=pk, project__owner=request.user, project__slug=slug)
    task.set_status("todo" if task.status == "done" else "done")
    task.save()
    return _back(request, f"{task.project.get_absolute_url()}?tab=board")


@require_POST
def task_delete(request, slug, pk):
    task = get_object_or_404(Task, pk=pk, project__owner=request.user, project__slug=slug)
    task.delete()
    return _back(request, f"{task.project.get_absolute_url()}?tab=board")


# --- links ---

@require_POST
def link_add(request, slug):
    project = _project(request, slug)
    form = LinkForm(request.POST)
    if form.is_valid():
        link = form.save(commit=False)
        link.project = project
        link.save()
    else:
        messages.error(request, "Links need a title and a valid URL.")
    return redirect(project)


@require_POST
def link_delete(request, slug, pk):
    project = _project(request, slug)
    get_object_or_404(ProjectLink, pk=pk, project=project).delete()
    return redirect(project)


# --- time tracking ---

def _stop_running(user):
    TimeEntry.objects.filter(project__owner=user, ended_at__isnull=True).update(ended_at=timezone.now())


@require_POST
def timer_start(request, slug):
    project = _project(request, slug)
    _stop_running(request.user)  # one running timer per user
    TimeEntry.objects.create(project=project, note=request.POST.get("note", "")[:200])
    return _back(request, project.get_absolute_url())


@require_POST
def timer_stop(request):
    _stop_running(request.user)
    return _back(request, "dashboard")


@require_POST
def time_delete(request, slug, pk):
    project = _project(request, slug)
    get_object_or_404(TimeEntry, pk=pk, project=project).delete()
    return redirect(f"{project.get_absolute_url()}?tab=time")


# --- sharing & export ---

@require_POST
def share_toggle(request, slug):
    project = _project(request, slug)
    if project.share_token:
        project.share_token = None
        messages.success(request, "Public link disabled.")
    else:
        project.enable_sharing()
        messages.success(request, "Public link enabled. Anyone with the link can view this project.")
    project.save(update_fields=["share_token"])
    return redirect(project)


@login_not_required
@ratelimit("shared", 60)
def shared(request, token):
    project = get_object_or_404(Project, share_token=token)
    tasks = list(project.tasks.all())
    return render(
        request,
        "projects/shared.html",
        {
            "project": project,
            "columns": [(key, label, [t for t in tasks if t.status == key]) for key, label in Task.STATUS_CHOICES],
            "updates": project.updates.all()[:30],
            "milestones": project.milestones.prefetch_related("tasks"),
        },
    )


def export_markdown(request, slug):
    project = _project(request, slug)
    text = render_to_string("projects/export.md", {"project": project})
    resp = HttpResponse(text, content_type="text/markdown; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{project.slug}.md"'
    return resp


def time_total(user, since):
    """Seconds tracked by `user` since `since` (running timers count up to now)."""
    return sum(e.seconds for e in TimeEntry.objects.filter(project__owner=user, started_at__gte=since))


# --- import from GitHub ---

def _safe_url(url):
    return url if url and url.startswith(("https://", "http://")) and len(url) <= 200 else ""


def project_import(request):
    ctx = {"form": ImportForm(request.POST or None)}
    try:
        viewer = client.overview(request.user)
        linked = {r.lower() for r in request.user.projects.exclude(github_repo="").values_list("github_repo", flat=True)}
        ctx["repos"] = [r for r in viewer["repositories"]["nodes"] if r["nameWithOwner"].lower() not in linked]
    except NoGitHubToken:
        ctx["needs_github"] = True
    except GitHubError as e:
        ctx["github_error"] = str(e)

    if request.method == "POST":
        if hit(request, "gh-import", 10):
            return too_many(request)
        if ctx["form"].is_valid():
            return _import_repo(request, ctx["form"].cleaned_data["repo"])
    return render(request, "projects/import.html", ctx)


def _import_repo(request, repo):
    try:
        token = client.get_token(request.user)
        info = client.get(token, f"/repos/{repo}")  # also proves this user's token can see the repo
    except GitHubError as e:
        messages.error(request, str(e))
        return redirect("projects:import")

    full_name = info["full_name"]
    existing = request.user.projects.filter(github_repo__iexact=full_name).first()
    if existing:
        messages.info(request, "That repository is already linked to one of your projects.")
        return redirect(existing)

    project = Project.objects.create(
        owner=request.user,
        name=info["name"][:120],
        description=(info.get("description") or "")[:2000],
        github_repo=full_name,
        status="active",
        start_date=date.fromisoformat(info["created_at"][:10]) if info.get("created_at") else None,
        readme=client.readme(token, full_name),
        live_url=_safe_url(info.get("homepage")),  # model validators don't run on create(); never store javascript: links
    )
    if _safe_url(info.get("html_url")):
        ProjectLink.objects.create(project=project, title="Repository", url=info["html_url"])
    try:
        sync_commits(project, force=True)
    except GitHubError:
        pass  # project is created; commits can be synced later from the project page
    messages.success(request, f"Imported {full_name}.")
    return redirect(project)

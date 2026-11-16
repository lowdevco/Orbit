import calendar
import re
from urllib.parse import urlencode
from datetime import date, timedelta

from django.contrib.auth.decorators import login_not_required
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.insights import client, stats
from apps.insights.client import GitHubError
from apps.projects.models import Milestone, ProjectUpdate, Task
from apps.projects.views import time_total

from .forms import CalendarTaskForm
from .markdown import render as render_markdown
from .ratelimit import ratelimit

MAX_QUERY = 100


def _try_github(fetch):
    try:
        return fetch()
    except GitHubError:
        return None  # dashboard still works without GitHub; tiles show a "connect" prompt


def dashboard(request):
    user = request.user
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    today = timezone.localdate()
    projects = user.projects.filter(archived=False)
    open_tasks = Task.objects.filter(project__owner=user, project__archived=False).exclude(status="done")

    viewer = _try_github(lambda: client.overview(user))
    github = stats.compute(viewer) if viewer else None
    inbox = _try_github(lambda: client.inbox(user)) if viewer else None
    events = _try_github(lambda: client.events(user)) if viewer else None

    open_milestones = [
        m for m in Milestone.objects.filter(project__owner=user, project__archived=False)
        .select_related("project").prefetch_related("tasks")
        if not m.is_complete
    ]
    milestones = open_milestones[:5]

    activity = sorted(
        [
            {"kind": "update", "when": u.created_at, "obj": u}
            for u in ProjectUpdate.objects.filter(project__owner=user).select_related("project")[:12]
        ]
        + [
            {"kind": "task", "when": t.completed_at, "obj": t}
            for t in Task.objects.filter(project__owner=user, completed_at__isnull=False)
            .select_related("project")
            .order_by("-completed_at")[:8]
        ],
        key=lambda a: a["when"],
        reverse=True,
    )[:12]

    ctx = {
        "stats": {
            "active_projects": projects.filter(status="active").count(),
            "open_tasks": open_tasks.count(),
            "notes": user.notes.count(),
            "milestones": len(open_milestones),
        },
        "github": github,
        "inbox": inbox,
        "gh_activity": stats.activity(events)[:6] if events else None,
        "milestones": milestones,
        "week": {
            "tasks_done": Task.objects.filter(project__owner=user, completed_at__gte=week_ago).count(),
            "updates": ProjectUpdate.objects.filter(project__owner=user, created_at__gte=week_ago).count(),
            "time": time_total(user, week_ago),
            "contributions": github["this_week"] if github else None,
        },
        "activity": activity,
        "upcoming": open_tasks.filter(due_date__isnull=False, due_date__lte=today + timedelta(days=14))
        .select_related("project")
        .order_by("due_date")[:8],
        "recent_projects": projects.exclude(status="done").prefetch_related("milestones__tasks", "tasks")[:6],
        "pinned_notes": user.notes.filter(pinned=True)[:4],
    }
    return render(request, "core/dashboard.html", ctx)


def _search(user, q, limit=8):
    results = []
    for p in user.projects.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(readme__icontains=q))[:limit]:
        results.append({"type": "Project", "title": p.name, "subtitle": p.get_status_display(), "url": p.get_absolute_url()})
    for n in user.notes.filter(Q(title__icontains=q) | Q(body__icontains=q) | Q(tags__icontains=q))[:limit]:
        results.append({"type": "Note", "title": n.title, "subtitle": n.tags, "url": n.get_absolute_url()})
    for m in Milestone.objects.filter(project__owner=user, title__icontains=q).select_related("project")[:limit]:
        results.append({"type": "Milestone", "title": m.title, "subtitle": m.project.name,
                        "url": m.project.get_absolute_url() + "?tab=milestones"})
    for t in Task.objects.filter(project__owner=user, title__icontains=q).select_related("project")[:limit]:
        results.append({"type": "Task", "title": t.title, "subtitle": t.project.name,
                        "url": t.project.get_absolute_url() + "?tab=board"})
    for u in (ProjectUpdate.objects.filter(project__owner=user)
              .filter(Q(title__icontains=q) | Q(body__icontains=q)).select_related("project")[:limit]):
        results.append({"type": "Update", "title": u.title, "subtitle": u.project.name, "url": u.project.get_absolute_url()})
    return results


def search(request):
    q = request.GET.get("q", "").strip()[:MAX_QUERY]
    return render(request, "core/search.html", {"q": q, "results": _search(request.user, q, 25) if q else []})


@ratelimit("search", 90)
def search_json(request):
    q = request.GET.get("q", "").strip()[:MAX_QUERY]
    return JsonResponse({"results": _search(request.user, q, 5) if q else []})


def calendar_view(request):
    today = timezone.localdate()
    try:
        year, month = (int(x) for x in request.GET.get("month", "").split("-"))
        first = date(year, month, 1)
        if not 1900 <= year <= 2999:  # keeps prev/next month arithmetic in range
            raise ValueError
    except ValueError:
        first = today.replace(day=1)
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)
    start, end = weeks[0][0], weeks[-1][-1]

    items = {}
    for m in (Milestone.objects.filter(project__owner=request.user, due_date__range=(start, end))
              .select_related("project").prefetch_related("tasks")):
        items.setdefault(m.due_date, []).append({
            "kind": "milestone", "label": m.title, "project": m.project, "done": m.is_complete,
            "detail": f"{m.progress}% done", "url": m.project.get_absolute_url() + "?tab=milestones",
        })
    for p in request.user.projects.filter(target_date__range=(start, end)):
        items.setdefault(p.target_date, []).append({
            "kind": "target", "label": f"{p.name} target", "project": p, "done": p.status == "done",
            "detail": "Project target date", "url": p.get_absolute_url(),
        })
    for t in (Task.objects.filter(project__owner=request.user, due_date__range=(start, end))
              .select_related("project", "milestone")):
        items.setdefault(t.due_date, []).append({
            "kind": "task", "label": t.title, "project": t.project, "done": t.status == "done",
            "priority": t.priority, "detail": t.milestone.title if t.milestone else t.get_status_display(),
            "url": reverse("projects:task_edit", args=[t.project.slug, t.pk]) + "?" + urlencode({"next": request.get_full_path()}),
        })

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return render(
        request,
        "core/calendar.html",
        {
            "first": first,
            "today": today,
            "weeks": [[(d, items.get(d, [])) for d in week] for week in weeks],
            "prev": prev_month.strftime("%Y-%m"),
            "next": next_month.strftime("%Y-%m"),
            "add_form": CalendarTaskForm(user=request.user),
            "has_projects": request.user.projects.filter(archived=False).exists(),
        },
    )


@require_POST
def calendar_add(request):
    form = CalendarTaskForm(request.POST, user=request.user)
    if form.is_valid():
        task = form.save()
        messages.success(request, f"Added '{task.title}' to {task.project.name} for {task.due_date:%b %d}.")
        month = task.due_date.strftime("%Y-%m")
    else:
        messages.error(request, "Pick a project, a title and a date.")
        month = request.POST.get("due_date", "")[:7]
    return redirect(reverse("calendar") + (f"?month={month}" if re.fullmatch(r"\d{4}-\d{2}", month) else ""))


@require_POST
@ratelimit("preview", 60)
def markdown_preview(request):
    text = request.POST.get("text", "")
    if len(text) > 200_000:
        return HttpResponseBadRequest("too long")
    return HttpResponse(render_markdown(text))


# --- PWA ---

@login_not_required
def manifest(request):
    return JsonResponse(
        {
            "name": "Orbit",
            "short_name": "Orbit",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#010409",
            "theme_color": "#010409",
            "icons": [
                {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        },
        content_type="application/manifest+json",
    )


@login_not_required
def service_worker(request):
    resp = render(request, "core/sw.js", content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    return resp


@login_not_required
def offline(request):
    return render(request, "core/offline.html")



# --- legal ---

LEGAL = {
    "operator": "lowdevco",
    "email": "muhammadirfank2007@gmail.com",
    "country": "India",
    "effective": date(2026, 11, 16),
}


@login_not_required
def terms(request):
    return render(request, "legal/terms.html", LEGAL)


@login_not_required
def privacy(request):
    return render(request, "legal/privacy.html", LEGAL)

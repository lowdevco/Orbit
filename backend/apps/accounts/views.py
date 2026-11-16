from django.contrib import messages
from django.contrib.auth import logout
from django.core import serializers
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.ratelimit import hit, ratelimit, too_many
from apps.insights import client
from apps.insights.client import GitHubError
from apps.notes.models import Note
from apps.projects.models import Milestone, Project, ProjectLink, ProjectUpdate, Task, TimeEntry

from .forms import AppearanceForm, GitHubKeyForm, ProfileForm
from .models import Profile

TABS = [
    ("profile", "Profile"),
    ("appearance", "Appearance"),
    ("connections", "Connections"),
    ("keys", "Keys"),
    ("data", "Your data"),
    ("account", "Account"),
]


def _settings_page(request, tab, **extra):
    user = request.user
    accounts = []
    profile = Profile.for_user(user)
    for a in user.socialaccount_set.all():
        accounts.append({
            "provider": a.provider,
            "label": a.get_provider_account().to_str(),  # GitHub username / Google email
            "avatar": a.get_avatar_url(),
        })
    _, source = client.token_source(user)
    ctx = {
        "tabs": TABS,
        "tab": tab,
        "accounts": accounts,
        "connected": {a["provider"] for a in accounts},
        "profile_form": ProfileForm(initial={
            "display_name": profile.display_name, "first_name": user.first_name, "last_name": user.last_name,
        }),
        "profile": profile,
        "accents": Profile.ACCENTS,
        "themes": Profile.THEME_CHOICES,
        "key_form": GitHubKeyForm(),
        "has_key": bool(profile.github_key_encrypted),
        "source": source,
        "counts": {
            "projects": user.projects.count(),
            "notes": user.notes.count(),
            "tasks": Task.objects.filter(project__owner=user).count(),
        },
    }
    ctx.update(extra)
    return render(request, "accounts/settings.html", ctx)


def settings_view(request):
    tab = request.GET.get("tab", "profile")
    if tab not in dict(TABS):
        tab = "profile"
    if request.method == "POST":
        form = ProfileForm(request.POST)
        if form.is_valid():
            request.user.first_name = form.cleaned_data["first_name"]
            request.user.last_name = form.cleaned_data["last_name"]
            request.user.save(update_fields=["first_name", "last_name"])
            profile = Profile.for_user(request.user)
            profile.display_name = form.cleaned_data["display_name"].strip()
            profile.save(update_fields=["display_name"])
            messages.success(request, "Profile saved.")
            return redirect("settings")
        return _settings_page(request, "profile", profile_form=form)
    return _settings_page(request, tab)


@require_POST
def appearance_view(request):
    form = AppearanceForm(request.POST)
    if form.is_valid():
        profile = Profile.for_user(request.user)
        profile.theme = form.cleaned_data["theme"]
        profile.accent = form.cleaned_data["accent"]
        profile.save(update_fields=["theme", "accent"])
        messages.success(request, "Appearance updated.")
    return redirect(reverse("settings") + "?tab=appearance")


def keys_view(request):
    if request.method != "POST":
        return redirect(reverse("settings") + "?tab=keys")
    if hit(request, "key-verify", 5, period=600):  # each attempt calls GitHub; stops token guessing via us
        return too_many(request, 600)
    form = GitHubKeyForm(request.POST)
    if form.is_valid():
        key = form.cleaned_data["key"].strip()
        try:
            login, scopes = client.check_token(key)
        except GitHubError as e:
            form.add_error("key", str(e))
        else:
            profile = Profile.for_user(request.user)
            profile.github_key = key
            profile.save()
            request.user.github_cache.all().delete()
            messages.success(request, f"Key saved. Connected to GitHub as @{login} ({scopes}).")
            return redirect(reverse("settings") + "?tab=keys")
    return _settings_page(request, "keys", key_form=form)


@require_POST
def key_delete(request):
    profile = Profile.for_user(request.user)
    profile.github_key = ""
    profile.save()
    request.user.github_cache.all().delete()
    messages.success(request, "GitHub key removed.")
    return redirect(reverse("settings") + "?tab=keys")


@ratelimit("export", 10)
def export_json(request):
    user = request.user
    projects = Project.objects.filter(owner=user)
    objects = [
        *projects,
        *Milestone.objects.filter(project__in=projects),
        *ProjectUpdate.objects.filter(project__in=projects),
        *Task.objects.filter(project__in=projects),
        *ProjectLink.objects.filter(project__in=projects),
        *TimeEntry.objects.filter(project__in=projects),
        *Note.objects.filter(owner=user),
    ]
    data = serializers.serialize("json", objects, indent=2)
    resp = HttpResponse(data, content_type="application/json")
    resp["Content-Disposition"] = 'attachment; filename="orbit-export.json"'
    return resp


@require_POST
def delete_account(request):
    # GitHub-style: type your email exactly (checked server-side).
    expected = (request.user.email or request.user.username).lower()
    if request.POST.get("confirm", "").strip().lower() != expected:
        messages.error(request, "Type your email exactly to delete your account.")
        return redirect(reverse("settings") + "?tab=account")
    user = request.user
    logout(request)
    user.delete()  # cascades to projects, notes, keys, social tokens, cached GitHub data
    return redirect("account_login")

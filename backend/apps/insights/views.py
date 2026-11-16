from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.ratelimit import ratelimit

from . import client, stats
from .client import GitHubError, NoGitHubToken

SORTS = {
    "updated": lambda r: r["updatedAt"],
    "stars": lambda r: r["stargazerCount"],
    "name": lambda r: r["name"].lower(),
}
REFRESH_TARGETS = ("insights:profile", "insights:analytics", "insights:inbox", "insights:activity", "dashboard")


def _github(fetch):
    """Run a GitHub fetch; return (data, error_context). error_context is set when GitHub isn't usable."""
    try:
        return fetch(), None
    except NoGitHubToken:
        return None, {"needs_github": True}
    except GitHubError as e:
        return None, {"github_error": str(e)}


def profile(request):
    viewer, err = _github(lambda: client.overview(request.user))
    if err:
        return render(request, "insights/profile.html", err)
    sort = request.GET.get("sort", "updated")
    lang = request.GET.get("lang", "")
    all_repos = viewer["repositories"]["nodes"]
    repos = [r for r in all_repos if not lang or (r["primaryLanguage"] and r["primaryLanguage"]["name"] == lang)]
    repos = sorted(repos, key=SORTS.get(sort, SORTS["updated"]), reverse=sort != "name")
    for r in repos:
        r["lang_color"] = stats.safe_color(r["primaryLanguage"] and r["primaryLanguage"]["color"])
    s = stats.compute(viewer)
    return render(
        request,
        "insights/profile.html",
        {
            "viewer": viewer,
            "repos": repos,
            "sort": sort,
            "lang": lang,
            "languages": sorted({r["primaryLanguage"]["name"] for r in all_repos if r["primaryLanguage"]}),
            "s": s,
        },
    )


def analytics(request):
    viewer, err = _github(lambda: client.overview(request.user))
    if err:
        return render(request, "insights/analytics.html", err)
    s = stats.compute(viewer)
    chart_data = {
        "weekly": {"labels": [w["week"] for w in s["weekly"]], "values": [w["count"] for w in s["weekly"]]},
        "languages": {
            "labels": [l["name"] for l in s["languages"]],
            "values": [l["percent"] for l in s["languages"]],
            "colors": [l["color"] for l in s["languages"]],
        },
        "committed": {"labels": [r["name"] for r in s["top_committed"]], "values": [r["count"] for r in s["top_committed"]]},
    }
    return render(request, "insights/analytics.html", {"viewer": viewer, "s": s, "chart_data": chart_data})


def inbox(request):
    data, err = _github(lambda: client.inbox(request.user))
    if err:
        return render(request, "insights/inbox.html", err)
    tab = request.GET.get("tab", "review")
    sections = {
        "review": ("Review requests", "Pull requests waiting for your review", data["review_requests"]),
        "assigned": ("Assigned issues", "Open issues assigned to you", data["assigned"]),
        "mine": ("Your pull requests", "Open pull requests you authored", data["my_prs"]),
    }
    tab = tab if tab in sections else "review"
    return render(
        request,
        "insights/inbox.html",
        {"inbox": data, "tab": tab, "sections": sections, "current": sections[tab]},
    )


def activity(request):
    events, err = _github(lambda: client.events(request.user))
    if err:
        return render(request, "insights/activity.html", err)
    kind = request.GET.get("kind", "")
    kind = kind if kind in ("push", "star", "release") else ""
    return render(request, "insights/activity.html", {"items": stats.activity(events, kind), "kind": kind})


@require_POST
@ratelimit("gh-refresh", 6)
def refresh(request):
    request.user.github_cache.all().delete()
    messages.success(request, "GitHub data refreshed.")
    target = request.POST.get("next")
    return redirect(target if target in REFRESH_TARGETS else "insights:profile")

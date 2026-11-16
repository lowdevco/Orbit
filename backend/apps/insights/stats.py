"""Turn the raw GitHub overview payload into numbers and chart series."""

import re
from collections import defaultdict
from datetime import date, datetime, timedelta

HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def safe_color(value, default="#7d8590"):
    """GitHub colours end up in style="" attributes; only allow plain hex."""
    return value if value and HEX.match(value) else default


def sparkline(values, width=100, height=28):
    """SVG polyline points for a list of numbers."""
    if not values:
        return ""
    top = max(values) or 1
    step = width / max(len(values) - 1, 1)
    return " ".join(f"{i * step:.1f},{height - (v / top) * (height - 2) - 1:.1f}" for i, v in enumerate(values))

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def streaks(days, today=None):
    """days: [(date, count)] sorted ascending. Returns (current, longest)."""
    today = today or date.today()
    longest = run = 0
    for _, count in days:
        run = run + 1 if count else 0
        longest = max(longest, run)
    counts = {d: c for d, c in days}
    current = 0
    d = today if counts.get(today) else today - timedelta(days=1)  # today not committed yet doesn't break it
    while counts.get(d):
        current += 1
        d -= timedelta(days=1)
    return current, longest


def compute(viewer, today=None):
    today = today or date.today()
    contrib = viewer["contributionsCollection"]
    weeks = contrib["contributionCalendar"]["weeks"]
    days = [
        (date.fromisoformat(d["date"]), d["contributionCount"])
        for w in weeks
        for d in w["contributionDays"]
    ]
    current, longest = streaks(days, today)

    heatmap = [
        [{"date": d["date"], "count": d["contributionCount"], "level": LEVELS.get(d["contributionLevel"], 0)}
         for d in w["contributionDays"]]
        for w in weeks
    ]
    if heatmap and weeks[0]["contributionDays"]:
        # First week can start mid-week; pad so rows line up with weekdays (0 = Sunday).
        heatmap[0] = [{}] * weeks[0]["contributionDays"][0]["weekday"] + heatmap[0]

    lang_size = defaultdict(int)
    lang_color = {}
    repos = viewer["repositories"]["nodes"]
    for r in repos:
        if r["isFork"]:
            continue
        for edge in r["languages"]["edges"]:
            lang_size[edge["node"]["name"]] += edge["size"]
            lang_color[edge["node"]["name"]] = safe_color(edge["node"]["color"])
    total = sum(lang_size.values()) or 1
    languages = [
        {"name": n, "color": lang_color[n], "percent": round(s * 100 / total, 1)}
        for n, s in sorted(lang_size.items(), key=lambda kv: -kv[1])[:8]
    ]

    week_start = today - timedelta(days=6)
    return {
        "total_contributions": contrib["contributionCalendar"]["totalContributions"],
        "total_commits": contrib["totalCommitContributions"],
        "this_week": sum(c for d, c in days if week_start <= d <= today),
        "current_streak": current,
        "longest_streak": longest,
        "heatmap": heatmap,
        "weekly": [{"week": w["contributionDays"][0]["date"], "count": sum(d["contributionCount"] for d in w["contributionDays"])} for w in weeks],
        "languages": languages,
        "last30": [c for _, c in days[-30:]],
        "sparkline": sparkline([c for _, c in days[-30:]]),
        "stars": sum(r["stargazerCount"] for r in repos),
        "top_starred": sorted(repos, key=lambda r: -r["stargazerCount"])[:5],
        "top_committed": [
            {"name": c["repository"]["nameWithOwner"], "url": c["repository"]["url"], "count": c["contributions"]["totalCount"]}
            for c in contrib["commitContributionsByRepository"]
        ],
    }


ACTIVITY_KINDS = {"PushEvent": "push", "WatchEvent": "star", "ReleaseEvent": "release"}


def activity(events, kind=""):
    """Turn raw GitHub events into feed items for pushes, stars and releases."""
    items = []
    for e in events:
        k = ACTIVITY_KINDS.get(e.get("type"))
        if not k or (kind and k != kind):
            continue
        repo = e["repo"]["name"]
        payload = e.get("payload") or {}
        item = {
            "kind": k,
            "repo": repo,
            "repo_url": f"https://github.com/{repo}",
            "when": datetime.fromisoformat(e["created_at"]),
            "url": f"https://github.com/{repo}",
        }
        if k == "push":
            branch = (payload.get("ref") or "").removeprefix("refs/heads/")
            commits = payload.get("commits") or []
            item.update(
                branch=branch,
                count=payload.get("size") or len(commits) or None,
                commits=[
                    {"sha": c.get("sha", "")[:7], "message": (c.get("message") or "").splitlines()[0][:120] if c.get("message") else ""}
                    for c in commits[:3]
                ],
                url=f"https://github.com/{repo}/commits/{branch}" if branch else item["url"],
            )
        elif k == "release":
            release = payload.get("release") or {}
            item.update(
                name=release.get("name") or release.get("tag_name") or "release",
                tag=release.get("tag_name", ""),
                url=release.get("html_url") or item["url"],
            )
        items.append(item)
    return items

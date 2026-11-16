"""Thin GitHub API client. Every call runs as the signed-in Orbit user, never as a shared server token."""

import base64
from datetime import timedelta

import requests
from allauth.socialaccount.models import SocialToken
from django.utils import timezone

API = "https://api.github.com"
CACHE_TTL = timedelta(minutes=15)


class GitHubError(Exception):
    pass


class NoGitHubToken(GitHubError):
    pass


def token_source(user):
    """Return (token, source). A key saved in Settings > Keys wins over the GitHub sign-in token."""
    from apps.accounts.models import Profile

    key = Profile.for_user(user).github_key
    if key:
        return key, "key"
    st = SocialToken.objects.filter(account__user=user, account__provider="github").first()
    if st:
        return st.token, "oauth"
    return None, None


def get_token(user):
    token, _ = token_source(user)
    if not token:
        raise NoGitHubToken("Connect GitHub or add a GitHub key in Settings to use this.")
    return token


def request(token, method, path, **kwargs):
    resp = requests.request(
        method,
        API + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Orbit",
        },
        timeout=8,
        **kwargs,
    )
    if resp.status_code == 401:
        raise GitHubError("GitHub rejected the token. Reconnect GitHub or update your key in Settings > Keys.")
    if resp.status_code == 404:
        raise GitHubError("Not found on GitHub (check the repo name, or that your token can see it).")
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("message", resp.text)
        except ValueError:
            msg = resp.text
        raise GitHubError(f"GitHub error {resp.status_code}: {msg}")
    return resp


def get(token, path, **params):
    return request(token, "GET", path, params=params).json()


def graphql(token, query, variables=None):
    data = request(token, "POST", "/graphql", json={"query": query, "variables": variables or {}}).json()
    if data.get("errors"):
        raise GitHubError("; ".join(e.get("message", "") for e in data["errors"]))
    return data["data"]


def cached(user, key, fetch):
    """Return cached JSON for (user, key), refetching when older than CACHE_TTL."""
    from .models import GitHubCache

    row = GitHubCache.objects.filter(user=user, key=key).first()
    if row and timezone.now() - row.fetched_at < CACHE_TTL:
        return row.data
    data = fetch()
    GitHubCache.objects.update_or_create(user=user, key=key, defaults={"data": data, "fetched_at": timezone.now()})
    return data


OVERVIEW_QUERY = """
query {
  viewer {
    login name avatarUrl bio company location websiteUrl url createdAt
    followers { totalCount }
    following { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        name nameWithOwner description url stargazerCount forkCount isPrivate isFork updatedAt
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
      }
    }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel weekday } }
      }
      commitContributionsByRepository(maxRepositories: 10) {
        repository { nameWithOwner url }
        contributions { totalCount }
      }
    }
  }
}
"""


def overview(user):
    """Profile, repos and a year of contributions in one GraphQL call (cached)."""
    token = get_token(user)
    return cached(user, "overview", lambda: graphql(token, OVERVIEW_QUERY)["viewer"])


def repo_activity(user, repo):
    """Open issues and PRs for a linked repo (cached)."""
    token = get_token(user)
    return cached(user, f"repo:{repo}", lambda: get(token, f"/repos/{repo}/issues", state="open", per_page=15))


def recent_commits(token, repo, since=None):
    params = {"per_page": 20}
    if since:
        params["since"] = since.isoformat()
    return get(token, f"/repos/{repo}/commits", **params)


def readme(token, repo):
    """Repo README as text, or "" if there is none (or it's huge)."""
    try:
        data = get(token, f"/repos/{repo}/readme")
    except GitHubError:
        return ""
    if data.get("encoding") != "base64" or data.get("size", 0) > 200_000:
        return ""
    return base64.b64decode(data["content"]).decode("utf-8", "replace")


def inbox(user):
    """Open PRs waiting for the user's review, issues assigned to them, and their own open PRs (cached)."""
    token = get_token(user)
    login = overview(user)["login"]

    def search(query):
        return get(token, "/search/issues", q=f"{query} is:open archived:false", sort="updated", per_page=30)["items"]

    return cached(user, "inbox", lambda: {
        "review_requests": search(f"is:pr review-requested:{login}"),
        "assigned": search(f"is:issue assignee:{login}"),
        "my_prs": search(f"is:pr author:{login}"),
    })


def events(user):
    """The user's recent public + private GitHub events (cached)."""
    token = get_token(user)
    login = overview(user)["login"]
    return cached(user, "events", lambda: get(token, f"/users/{login}/events", per_page=100))


def create_issue(user, repo, title, body):
    token = get_token(user)
    return request(token, "POST", f"/repos/{repo}/issues", json={"title": title, "body": body}).json()


def check_token(token):
    """Validate a token; returns (login, scopes string)."""
    resp = request(token, "GET", "/user")
    return resp.json().get("login", ""), resp.headers.get("X-OAuth-Scopes", "fine-grained token")

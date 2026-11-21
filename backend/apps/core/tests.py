from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.accounts.models import Profile
from apps.core.markdown import render
from apps.insights import stats
from apps.notes.models import Note
from apps.projects.models import Milestone, Project, Task, normalize_repo

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # rate-limit counters are keyed by user id, which repeats across tests
        self.alice = User.objects.create_user("alice", "alice@example.com")
        self.bob = User.objects.create_user("bob", "bob@example.com")
        self.client.force_login(self.alice)
        self.project = Project.objects.create(owner=self.alice, name="Rocket Ship")


class IsolationTests(Base):
    def test_other_users_cannot_see_or_change_project(self):
        self.client.force_login(self.bob)
        url = self.project.get_absolute_url()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(f"{url}delete/").status_code, 404)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_other_users_cannot_see_notes(self):
        note = Note.objects.create(owner=self.alice, title="secret")
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(note.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get("/search/?q=secret"), "secret</a>")

    def test_same_slug_allowed_for_different_users(self):
        other = Project.objects.create(owner=self.bob, name="Rocket Ship")
        self.assertEqual(other.slug, self.project.slug)
        self.assertEqual(Project.objects.create(owner=self.alice, name="Rocket Ship").slug, "rocket-ship-2")

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])


class PagesTests(Base):
    def test_main_pages_render(self):
        Task.objects.create(project=self.project, title="Launch", due_date=date.today())
        Milestone.objects.create(project=self.project, title="v1")
        base = self.project.get_absolute_url()
        settings_tabs = [f"/settings/?tab={t}" for t in ("profile", "connections", "keys", "data", "account")]
        for url in ["/", "/projects/", "/projects/new/", "/projects/import/", "/notes/", "/notes/new/", "/calendar/",
                    "/search/?q=rocket", *settings_tabs,
                    base, base + "?tab=board", base + "?tab=milestones", base + "?tab=docs", base + "?tab=time",
                    "/github/", "/github/analytics/", "/github/inbox/", "/github/activity/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_github_pages_prompt_to_connect_without_token(self):
        self.assertContains(self.client.get("/github/analytics/"), "Connect GitHub to unlock this")


class KanbanTests(Base):
    def test_move_reorders_and_completes(self):
        a = Task.objects.create(project=self.project, title="a", order=0)
        b = Task.objects.create(project=self.project, title="b", order=1)
        done = Task.objects.create(project=self.project, title="c", status="done", order=0)
        resp = self.client.post(f"{self.project.get_absolute_url()}tasks/{b.pk}/move/", {"status": "done", "index": 0})
        self.assertEqual(resp.json()["progress"], 67)
        b.refresh_from_db(); done.refresh_from_db(); a.refresh_from_db()
        self.assertEqual((b.status, b.order, done.order), ("done", 0, 1))
        self.assertIsNotNone(b.completed_at)

    def test_move_rejects_bad_status(self):
        t = Task.objects.create(project=self.project, title="a")
        resp = self.client.post(f"{self.project.get_absolute_url()}tasks/{t.pk}/move/", {"status": "nope"})
        self.assertEqual(resp.status_code, 400)


class SharingTests(Base):
    def test_public_link_only_when_enabled(self):
        self.client.post(f"{self.project.get_absolute_url()}share/")
        self.project.refresh_from_db()
        token = self.project.share_token
        self.client.logout()
        self.assertContains(self.client.get(f"/p/{token}/"), "Rocket Ship")
        self.client.force_login(self.alice)
        self.client.post(f"{self.project.get_absolute_url()}share/")
        self.client.logout()
        self.assertEqual(self.client.get(f"/p/{token}/").status_code, 404)


class TimerTests(Base):
    def test_only_one_running_timer(self):
        other = Project.objects.create(owner=self.alice, name="Other")
        self.client.post(f"{self.project.get_absolute_url()}timer/start/")
        self.client.post(f"{other.get_absolute_url()}timer/start/")
        running = [e.project.name for p in (self.project, other) for e in p.time_entries.filter(ended_at__isnull=True)]
        self.assertEqual(running, ["Other"])


class UnitTests(TestCase):
    def test_markdown_strips_scripts(self):
        html = render("**hi** <script>alert(1)</script> [x](javascript:alert(1))")
        self.assertIn("<strong>hi</strong>", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("javascript:", html)

    def test_normalize_repo(self):
        self.assertEqual(normalize_repo("https://github.com/django/django.git"), "django/django")
        self.assertEqual(normalize_repo("owner/repo"), "owner/repo")
        with self.assertRaises(Exception):
            normalize_repo("../../etc")

    def test_key_is_encrypted_at_rest(self):
        user = User.objects.create_user("carol")
        p = Profile.for_user(user)
        p.github_key = "ghp_secret"
        p.save()
        p.refresh_from_db()
        self.assertNotIn("ghp_secret", p.github_key_encrypted)
        self.assertEqual(p.github_key, "ghp_secret")

    def test_streaks(self):
        today = date(2026, 11, 16)
        days = [(today - timedelta(days=i), c) for i, c in reversed(list(enumerate([0, 2, 1, 0, 5, 5, 5, 0])))]
        # today has 0 -> streak counts from yesterday: 2 days; longest run is 3
        self.assertEqual(stats.streaks(days, today), (2, 3))

    def test_compute_pads_first_week(self):
        viewer = {
            "contributionsCollection": {
                "totalCommitContributions": 3,
                "contributionCalendar": {"totalContributions": 3, "weeks": [{"contributionDays": [
                    {"date": "2026-11-11", "contributionCount": 3, "contributionLevel": "FOURTH_QUARTILE", "weekday": 3},
                ]}]},
                "commitContributionsByRepository": [],
            },
            "repositories": {"nodes": []},
        }
        s = stats.compute(viewer, today=date(2026, 11, 16))
        self.assertEqual(len(s["heatmap"][0]), 4)
        self.assertEqual(s["this_week"], 3)


class GitHubSyncTests(Base):
    def test_sync_creates_updates_once(self):
        from apps.projects.views import sync_commits

        self.project.github_repo = "o/r"
        self.project.save()
        commits = [{"sha": "a" * 40, "html_url": "https://github.com/o/r/commit/a",
                    "commit": {"message": "Fix bug\n\ndetails", "author": {"date": "2026-11-15T10:00:00Z"}}}]
        with mock.patch("apps.insights.client.get_token", return_value="t"), \
             mock.patch("apps.insights.client.recent_commits", return_value=commits):
            sync_commits(self.project, force=True)
            sync_commits(self.project, force=True)
        updates = list(self.project.updates.all())
        self.assertEqual(len(updates), 1)
        self.assertEqual((updates[0].title, updates[0].body, updates[0].source), ("Fix bug", "details", "github"))


class MilestoneTests(Base):
    def test_progress_and_completion(self):
        m = Milestone.objects.create(project=self.project, title="MVP")
        Task.objects.create(project=self.project, milestone=m, title="a", status="done")
        Task.objects.create(project=self.project, milestone=m, title="b")
        self.assertEqual((m.progress, m.is_complete), (50, False))
        self.assertEqual(self.project.next_milestone, m)

    def test_add_edit_delete_keeps_tasks(self):
        base = self.project.get_absolute_url()
        self.client.post(f"{base}milestones/add/", {"title": "Beta"})
        m = self.project.milestones.get()
        t = Task.objects.create(project=self.project, milestone=m, title="x")
        self.client.post(f"{base}milestones/{m.pk}/edit/", {"title": "Beta 2"})
        m.refresh_from_db()
        self.assertEqual(m.title, "Beta 2")
        self.client.post(f"{base}milestones/{m.pk}/delete/")
        t.refresh_from_db()
        self.assertIsNone(t.milestone)

    def test_cannot_attach_task_to_another_users_milestone(self):
        theirs = Milestone.objects.create(project=Project.objects.create(owner=self.bob, name="B"), title="secret")
        t = Task.objects.create(project=self.project, title="x")
        resp = self.client.post(f"{self.project.get_absolute_url()}tasks/{t.pk}/edit/",
                                {"title": "x", "status": "todo", "priority": 0, "milestone": theirs.pk})
        self.assertEqual(resp.status_code, 200)  # form re-rendered with an error
        t.refresh_from_db()
        self.assertIsNone(t.milestone)

    def test_other_user_cannot_edit_milestone(self):
        m = Milestone.objects.create(project=self.project, title="mine")
        self.client.force_login(self.bob)
        self.assertEqual(self.client.post(f"{self.project.get_absolute_url()}milestones/{m.pk}/delete/").status_code, 404)

    def test_task_edit_sets_completed_at(self):
        t = Task.objects.create(project=self.project, title="x")
        self.client.post(f"{self.project.get_absolute_url()}tasks/{t.pk}/edit/",
                         {"title": "x", "status": "done", "priority": 3, "labels": "bug, ui"})
        t.refresh_from_db()
        self.assertEqual((t.status, t.priority, t.label_list), ("done", 3, ["bug", "ui"]))
        self.assertIsNotNone(t.completed_at)


class SecurityTests(Base):
    def test_project_colour_rejects_css_injection(self):
        resp = self.client.post("/projects/new/", {"name": "X", "status": "active", "color": "red;background:url(x)"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Project.objects.filter(name="X").exists())

    def test_csp_header_with_nonce(self):
        resp = self.client.get("/")
        csp = resp["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'nonce-", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        nonce = csp.split("'nonce-")[1].split("'")[0]
        self.assertContains(resp, f'nonce="{nonce}"')

    def test_post_rate_limit(self):
        from django.core.cache import cache

        cache.clear()
        with self.settings(RATELIMIT_POST_PER_MINUTE=3):
            codes = [self.client.post("/preview/", {"text": "x"}).status_code for _ in range(5)]
        cache.clear()
        self.assertEqual(codes[:3], [200, 200, 200])
        self.assertEqual(codes[3:], [429, 429])

    def test_back_redirect_rejects_other_hosts(self):
        t = Task.objects.create(project=self.project, title="x")
        resp = self.client.post(f"{self.project.get_absolute_url()}tasks/{t.pk}/toggle/", {"next": "https://evil.example/"})
        self.assertNotIn("evil", resp["Location"])

    def test_reserved_slug(self):
        self.assertEqual(Project.objects.create(owner=self.alice, name="Import").slug, "import-project")

    def test_delete_account_needs_typed_email(self):
        for wrong in ("", "alice", "bob@example.com"):
            self.client.post("/settings/delete-account/", {"confirm": wrong})
            self.assertTrue(User.objects.filter(pk=self.alice.pk).exists())
        self.client.post("/settings/delete-account/", {"confirm": "Alice@Example.com"})
        self.assertFalse(User.objects.filter(pk=self.alice.pk).exists())


class DeleteProjectTests(Base):
    def test_delete_needs_exact_project_name(self):
        base = self.project.get_absolute_url()
        for wrong in ("", "rocket ship", "Rocket"):
            self.client.post(f"{base}delete/", {"confirm": wrong})
            self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())
        self.client.post(f"{base}delete/", {"confirm": "Rocket Ship"})
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    def test_edit_page_shows_type_to_confirm(self):
        resp = self.client.get(f"{self.project.get_absolute_url()}edit/")
        self.assertContains(resp, 'data-match="Rocket Ship"')
        self.assertNotContains(resp, "6-digit")


class ProjectColourTests(Base):
    def test_default_colour_follows_accent(self):
        self.assertEqual(self.project.color, "")
        self.assertEqual(self.project.swatch, "var(--color-accent)")
        self.assertContains(self.client.get("/projects/"), "background: var(--color-accent)")

    def test_square_picker_saves_any_hex(self):
        url = f"{self.project.get_absolute_url()}edit/"
        self.client.post(url, {"name": "Rocket Ship", "status": "active", "color": "#12AB56"})
        self.project.refresh_from_db()
        self.assertEqual(self.project.swatch, "#12ab56")
        self.assertContains(self.client.get(url), 'type="color"')

    def test_new_project_picker_starts_on_user_accent(self):
        from apps.accounts.models import Profile

        p = Profile.for_user(self.alice)
        p.accent = "pink"
        p.save()
        self.assertContains(self.client.get("/projects/new/"), 'value="#d6409f"')

    def test_rejects_non_hex_colour(self):
        url = f"{self.project.get_absolute_url()}edit/"
        for bad in ("red;background:url(x)", "javascript:x"):
            resp = self.client.post(url, {"name": "Rocket Ship", "status": "active", "color": bad})
            self.assertEqual(resp.status_code, 200)  # form re-rendered with an error
        self.project.refresh_from_db()
        self.assertEqual(self.project.color, "")


class ErrorPageTests(Base):
    def test_custom_404(self):
        resp = self.client.get("/definitely-not-a-page/")
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, "Lost in orbit", status_code=404)

    def test_other_users_project_is_themed_404(self):
        self.client.force_login(self.bob)
        self.assertContains(self.client.get(self.project.get_absolute_url()), "Lost in orbit", status_code=404)


class ProfileAppearanceTests(Base):
    def test_display_name_and_appearance(self):
        from apps.accounts.models import Profile

        self.client.post("/settings/", {"display_name": "Irfan", "first_name": "", "last_name": ""})
        self.client.post("/settings/appearance/", {"theme": "light", "accent": "green"})
        p = Profile.for_user(self.alice)
        self.assertEqual((p.display_name, p.theme, p.accent), ("Irfan", "light", "green"))
        resp = self.client.get("/")
        self.assertContains(resp, 'data-theme="light" data-accent="green"')
        self.assertContains(resp, "Welcome back, Irfan")

    def test_appearance_rejects_unknown_values(self):
        from apps.accounts.models import Profile

        self.client.post("/settings/appearance/", {"theme": "neon", "accent": "red\" onload=\"x"})
        p = Profile.for_user(self.alice)
        self.assertEqual((p.theme, p.accent), ("dark", "blue"))


class CalendarAndFixesTests(Base):
    def test_calendar_shows_milestones_and_links_tasks(self):
        today = date.today()
        Milestone.objects.create(project=self.project, title="Launch day", due_date=today)
        t = Task.objects.create(project=self.project, title="Write docs", due_date=today)
        resp = self.client.get("/calendar/")
        self.assertContains(resp, "Launch day")
        self.assertContains(resp, f"/tasks/{t.pk}/edit/?next=")

    def test_calendar_quick_add_only_into_own_projects(self):
        theirs = Project.objects.create(owner=self.bob, name="Bob's")
        day = date.today().isoformat()
        self.client.post("/calendar/add/", {"project": theirs.pk, "title": "sneaky", "due_date": day, "priority": 0})
        self.assertFalse(Task.objects.filter(title="sneaky").exists())
        self.client.post("/calendar/add/", {"project": self.project.pk, "title": "planned", "due_date": day, "priority": 2})
        self.assertTrue(Task.objects.filter(project=self.project, title="planned", due_date=date.today()).exists())

    def test_calendar_handles_odd_month(self):
        self.assertEqual(self.client.get("/calendar/?month=9999-12").status_code, 200)

    def test_dashboard_counts_all_open_milestones(self):
        for i in range(7):
            Milestone.objects.create(project=self.project, title=f"m{i}")
        self.assertEqual(self.client.get("/").context["stats"]["milestones"], 7)

    def test_note_tag_filter_is_exact(self):
        Note.objects.create(owner=self.alice, title="A", tags="ui, design")
        Note.objects.create(owner=self.alice, title="B", tags="build")
        titles = [n.title for n in self.client.get("/notes/?tag=ui").context["notes"]]
        self.assertEqual(titles, ["A"])

    def test_live_url_must_be_http(self):
        resp = self.client.post("/projects/new/", {"name": "L", "status": "active", "color": "#2f81f7", "live_url": "javascript:alert(1)"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Project.objects.filter(name="L").exists())

    def test_no_browser_dialogs_or_emoji_in_templates(self):
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[3] / "frontend"
        emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐]")
        for f in [*root.glob("templates/**/*.html"), root / "static/js/orbit.js"]:
            text = f.read_text(encoding="utf-8")
            self.assertIsNone(emoji.search(text), f)
            self.assertNotRegex(text, r"(?<![\w.])(confirm|alert)\(", f)


class PublicPagesTests(TestCase):
    def test_legal_pages_are_public(self):
        for url in ("/terms/", "/privacy/"):
            resp = self.client.get(url)
            self.assertContains(resp, "lowdevco")
            self.assertContains(resp, "muhammadirfank2007@gmail.com")


class ImportAndActivityTests(Base):
    def test_import_creates_project_with_safe_links(self):
        info = {"full_name": "o/r", "name": "r", "description": "desc", "created_at": "2025-01-02T00:00:00Z",
                "html_url": "https://github.com/o/r", "homepage": "javascript:alert(1)"}
        with mock.patch("apps.insights.client.get_token", return_value="t"), \
             mock.patch("apps.insights.client.get", return_value=info), \
             mock.patch("apps.insights.client.readme", return_value="# Hi"), \
             mock.patch("apps.insights.client.recent_commits", return_value=[]), \
             mock.patch("apps.insights.client.overview", side_effect=__import__("apps.insights.client", fromlist=["x"]).NoGitHubToken()):
            resp = self.client.post("/projects/import/", {"repo": "https://github.com/o/r"})
        project = Project.objects.get(owner=self.alice, github_repo="o/r")
        self.assertRedirects(resp, project.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual((project.readme, project.description), ("# Hi", "desc"))
        self.assertEqual([l.url for l in project.links.all()], ["https://github.com/o/r"])

    def test_activity_parsing(self):
        events = [
            {"type": "PushEvent", "repo": {"name": "o/r"}, "created_at": "2026-11-15T10:00:00Z",
             "payload": {"ref": "refs/heads/main", "size": 2, "commits": [{"sha": "abcdef123", "message": "Fix\n\nmore"}]}},
            {"type": "WatchEvent", "repo": {"name": "x/y"}, "created_at": "2026-11-14T10:00:00Z", "payload": {}},
            {"type": "IssuesEvent", "repo": {"name": "x/y"}, "created_at": "2026-11-14T10:00:00Z", "payload": {}},
        ]
        items = stats.activity(events)
        self.assertEqual([i["kind"] for i in items], ["push", "star"])
        self.assertEqual((items[0]["branch"], items[0]["count"], items[0]["commits"][0]["message"]), ("main", 2, "Fix"))
        self.assertEqual([i["kind"] for i in stats.activity(events, "star")], ["star"])

    def test_safe_color(self):
        self.assertEqual(stats.safe_color("#f1e05a"), "#f1e05a")
        self.assertEqual(stats.safe_color("red;x"), "#7d8590")


class MarkdownTests(SimpleTestCase):
    def test_lists_without_blank_line_and_line_breaks(self):
        from apps.core.markdown import render

        html = render("Site\n- Domain: a.com\n- User: b\n\nOne\nTwo\n```\n- not a list\n```")
        self.assertIn("<li>Domain: a.com</li>", html)
        self.assertIn("One<br", html)
        self.assertIn("<pre><code>- not a list", html)


class TimelineTasksTests(Base):
    def test_task_shows_once_with_live_status(self):
        task = Task.objects.create(project=self.project, title="Ship payroll")
        url = self.project.get_absolute_url()
        self.assertContains(self.client.get(url), "Ship payroll", count=1)
        self.client.post(f"{url}tasks/{task.pk}/toggle/".replace("//", "/"))
        task.refresh_from_db()
        self.assertEqual(task.status, "done")
        resp = self.client.get(url)
        self.assertContains(resp, "Ship payroll", count=1)
        self.assertContains(resp, "tl-task-done")


class SelectComponentTests(SimpleTestCase):
    def test_partial_marks_selected_and_placeholder(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            "partials/select.html",
            {"name": "sort", "options": [(1, "One"), (2, "Two")], "value": "2", "placeholder": "Any", "label": "Sort", "autosubmit": True},
        )
        self.assertIn('data-orbit-select', html)
        self.assertIn('data-autosubmit', html)
        self.assertIn('<option value="">Any</option>', html)
        self.assertIn('<option value="2" selected>Two</option>', html)
        self.assertNotIn('<option value="1" selected', html)

    def test_styled_forms_use_component_for_single_selects(self):
        from django import forms

        from apps.core.forms import StyledFormMixin

        class F(StyledFormMixin, forms.Form):
            one = forms.ChoiceField(choices=[("a", "A")])
            many = forms.MultipleChoiceField(choices=[("a", "A")])

        f = F()
        self.assertIn("data-orbit-select", f.fields["one"].widget.attrs)
        self.assertNotIn("data-orbit-select", f.fields["many"].widget.attrs)

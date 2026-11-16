import re
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, URLValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
# Colours are written into style="" attributes, so only plain hex is allowed (blocks CSS injection).
hex_color = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a hex colour like #2f81f7.")


def normalize_repo(value):
    """Accept 'owner/name' or a github.com URL; return 'owner/name'."""
    value = (value or "").strip().removesuffix(".git").rstrip("/")
    value = re.sub(r"^(https?://)?(www\.)?github\.com/", "", value)
    if value and not REPO_RE.match(value):
        raise ValidationError("Use the form owner/repo, e.g. torvalds/linux.")
    return value


RESERVED_SLUGS = {"new", "import", "timer"}


class Project(models.Model):
    STATUS_CHOICES = [("idea", "Idea"), ("active", "Active"), ("paused", "Paused"), ("done", "Done")]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    description = models.TextField(blank=True)
    readme = models.TextField(blank=True, help_text="Markdown docs for this project.")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    color = models.CharField(
        max_length=7, blank=True, default="", validators=[hex_color],
        help_text="Leave on 'Theme accent' to follow your accent colour.",
    )
    live_url = models.URLField(
        max_length=300, blank=True, validators=[URLValidator(schemes=["http", "https"])],
        help_text="Where the project runs, e.g. https://myapp.com",
    )
    github_repo = models.CharField(max_length=140, blank=True, help_text="owner/repo — commits show up in the timeline.")
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    archived = models.BooleanField(default=False)
    share_token = models.CharField(max_length=32, null=True, blank=True, unique=True)
    github_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["owner", "slug"], name="unique_project_slug_per_owner")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:120] or "project"
            if base in RESERVED_SLUGS:  # would collide with /projects/new/, /import/, /timer/
                base += "-project"
            slug, n = base, 2
            while Project.objects.filter(owner=self.owner, slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("projects:detail", args=[self.slug])

    def enable_sharing(self):
        self.share_token = secrets.token_urlsafe(16)

    @property
    def progress(self):
        tasks = list(self.tasks.values_list("status", flat=True))
        return round(tasks.count("done") * 100 / len(tasks)) if tasks else 0

    @property
    def is_overdue(self):
        return bool(self.target_date and self.status != "done" and self.target_date < timezone.localdate())

    @property
    def swatch(self):
        """CSS colour for this project: its fixed colour, or the user's theme accent. Safe for style="" (hex-validated)."""
        return self.color or "var(--color-accent)"

    @property
    def next_milestone(self):
        return next((m for m in self.milestones.all() if not m.is_complete), None)


class ProjectUpdate(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="updates")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    source = models.CharField(max_length=10, choices=[("manual", "Manual"), ("github", "GitHub")], default="manual")
    github_sha = models.CharField(max_length=40, blank=True)
    url = models.URLField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "github_sha"], condition=~models.Q(github_sha=""), name="unique_commit_per_project"
            )
        ]


class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [models.F("due_date").asc(nulls_last=True), "created_at"]

    def __str__(self):
        return self.title

    @property
    def counts(self):
        statuses = [t.status for t in self.tasks.all()]
        return statuses.count("done"), len(statuses)

    @property
    def progress(self):
        done, total = self.counts
        return round(done * 100 / total) if total else 0

    @property
    def is_complete(self):
        done, total = self.counts
        return total > 0 and done == total

    @property
    def is_overdue(self):
        return bool(self.due_date and not self.is_complete and self.due_date < timezone.localdate())


class Task(models.Model):
    STATUS_CHOICES = [("todo", "To do"), ("doing", "Doing"), ("done", "Done")]
    PRIORITY_CHOICES = [(0, "None"), (1, "Low"), (2, "Medium"), (3, "High"), (4, "Urgent")]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    milestone = models.ForeignKey(Milestone, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=5, choices=STATUS_CHOICES, default="todo")
    priority = models.PositiveSmallIntegerField(choices=PRIORITY_CHOICES, default=0)
    labels = models.CharField(max_length=200, blank=True, help_text="Comma separated, e.g. bug, frontend")
    order = models.PositiveIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]

    def __str__(self):
        return self.title

    @property
    def label_list(self):
        return [label.strip() for label in self.labels.split(",") if label.strip()]

    def set_status(self, status):
        self.status = status
        if status == "done" and not self.completed_at:
            self.completed_at = timezone.now()
        elif status != "done":
            self.completed_at = None

    @property
    def is_overdue(self):
        return bool(self.due_date and self.status != "done" and self.due_date < timezone.localdate())


class ProjectLink(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="links")
    title = models.CharField(max_length=120)
    url = models.URLField()

    class Meta:
        ordering = ["title"]


class TimeEntry(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="time_entries")
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-started_at"]

    @property
    def seconds(self):
        return int(((self.ended_at or timezone.now()) - self.started_at).total_seconds())

import re

from django import forms

from apps.core.forms import StyledFormMixin

from .models import Milestone, Project, ProjectLink, ProjectUpdate, Task, normalize_repo

HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


class ProjectForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "status", "color", "live_url", "github_repo", "start_date", "target_date", "readme", "archived"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "readme": forms.Textarea(attrs={"rows": 12, "data-md-preview": ""}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "live_url": forms.URLInput(attrs={"placeholder": "https://"}),
        }

    color = forms.CharField(
        required=False, max_length=7, label="Colour",
        widget=forms.TextInput(attrs={"type": "color", "class": "input h-10 w-20 cursor-pointer p-1"}),
    )

    def __init__(self, *args, accent="#2f81f7", **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.color:
            # New projects (and older ones that followed the theme) start on the user's current accent.
            self.initial["color"] = accent

    def clean_color(self):
        value = (self.cleaned_data.get("color") or "").strip().lower()
        if value and not HEX_RE.match(value):  # value lands in style="", so hex only
            raise forms.ValidationError("Pick a colour.")
        return value

    def clean_github_repo(self):
        return normalize_repo(self.cleaned_data["github_repo"])


class UpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectUpdate
        fields = ["title", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "What changed? e.g. Shipped login page"}),
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Details (markdown, optional)"}),
        }


class ProjectScopedMixin:
    """Limits the milestone dropdown to this project's milestones, so tasks can't be attached elsewhere."""

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        if "milestone" in self.fields:
            self.fields["milestone"].queryset = project.milestones.all()
            self.fields["milestone"].empty_label = "No milestone"


class TaskForm(ProjectScopedMixin, StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "status", "priority", "milestone", "labels", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "data-md-preview": "", "placeholder": "Details, acceptance criteria… (markdown)"}),
            "labels": forms.TextInput(attrs={"placeholder": "bug, frontend"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class QuickTaskForm(ProjectScopedMixin, StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "priority", "milestone", "due_date"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Add a task…"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class MilestoneForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Milestone
        fields = ["title", "due_date", "description"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. v1.0 launch"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "What does done look like?"}),
        }


class LinkForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectLink
        fields = ["title", "url"]


class IssueForm(StyledFormMixin, forms.Form):
    title = forms.CharField(max_length=250, widget=forms.TextInput(attrs={"placeholder": "Issue title"}))
    body = forms.CharField(required=False, max_length=20000, widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Describe the issue (markdown)"}))


class ImportForm(forms.Form):
    repo = forms.CharField(max_length=140)

    def clean_repo(self):
        repo = normalize_repo(self.cleaned_data["repo"])
        if not repo:
            raise forms.ValidationError("Pick a repository.")
        return repo

from django import forms

from apps.projects.models import Task


class StyledFormMixin:
    """Adds the Orbit input classes to every widget so templates can just render {{ field }}."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "checkbox")
            elif isinstance(w, forms.Textarea):
                w.attrs.setdefault("class", "input font-mono text-sm")
                w.attrs.setdefault("rows", 8)
            else:
                w.attrs.setdefault("class", "input")


class CalendarTaskForm(StyledFormMixin, forms.ModelForm):
    """Quick-add a dated task from the calendar, into one of the user's own projects."""

    class Meta:
        model = Task
        fields = ["project", "title", "due_date", "priority"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Task title"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = user.projects.filter(archived=False)
        self.fields["due_date"].required = True

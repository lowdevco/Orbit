from django import forms

from apps.core.forms import StyledFormMixin

from .models import Note


class NoteForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Note
        fields = ["title", "project", "tags", "pinned", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 18, "data-md-preview": ""})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        # Only the user's own projects can be attached.
        self.fields["project"].queryset = user.projects.filter(archived=False)

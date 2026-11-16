from django import forms

from apps.core.forms import StyledFormMixin

from .models import Profile


class ProfileForm(StyledFormMixin, forms.Form):
    display_name = forms.CharField(
        max_length=80, required=False, help_text="Shown across Orbit. Leave empty to use your name."
    )
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)


class AppearanceForm(forms.Form):
    theme = forms.ChoiceField(choices=Profile.THEME_CHOICES)
    accent = forms.ChoiceField(choices=Profile.ACCENT_CHOICES)


class GitHubKeyForm(StyledFormMixin, forms.Form):
    key = forms.CharField(
        label="GitHub personal access token",
        widget=forms.PasswordInput(attrs={"placeholder": "ghp_... or github_pat_...", "autocomplete": "off"}),
        max_length=255,
    )

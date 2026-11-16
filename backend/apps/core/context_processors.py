from apps.accounts.models import Profile
from apps.projects.models import TimeEntry


def orbit(request):
    user = request.user
    if not user.is_authenticated:
        return {"ui_theme": "dark", "ui_accent": "blue"}
    profile = Profile.for_user(user)
    avatar = ""
    for account in user.socialaccount_set.all():
        avatar = avatar or account.get_avatar_url()
    return {
        "ui_theme": profile.theme,
        "ui_accent": profile.accent,
        "user_avatar": avatar,
        "user_display": profile.display_name or user.get_full_name() or user.email or user.username,
        "user_greeting": profile.display_name or user.first_name,
        "running_timer": TimeEntry.objects.filter(project__owner=user, ended_at__isnull=True)
        .select_related("project")
        .first(),
    }

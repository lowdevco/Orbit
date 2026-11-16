from django.conf import settings
from django.db import models


class GitHubCache(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="github_cache")
    key = models.CharField(max_length=200)
    data = models.JSONField()
    fetched_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="unique_cache_key")]

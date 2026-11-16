import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    # Key derived from SECRET_KEY: rotating SECRET_KEY makes stored keys unreadable (users re-enter them).
    digest = hashlib.sha256(("orbit-keys:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class Profile(models.Model):
    THEME_CHOICES = [("dark", "Dark"), ("light", "Light"), ("system", "System")]
    # (key, label, swatch hex). Swatches are fixed values, never user input, so they're safe in style="".
    ACCENTS = [
        ("blue", "Blue", "#2f81f7"),
        ("green", "Git green", "#2da44e"),
        ("purple", "Purple", "#8957e5"),
        ("orange", "Orange", "#e16f24"),
        ("pink", "Pink", "#d6409f"),
        ("teal", "Teal", "#1b9aaa"),
        ("yellow", "Yellow", "#d4a72c"),
    ]
    ACCENT_CHOICES = [(key, label) for key, label, _ in ACCENTS]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=80, blank=True)
    theme = models.CharField(max_length=6, choices=THEME_CHOICES, default="dark")
    accent = models.CharField(max_length=6, choices=ACCENT_CHOICES, default="blue")
    github_key_encrypted = models.TextField(blank=True)

    @property
    def accent_hex(self):
        return next((hex_ for key, _, hex_ in self.ACCENTS if key == self.accent), "#2f81f7")

    @classmethod
    def for_user(cls, user):
        return cls.objects.get_or_create(user=user)[0]

    @property
    def github_key(self):
        if not self.github_key_encrypted:
            return ""
        try:
            return _fernet().decrypt(self.github_key_encrypted.encode()).decode()
        except InvalidToken:
            return ""

    @github_key.setter
    def github_key(self, value):
        self.github_key_encrypted = _fernet().encrypt(value.encode()).decode() if value else ""

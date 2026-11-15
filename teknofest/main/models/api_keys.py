import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class JuryAPIKey(models.Model):
    """A personal, expiring bearer token for jury API access."""

    class Duration(models.IntegerChoices):
        ONE_DAY = 1, _("1 day")
        SEVEN_DAYS = 7, _("7 days")
        THIRTY_DAYS = 30, _("30 days")
        NINETY_DAYS = 90, _("90 days")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jury_api_keys",
    )
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=16, unique=True)
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("user", "expires_at"))]

    def __str__(self) -> str:
        return f"{self.user} · {self.name} ({self.prefix}…)"

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @classmethod
    def create_key(cls, user, name: str, duration_days: int):
        if duration_days not in cls.Duration.values:
            raise ValueError("Unsupported API key duration.")

        raw_key = f"ptj_{secrets.token_urlsafe(32)}"
        key = cls.objects.create(
            user=user,
            name=name.strip(),
            prefix=raw_key[:12],
            key_hash=cls.hash_key(raw_key),
            expires_at=timezone.now() + timedelta(days=duration_days),
        )
        return key, raw_key

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and not self.is_expired

    @property
    def status(self) -> str:
        if self.revoked_at is not None:
            return "revoked"
        if self.is_expired:
            return "expired"
        return "active"

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

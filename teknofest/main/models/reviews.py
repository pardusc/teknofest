from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """A jury member's evaluation of one application."""

    application = models.ForeignKey(
        "Application",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    juror = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    note = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("application", "juror"),
                name="unique_review_per_application_and_juror",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.application} · {self.juror}"

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def juror_name(self) -> str:
        """Name shown to other jury members when listing reviews."""
        return self.juror.get_full_name() or self.juror.username

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Review(models.Model):
    """A jury member's evaluation of one application."""

    application = models.ForeignKey(
        "Application",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("Application"),
    )
    juror = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name=_("Juror"),
    )
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Score"),
    )
    note = models.TextField(blank=True, verbose_name=_("Note"))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Completed at"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Review")
        verbose_name_plural = _("Reviews")
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

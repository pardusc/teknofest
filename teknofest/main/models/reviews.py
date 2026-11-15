from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """A jury member's evaluation of one application."""

    application = models.ForeignKey(
        "Application",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Başvuru",
    )
    juror = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Jüri üyesi",
    )
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Puan",
    )
    note = models.TextField(blank=True, verbose_name="Not")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Tamamlanma")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Son güncelleme")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Değerlendirme"
        verbose_name_plural = "Değerlendirmeler"
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

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import get_language


class SiteSettings(models.Model):
    """Singleton with competition-wide and home-page settings."""

    class ApplicationStatus(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        OPEN = "open", "Open"
        IN_REVIEW = "in_review", "In review"
        CLOSED = "closed", "Closed"

    site_title = models.CharField(max_length=128, default="Pardus Teknofest")
    competition_name = models.CharField(
        max_length=255,
        default="Pardus Hata Yakalama ve Geliştirme Yarışması",
    )
    application_status = models.CharField(
        max_length=16,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.OPEN,
    )
    application_opens_at = models.DateTimeField(null=True, blank=True)
    application_closes_at = models.DateTimeField(null=True, blank=True)

    hero_eyebrow = models.CharField(max_length=255, blank=True)
    hero_title = models.CharField(max_length=255, blank=True)
    hero_lead = models.TextField(blank=True)
    announcement = models.TextField(blank=True)
    announcement_active = models.BooleanField(default=False)
    calendar_note = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    footer_tagline = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self) -> str:
        return self.site_title

    @property
    def current_year(self) -> int:
        """The competition year is always the current local calendar year."""
        return timezone.localdate().year

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.application_opens_at
            and self.application_closes_at
            and self.application_closes_at <= self.application_opens_at
        ):
            errors["application_closes_at"] = (
                "The closing date must be after the opening date."
            )

        if errors:
            raise ValidationError(errors)

    @classmethod
    def load(cls) -> "SiteSettings":
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings

    @property
    def is_application_open(self) -> bool:
        if self.application_status != self.ApplicationStatus.OPEN:
            return False
        now = timezone.now()
        if self.application_opens_at and now < self.application_opens_at:
            return False
        if self.application_closes_at and now > self.application_closes_at:
            return False
        return True

    def localized(self, language=None) -> dict:
        """Resolve text fields for the active language, falling back to base values."""
        language = language or get_language() or django_settings.LANGUAGE_CODE
        translation = self.translations.filter(language=language).first()
        return {
            field: (getattr(translation, field, "") or getattr(self, field))
            for field in TRANSLATABLE_FIELDS
        }


TRANSLATABLE_FIELDS = (
    "hero_eyebrow",
    "hero_title",
    "hero_lead",
    "announcement",
    "calendar_note",
    "footer_tagline",
)


class SiteSettingsTranslation(models.Model):
    settings = models.ForeignKey(
        SiteSettings,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    language = models.CharField(
        max_length=8,
        choices=django_settings.LANGUAGES,
    )
    hero_eyebrow = models.CharField(max_length=255, blank=True)
    hero_title = models.CharField(max_length=255, blank=True)
    hero_lead = models.TextField(blank=True)
    announcement = models.TextField(blank=True)
    calendar_note = models.TextField(blank=True)
    footer_tagline = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("settings", "language"),
                name="unique_settings_translation_per_language",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.settings} · {self.language}"

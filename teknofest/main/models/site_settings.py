from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _


class SiteSettings(models.Model):
    """Singleton with competition-wide and home-page settings."""

    class ApplicationStatus(models.TextChoices):
        UPCOMING = "upcoming", _("Upcoming")
        OPEN = "open", _("Open")
        IN_REVIEW = "in_review", _("In review")
        CLOSED = "closed", _("Closed")

    site_title = models.CharField(
        max_length=128,
        default="Pardus Teknofest",
        verbose_name=_("Site title"),
    )
    competition_name = models.CharField(
        max_length=255,
        default="Pardus Hata Yakalama ve Geliştirme Yarışması",
        verbose_name=_("Competition name"),
    )
    application_status = models.CharField(
        max_length=16,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.OPEN,
        verbose_name=_("Application status"),
    )
    application_opens_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Application opens at"),
    )
    application_closes_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Application closes at"),
    )

    hero_eyebrow = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Hero eyebrow"),
    )
    hero_title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Hero title"),
    )
    hero_lead = models.TextField(blank=True, verbose_name=_("Hero lead"))
    announcement = models.TextField(blank=True, verbose_name=_("Announcement"))
    announcement_active = models.BooleanField(default=False, verbose_name=_("Announcement active"))
    calendar_note = models.TextField(blank=True, verbose_name=_("Calendar note"))
    contact_email = models.EmailField(blank=True, verbose_name=_("Contact email"))
    footer_tagline = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Footer tagline"),
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        verbose_name = _("Site settings")
        verbose_name_plural = _("Site settings")

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
        verbose_name=_("Settings"),
    )
    language = models.CharField(
        max_length=8,
        choices=django_settings.LANGUAGES,
        verbose_name=_("Language"),
    )
    hero_eyebrow = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Hero eyebrow"),
    )
    hero_title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Hero title"),
    )
    hero_lead = models.TextField(blank=True, verbose_name=_("Hero lead"))
    announcement = models.TextField(blank=True, verbose_name=_("Announcement"))
    calendar_note = models.TextField(blank=True, verbose_name=_("Calendar note"))
    footer_tagline = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Footer tagline"),
    )

    class Meta:
        verbose_name = _("Site settings translation")
        verbose_name_plural = _("Site settings translations")
        constraints = [
            models.UniqueConstraint(
                fields=("settings", "language"),
                name="unique_settings_translation_per_language",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.settings} · {self.language}"

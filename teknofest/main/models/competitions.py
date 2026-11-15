import re

from django.conf import settings as django_settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from ..validators import (
    APPLICATION_TITLE_KEY,
    APPLICATION_TITLE_MAX_LENGTH,
    APPLICATION_TITLE_MIN_LENGTH,
)


class CompetitionYear(models.Model):
    """A competition edition. Applications are always tied to one year."""

    year = models.PositiveSmallIntegerField(unique=True, verbose_name=_("Year"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        ordering = ("-year",)
        verbose_name = _("Competition year")
        verbose_name_plural = _("Competition years")

    def __str__(self) -> str:
        return str(self.year)

    @classmethod
    def current(cls) -> "CompetitionYear":
        """Return the current competition year, creating its tag if needed."""
        year = timezone.localdate().year
        instance, _ = cls.objects.get_or_create(
            year=year,
            defaults={"is_active": True},
        )
        return instance


class Category(models.Model):
    """A competition category, for example bug hunting or development."""

    slug = models.SlugField(max_length=64, unique=True, verbose_name=_("Slug"))
    name = models.CharField(max_length=128, verbose_name=_("Name"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    home_description = models.TextField(blank=True, verbose_name=_("Home description"))
    home_highlights = models.TextField(
        blank=True,
        verbose_name=_("Home highlights"),
        help_text=_("One item per line, shown on the home page."),
    )
    code_prefix = models.CharField(
        max_length=16,
        blank=True,
        verbose_name=_("Code prefix"),
        help_text=_("Prefix used in application codes, for example BUG."),
    )
    order = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))

    class Meta:
        ordering = ("order", "name")
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")

    def __str__(self) -> str:
        return self.name

    def translation_for(self, language=None):
        language = language or get_language() or django_settings.LANGUAGE_CODE
        cache = getattr(self, "_translation_cache", {})
        if language not in cache:
            cache[language] = self.translations.filter(language=language).first()
            self._translation_cache = cache
        return cache[language]

    @property
    def display_name(self) -> str:
        translation = self.translation_for()
        return (translation.name if translation else "") or self.name

    @property
    def display_description(self) -> str:
        translation = self.translation_for()
        return (translation.description if translation else "") or self.description

    @property
    def display_home_description(self) -> str:
        translation = self.translation_for()
        return (
            (translation.home_description if translation else "")
            or self.home_description
            or self.display_description
        )

    @property
    def highlight_list(self) -> list[str]:
        translation = self.translation_for()
        text = (
            (translation.home_highlights if translation else "")
            or self.home_highlights
        )
        return [line.strip() for line in text.splitlines() if line.strip()]


class CategoryTranslation(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="translations",
        verbose_name=_("Category"),
    )
    language = models.CharField(
        max_length=8,
        choices=django_settings.LANGUAGES,
        verbose_name=_("Language"),
    )
    name = models.CharField(max_length=128, blank=True, verbose_name=_("Name"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    home_description = models.TextField(blank=True, verbose_name=_("Home description"))
    home_highlights = models.TextField(blank=True, verbose_name=_("Home highlights"))

    class Meta:
        verbose_name = _("Category translation")
        verbose_name_plural = _("Category translations")
        constraints = [
            models.UniqueConstraint(
                fields=("category", "language"),
                name="unique_category_translation_per_language",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category} · {self.language}"


class FormDefinition(models.Model):
    """The form an applicant fills in for one category in one year."""

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        IN_REVIEW = "in_review", _("In review")
        CLOSED = "closed", _("Closed")

    class AttachmentPolicy(models.TextChoices):
        NONE = "none", _("No attachments")
        OPTIONAL = "optional", _("Optional")
        REQUIRED = "required", _("Required")

    year = models.ForeignKey(
        CompetitionYear,
        on_delete=models.PROTECT,
        related_name="forms",
        verbose_name=_("Year"),
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="forms",
        verbose_name=_("Category"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Title"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name=_("Status"),
    )
    mask_applicant_identity = models.BooleanField(
        default=False,
        verbose_name=_("Mask applicant identity"),
        help_text=_("Hide the applicant's name and e-mail from the jury."),
    )
    attachment_policy = models.CharField(
        max_length=16,
        choices=AttachmentPolicy.choices,
        default=AttachmentPolicy.OPTIONAL,
        verbose_name=_("Attachment policy"),
    )
    submission_limit = models.PositiveSmallIntegerField(
        default=1,
        verbose_name=_("Submission limit"),
        help_text=_(
            "How many applications one applicant may submit for this form. "
            "0 means unlimited."
        ),
    )
    opens_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Opens at"))
    closes_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Closes at"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        ordering = ("-year__year", "category__order")
        verbose_name = _("Form definition")
        verbose_name_plural = _("Form definitions")
        constraints = [
            models.UniqueConstraint(
                fields=("year", "category"),
                name="unique_form_per_year_and_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.year} · {self.category.name}"

    def clean(self):
        super().clean()
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValidationError(
                {"closes_at": _("The closing date must be after the opening date.")}
            )

    @property
    def is_accepting_submissions(self) -> bool:
        from .site_settings import SiteSettings

        if self.status != self.Status.OPEN:
            return False

        settings = SiteSettings.load()
        if self.year.year != settings.current_year:
            return False
        if not settings.is_application_open:
            return False

        now = timezone.now()
        if self.opens_at and now < self.opens_at:
            return False
        if self.closes_at and now > self.closes_at:
            return False
        return True

    def submission_count_for(self, applicant) -> int:
        """Applications the applicant already submitted for this form."""
        return self.applications.filter(applicant=applicant).count()

    def has_reached_submission_limit(self, applicant) -> bool:
        """Whether the applicant used every slot; a limit of 0 is unlimited."""
        if not self.submission_limit:
            return False
        return self.submission_count_for(applicant) >= self.submission_limit

    def accepts_submission_from(self, applicant) -> bool:
        return self.is_accepting_submissions and not self.has_reached_submission_limit(
            applicant
        )


class FormField(models.Model):
    """A single field in a dynamic form definition."""

    class FieldType(models.TextChoices):
        SHORT_TEXT = "short_text", _("Short text")
        LONG_TEXT = "long_text", _("Long text")
        MARKDOWN = "markdown", _("Markdown")
        SELECT = "select", _("Single choice")
        MULTI_SELECT = "multi_select", _("Multiple choice")
        NUMBER = "number", _("Number")
        EMAIL = "email", _("E-mail")
        URL = "url", _("URL")
        BOOLEAN = "boolean", _("Yes / No")
        DATE = "date", _("Date")

    class ReviewVisibility(models.TextChoices):
        VISIBLE = "visible", _("Visible")
        MASKED = "masked", _("Masked")
        HIDDEN = "hidden", _("Hidden")

    TEXT_TYPES = (
        FieldType.SHORT_TEXT,
        FieldType.LONG_TEXT,
        FieldType.MARKDOWN,
    )
    CHOICE_TYPES = (FieldType.SELECT, FieldType.MULTI_SELECT)
    RESERVED_KEYS = {"id", "submit", "action", "csrfmiddlewaretoken"}

    form = models.ForeignKey(
        FormDefinition,
        on_delete=models.CASCADE,
        related_name="fields",
        verbose_name=_("Form"),
    )
    key = models.SlugField(
        max_length=64,
        verbose_name=_("Key"),
        help_text=_("Identifier used in submitted data, for example steps_to_reproduce."),
    )
    label = models.CharField(max_length=255, verbose_name=_("Label"))
    field_type = models.CharField(
        max_length=16,
        choices=FieldType.choices,
        verbose_name=_("Field type"),
    )
    short_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Short description"),
        help_text=_("Shown under the question title."),
    )
    placeholder = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Placeholder"),
        help_text=_(
            "Hint shown inside empty text fields. "
            "Leave blank to use a default hint."
        ),
    )
    is_required = models.BooleanField(default=True, verbose_name=_("Required"))
    min_length = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Minimum length"),
    )
    max_length = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Maximum length"),
    )
    regex = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Regular expression"),
        help_text=_("Optional regular expression the answer must match."),
    )
    regex_error_message = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Regular expression error message"),
    )
    choices = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Choices"),
        help_text=_('List of objects like {"value": "low", "label": "Low"}.'),
    )
    order = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    review_visibility = models.CharField(
        max_length=8,
        choices=ReviewVisibility.choices,
        default=ReviewVisibility.VISIBLE,
        verbose_name=_("Review visibility"),
        help_text=_("What the jury can see for this field."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        ordering = ("order", "id")
        verbose_name = _("Form field")
        verbose_name_plural = _("Form fields")
        constraints = [
            models.UniqueConstraint(
                fields=("form", "key"),
                name="unique_field_key_per_form",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label} ({self.key})"

    def clean(self):
        super().clean()
        errors = {}

        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.key or ""):
            errors["key"] = (
                _("Use lowercase letters, digits and underscores, starting with a letter.")
            )
        if self.key in self.RESERVED_KEYS:
            errors["key"] = _("This key is reserved.")

        if self.key == APPLICATION_TITLE_KEY:
            if self.field_type != self.FieldType.SHORT_TEXT:
                errors["field_type"] = _(
                    "The title field must be a short text field."
                )
            if not self.is_required:
                errors["is_required"] = _("The title field must be required.")
            if self.review_visibility != self.ReviewVisibility.VISIBLE:
                errors["review_visibility"] = _(
                    "The title field must be visible to the jury."
                )
            if (
                self.max_length is not None
                and self.max_length > APPLICATION_TITLE_MAX_LENGTH
            ):
                errors["max_length"] = _(
                    "The title field can be at most %(max)s characters."
                ) % {"max": APPLICATION_TITLE_MAX_LENGTH}
            if (
                self.min_length is not None
                and self.min_length < APPLICATION_TITLE_MIN_LENGTH
            ):
                errors["min_length"] = _(
                    "The title field must be at least %(min)s characters."
                ) % {"min": APPLICATION_TITLE_MIN_LENGTH}

        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            errors["max_length"] = _("Maximum length must be at least the minimum length.")

        if self.regex:
            try:
                re.compile(self.regex)
            except re.error:
                errors["regex"] = _("Enter a valid regular expression.")

        if self.field_type in self.CHOICE_TYPES and not self.choice_pairs:
            errors[NON_FIELD_ERRORS] = (
                _("Single and multiple choice fields require at least one choice.")
            )

        if errors:
            raise ValidationError(errors)

    @property
    def choice_pairs(self) -> list[tuple[str, str]]:
        pairs = []
        for item in self.choices or []:
            if isinstance(item, dict):
                value = str(item.get("value", "")).strip()
                label = str(item.get("label") or value).strip()
            else:
                value = label = str(item).strip()
            if value:
                pairs.append((value, label))
        return pairs

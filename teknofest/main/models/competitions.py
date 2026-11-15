import re

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.utils import timezone


class CompetitionYear(models.Model):
    """A competition edition. Applications are always tied to one year."""

    year = models.PositiveSmallIntegerField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-year",)

    def __str__(self) -> str:
        return str(self.year)


class Category(models.Model):
    """A competition category, for example bug/suggestion or development."""

    class AttachmentPolicy(models.TextChoices):
        NONE = "none", "No attachments"
        OPTIONAL = "optional", "Optional"
        REQUIRED = "required", "Required"

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    code_prefix = models.CharField(
        max_length=16,
        blank=True,
        help_text="Prefix used in application codes, for example BUG.",
    )
    attachment_policy = models.CharField(
        max_length=16,
        choices=AttachmentPolicy.choices,
        default=AttachmentPolicy.OPTIONAL,
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("order", "name")
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class FormDefinition(models.Model):
    """The form an applicant fills in for one category in one year."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_REVIEW = "in_review", "In review"
        CLOSED = "closed", "Closed"

    year = models.ForeignKey(
        CompetitionYear,
        on_delete=models.PROTECT,
        related_name="forms",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="forms",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    mask_applicant_identity = models.BooleanField(
        default=False,
        help_text="Hide the applicant's name and e-mail from the jury.",
    )
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-year__year", "category__order")
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
                {"closes_at": "The closing date must be after the opening date."}
            )

    @property
    def is_accepting_submissions(self) -> bool:
        if self.status != self.Status.OPEN:
            return False
        now = timezone.now()
        if self.opens_at and now < self.opens_at:
            return False
        if self.closes_at and now > self.closes_at:
            return False
        return True


class FormField(models.Model):
    """A single field in a dynamic form definition."""

    class FieldType(models.TextChoices):
        SHORT_TEXT = "short_text", "Short text"
        LONG_TEXT = "long_text", "Long text"
        MARKDOWN = "markdown", "Markdown"
        SELECT = "select", "Single choice"
        MULTI_SELECT = "multi_select", "Multiple choice"
        NUMBER = "number", "Number"
        EMAIL = "email", "E-mail"
        URL = "url", "URL"
        BOOLEAN = "boolean", "Yes / No"
        DATE = "date", "Date"

    class ReviewVisibility(models.TextChoices):
        VISIBLE = "visible", "Visible"
        MASKED = "masked", "Masked"
        HIDDEN = "hidden", "Hidden"

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
    )
    key = models.SlugField(
        max_length=64,
        help_text="Identifier used in submitted data, for example steps_to_reproduce.",
    )
    label = models.CharField(max_length=255)
    field_type = models.CharField(max_length=16, choices=FieldType.choices)
    help_text = models.CharField(max_length=255, blank=True)
    is_required = models.BooleanField(default=True)
    min_length = models.PositiveIntegerField(null=True, blank=True)
    max_length = models.PositiveIntegerField(null=True, blank=True)
    regex = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional regular expression the answer must match.",
    )
    regex_error_message = models.CharField(max_length=255, blank=True)
    choices = models.JSONField(
        default=list,
        blank=True,
        help_text='List of objects like {"value": "low", "label": "Low"}.',
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    review_visibility = models.CharField(
        max_length=8,
        choices=ReviewVisibility.choices,
        default=ReviewVisibility.VISIBLE,
        help_text="What the jury can see for this field.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "id")
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
                "Use lowercase letters, digits and underscores, starting with a letter."
            )
        if self.key in self.RESERVED_KEYS:
            errors["key"] = "This key is reserved."

        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            errors["max_length"] = "Maximum length must be at least the minimum length."

        if self.regex:
            try:
                re.compile(self.regex)
            except re.error:
                errors["regex"] = "Enter a valid regular expression."

        if self.field_type in self.CHOICE_TYPES and not self.choice_pairs:
            errors[NON_FIELD_ERRORS] = (
                "Single and multiple choice fields require at least one choice."
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

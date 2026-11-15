import re

from django.conf import settings as django_settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _


class CompetitionYear(models.Model):
    """A competition edition. Applications are always tied to one year."""

    year = models.PositiveSmallIntegerField(unique=True, verbose_name="Yıl")
    is_active = models.BooleanField(default=True, verbose_name="Etkin")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")

    class Meta:
        ordering = ("-year",)
        verbose_name = "Yarışma yılı"
        verbose_name_plural = "Yarışma yılları"

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

    slug = models.SlugField(max_length=64, unique=True, verbose_name="Kısa ad")
    name = models.CharField(max_length=128, verbose_name="Ad")
    description = models.TextField(blank=True, verbose_name="Açıklama")
    home_description = models.TextField(blank=True, verbose_name="Ana sayfa açıklaması")
    home_highlights = models.TextField(
        blank=True,
        verbose_name="Ana sayfa maddeleri",
        help_text="One item per line, shown on the home page.",
    )
    code_prefix = models.CharField(
        max_length=16,
        blank=True,
        verbose_name="Kod ön eki",
        help_text="Prefix used in application codes, for example BUG.",
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    is_active = models.BooleanField(default=True, verbose_name="Etkin")

    class Meta:
        ordering = ("order", "name")
        verbose_name = "Kategori"
        verbose_name_plural = "Kategoriler"

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
    )
    language = models.CharField(
        max_length=8,
        choices=django_settings.LANGUAGES,
    )
    name = models.CharField(max_length=128, blank=True)
    description = models.TextField(blank=True)
    home_description = models.TextField(blank=True)
    home_highlights = models.TextField(blank=True)

    class Meta:
        verbose_name = "Kategori çevirisi"
        verbose_name_plural = "Kategori çevirileri"
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
        OPEN = "open", "Açık"
        IN_REVIEW = "in_review", "İncelemede"
        CLOSED = "closed", "Kapalı"

    class AttachmentPolicy(models.TextChoices):
        NONE = "none", "Ek dosya yok"
        OPTIONAL = "optional", "İsteğe bağlı"
        REQUIRED = "required", "Zorunlu"

    year = models.ForeignKey(
        CompetitionYear,
        on_delete=models.PROTECT,
        related_name="forms",
        verbose_name="Yıl",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="forms",
        verbose_name="Kategori",
    )
    title = models.CharField(max_length=255, verbose_name="Başlık")
    description = models.TextField(blank=True, verbose_name="Açıklama")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name="Durum",
    )
    mask_applicant_identity = models.BooleanField(
        default=False,
        verbose_name="Başvuru sahibi kimliğini gizle",
        help_text="Hide the applicant's name and e-mail from the jury.",
    )
    attachment_policy = models.CharField(
        max_length=16,
        choices=AttachmentPolicy.choices,
        default=AttachmentPolicy.OPTIONAL,
        verbose_name="Ek dosya politikası",
    )
    submission_override = models.BooleanField(
        default=False,
        verbose_name="Gönderim istisnası",
        help_text=(
            "Allow submissions even when the global application period is closed. "
            "The form's own dates still apply."
        ),
    )
    opens_at = models.DateTimeField(null=True, blank=True, verbose_name="Açılış")
    closes_at = models.DateTimeField(null=True, blank=True, verbose_name="Kapanış")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Son güncelleme")

    class Meta:
        ordering = ("-year__year", "category__order")
        verbose_name = "Form tanımı"
        verbose_name_plural = "Form tanımları"
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
        if not settings.is_application_open and not self.submission_override:
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
        SHORT_TEXT = "short_text", "Kısa metin"
        LONG_TEXT = "long_text", "Uzun metin"
        MARKDOWN = "markdown", "Markdown"
        SELECT = "select", "Tek seçim"
        MULTI_SELECT = "multi_select", "Çoklu seçim"
        NUMBER = "number", "Sayı"
        EMAIL = "email", "E-posta"
        URL = "url", "URL"
        BOOLEAN = "boolean", "Evet / Hayır"
        DATE = "date", "Tarih"

    class ReviewVisibility(models.TextChoices):
        VISIBLE = "visible", "Görünür"
        MASKED = "masked", "Maskelenmiş"
        HIDDEN = "hidden", "Gizli"

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
        verbose_name="Form",
    )
    key = models.SlugField(
        max_length=64,
        verbose_name="Anahtar",
        help_text="Identifier used in submitted data, for example steps_to_reproduce.",
    )
    label = models.CharField(max_length=255, verbose_name="Etiket")
    field_type = models.CharField(
        max_length=16,
        choices=FieldType.choices,
        verbose_name="Alan türü",
    )
    short_description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Short description",
        help_text="Shown under the question title.",
    )
    placeholder = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Placeholder",
        help_text=(
            "Hint shown inside empty text fields. "
            "Leave blank to use a default hint."
        ),
    )
    is_required = models.BooleanField(default=True, verbose_name="Zorunlu")
    min_length = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="En az uzunluk",
    )
    max_length = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="En fazla uzunluk",
    )
    regex = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Düzenli ifade",
        help_text="Optional regular expression the answer must match.",
    )
    regex_error_message = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Düzenli ifade hata mesajı",
    )
    choices = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Seçenekler",
        help_text='List of objects like {"value": "low", "label": "Low"}.',
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Sıra")
    is_active = models.BooleanField(default=True, verbose_name="Etkin")
    review_visibility = models.CharField(
        max_length=8,
        choices=ReviewVisibility.choices,
        default=ReviewVisibility.VISIBLE,
        verbose_name="İnceleme görünürlüğü",
        help_text="What the jury can see for this field.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Son güncelleme")

    class Meta:
        ordering = ("order", "id")
        verbose_name = "Form alanı"
        verbose_name_plural = "Form alanları"
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

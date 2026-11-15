import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.utils.translation import gettext_lazy as _
from django.dispatch import receiver

from ..validators import validate_application_title


def attachment_upload_to(instance, filename):
    return (
        f"applications/{instance.application.year.year}/"
        f"{instance.application.public_id}/{Path(filename).name}"
    )


class Application(models.Model):
    """An applicant's submission for one form (year + category)."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", _("Submitted")
        IN_REVIEW = "in_review", _("In review")
        EVALUATED = "evaluated", _("Evaluated")

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name=_("Public ID"),
    )
    code = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("Code"),
        help_text=_("Assigned when the application is submitted."),
    )
    title = models.CharField(
        max_length=100,
        verbose_name="Application title",
        validators=[validate_application_title],
        help_text="The title entered by the applicant.",
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name=_("Applicant"),
    )
    form = models.ForeignKey(
        "FormDefinition",
        on_delete=models.PROTECT,
        related_name="applications",
        verbose_name=_("Form"),
    )
    year = models.ForeignKey(
        "CompetitionYear",
        on_delete=models.PROTECT,
        related_name="applications",
        verbose_name=_("Year"),
    )
    category = models.ForeignKey(
        "Category",
        on_delete=models.PROTECT,
        related_name="applications",
        verbose_name=_("Category"),
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SUBMITTED,
        verbose_name=_("Status"),
    )
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Submitted at"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Application")
        verbose_name_plural = _("Applications")
        constraints = [
            models.UniqueConstraint(
                fields=("applicant", "form"),
                name="unique_application_per_applicant_and_form",
            ),
        ]

    def __str__(self) -> str:
        return self.code or f"Draft {self.public_id}"

    @property
    def status_label(self):
        return {
            self.Status.SUBMITTED: _("Submitted"),
            self.Status.IN_REVIEW: _("In review"),
            self.Status.EVALUATED: _("Evaluated"),
        }.get(self.status, self.get_status_display())

    @property
    def status_tone(self) -> str:
        return {
            self.Status.SUBMITTED: "chip-neutral",
            self.Status.IN_REVIEW: "chip-warning",
            self.Status.EVALUATED: "chip-success",
        }.get(self.status, "chip-neutral")

    @property
    def is_editable(self) -> bool:
        return (
            self.status == self.Status.SUBMITTED
            and self.form.is_accepting_submissions
        )


class ApplicationAnswer(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name=_("Application"),
    )
    field = models.ForeignKey(
        "FormField",
        on_delete=models.PROTECT,
        related_name="answers",
        verbose_name=_("Field"),
    )
    value = models.JSONField(verbose_name=_("Value"))

    class Meta:
        ordering = ("field__order", "id")
        verbose_name = _("Application answer")
        verbose_name_plural = _("Application answers")
        constraints = [
            models.UniqueConstraint(
                fields=("application", "field"),
                name="unique_answer_per_application_and_field",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.field.key} = {self.value!r}"


class Attachment(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("Application"),
    )
    file = models.FileField(upload_to=attachment_upload_to, verbose_name=_("File"))
    original_name = models.CharField(max_length=255, verbose_name=_("Original name"))
    content_type = models.CharField(max_length=64, verbose_name=_("Content type"))
    size = models.PositiveIntegerField(verbose_name=_("Size"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Uploaded at"))

    class Meta:
        ordering = ("uploaded_at", "id")
        verbose_name = _("Attachment")
        verbose_name_plural = _("Attachments")

    def __str__(self) -> str:
        return self.original_name


class ApplicationSequence(models.Model):
    """Per year and category counter used for readable application codes."""

    year = models.ForeignKey(
        "CompetitionYear",
        on_delete=models.CASCADE,
        related_name="sequences",
    )
    category = models.ForeignKey(
        "Category",
        on_delete=models.CASCADE,
        related_name="sequences",
    )
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Application sequence")
        verbose_name_plural = _("Application sequences")
        constraints = [
            models.UniqueConstraint(
                fields=("year", "category"),
                name="unique_sequence_per_year_and_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.year} · {self.category}"


@receiver(post_delete, sender=Attachment)
def delete_attachment_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)

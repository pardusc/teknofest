import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver


def attachment_upload_to(instance, filename):
    return (
        f"applications/{instance.application.year.year}/"
        f"{instance.application.public_id}/{Path(filename).name}"
    )


class Application(models.Model):
    """An applicant's submission for one form (year + category)."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        IN_REVIEW = "in_review", "In review"
        EVALUATED = "evaluated", "Evaluated"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    code = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        help_text="Assigned when the application is submitted.",
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    form = models.ForeignKey(
        "FormDefinition",
        on_delete=models.PROTECT,
        related_name="applications",
    )
    year = models.ForeignKey(
        "CompetitionYear",
        on_delete=models.PROTECT,
        related_name="applications",
    )
    category = models.ForeignKey(
        "Category",
        on_delete=models.PROTECT,
        related_name="applications",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("applicant", "form"),
                name="unique_application_per_applicant_and_form",
            ),
        ]

    def __str__(self) -> str:
        return self.code or f"Draft {self.public_id}"

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
    )
    field = models.ForeignKey(
        "FormField",
        on_delete=models.PROTECT,
        related_name="answers",
    )
    value = models.JSONField()

    class Meta:
        ordering = ("field__order", "id")
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
    )
    file = models.FileField(upload_to=attachment_upload_to)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=64)
    size = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("uploaded_at", "id")

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

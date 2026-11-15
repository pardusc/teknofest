import uuid
from datetime import date, datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from PIL import Image

from ..dynamic_forms import build_form
from ..models import (
    Application,
    ApplicationAnswer,
    ApplicationSequence,
    Attachment,
    Category,
    FormDefinition,
)
from ..permissions import is_jury

MAX_ATTACHMENTS = 10
MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_TOTAL_SIZE = 10 * 1024 * 1024

ALLOWED_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
}


def start_application(applicant, form: FormDefinition) -> Application:
    """Return the applicant's existing application, or start a new draft."""
    _ensure_applicant(applicant)
    if not form.is_accepting_submissions:
        raise ValidationError("This form is not accepting applications.")

    existing = Application.objects.filter(applicant=applicant, form=form).first()
    if existing:
        return existing

    try:
        return Application.objects.create(
            applicant=applicant,
            form=form,
            year=form.year,
            category=form.category,
        )
    except IntegrityError:
        return Application.objects.get(applicant=applicant, form=form)


def save_draft(application: Application, data: dict) -> Application:
    """Validate and store partial answers. Required fields may stay empty."""
    _ensure_applicant(application.applicant)
    _ensure_editable(application)
    fields = _active_fields(application)

    form = build_form(application.form, data=data, enforce_required=False)
    if not form.is_valid():
        raise ValidationError(form.errors)

    _write_answers(application, form, fields, data.keys())
    application.save(update_fields=["updated_at"])
    return application


def submit(application: Application, data: dict | None = None) -> Application:
    """Validate everything and finalize the application with a readable code."""
    with transaction.atomic():
        application = Application.objects.select_for_update().get(pk=application.pk)
        _ensure_applicant(application.applicant)
        _ensure_editable(application)

        if data is not None:
            save_draft(application, data)

        fields = _active_fields(application)
        answers = {
            answer.field.key: answer.value
            for answer in application.answers.select_related("field")
            if answer.field.is_active
        }

        form = build_form(application.form, data=answers)
        if not form.is_valid():
            raise ValidationError(form.errors)

        profile = getattr(application.applicant, "profile", None)
        if profile is None or not profile.is_complete:
            raise ValidationError("Complete your profile before submitting.")

        _check_attachments(application)

        if not application.code:
            application.code = _next_code(application)

        application.status = Application.Status.SUBMITTED
        application.submitted_at = timezone.now()
        application.save(
            update_fields=["code", "status", "submitted_at", "updated_at"]
        )

        _send_confirmation(application)

    return application


def delete_application(application: Application) -> None:
    """Delete an application and its files while it is still editable."""
    with transaction.atomic():
        application = Application.objects.select_for_update().get(pk=application.pk)
        _ensure_applicant(application.applicant)
        _ensure_editable(application)
        application.delete()


def add_attachment(
    application: Application,
    upload: UploadedFile,
) -> Attachment:
    _ensure_applicant(application.applicant)
    _ensure_editable(application)

    if application.category.attachment_policy == Category.AttachmentPolicy.NONE:
        raise ValidationError("This category does not accept attachments.")

    if application.attachments.count() >= MAX_ATTACHMENTS:
        raise ValidationError(
            f"At most {MAX_ATTACHMENTS} files can be uploaded per application."
        )

    current_total = application.attachments.aggregate(total=Sum("size"))["total"] or 0
    size = upload.size or 0
    if size > MAX_FILE_SIZE:
        raise ValidationError("Each file must be 2 MB or smaller.")
    if current_total + size > MAX_TOTAL_SIZE:
        raise ValidationError("Total attachment size must be 10 MB or smaller.")

    image_format = _verify_image(upload)
    content_type, extension = ALLOWED_IMAGE_FORMATS[image_format]

    original_name = Path(upload.name).name
    upload.name = f"{uuid.uuid4().hex}{extension}"

    return Attachment.objects.create(
        application=application,
        file=upload,
        original_name=original_name,
        content_type=content_type,
        size=size,
    )


def delete_attachment(attachment: Attachment) -> None:
    _ensure_applicant(attachment.application.applicant)
    _ensure_editable(attachment.application)
    attachment.delete()


def _ensure_applicant(user) -> None:
    if is_jury(user):
        raise ValidationError("Jury accounts cannot submit applications.")


def _ensure_editable(application: Application) -> None:
    if not application.is_editable:
        raise ValidationError("This application can no longer be edited.")


def _active_fields(application: Application) -> dict:
    return {
        field.key: field
        for field in application.form.fields.filter(is_active=True)
    }


def _write_answers(application, form, fields, submitted_keys) -> None:
    for key in set(submitted_keys) & set(fields):
        value = form.cleaned_data.get(key)
        if value in (None, "", []):
            ApplicationAnswer.objects.filter(
                application=application,
                field=fields[key],
            ).delete()
            continue
        ApplicationAnswer.objects.update_or_create(
            application=application,
            field=fields[key],
            defaults={"value": _json_value(value)},
        )


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _check_attachments(application: Application) -> None:
    policy = application.category.attachment_policy
    if policy == Category.AttachmentPolicy.NONE:
        if application.attachments.exists():
            raise ValidationError("This category does not accept attachments.")
    elif policy == Category.AttachmentPolicy.REQUIRED:
        if not application.attachments.exists():
            raise ValidationError(
                "At least one attachment is required for this category."
            )


def _next_code(application: Application) -> str:
    sequence, _ = ApplicationSequence.objects.select_for_update().get_or_create(
        year=application.year,
        category=application.category,
    )
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])

    prefix = application.category.code_prefix or application.category.slug.upper()
    return f"{prefix}-{application.year.year}-{sequence.last_number:05d}"


def _verify_image(upload: UploadedFile) -> str:
    try:
        image = Image.open(upload)
        image_format = image.format
        image.verify()
    except Exception as exc:
        raise ValidationError("Upload a JPG or PNG image.") from exc
    finally:
        upload.seek(0)

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Upload a JPG or PNG image.")
    return image_format


def _send_confirmation(application: Application) -> None:
    send_mail(
        subject=f"Application received: {application.code}",
        message=(
            f"Your {application.category.name} application has been received.\n\n"
            f"Application code: {application.code}\n"
            f"Year: {application.year.year}\n\n"
            "You can edit or delete your application until the deadline."
        ),
        from_email=None,
        recipient_list=[application.applicant.email],
        fail_silently=False,
    )

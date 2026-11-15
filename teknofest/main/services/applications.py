import uuid
from datetime import date, datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from PIL import Image

from ..dynamic_forms import build_form
from ..models import (
    Application,
    ApplicationAnswer,
    ApplicationSequence,
    Attachment,
    AuditEvent,
    FormDefinition,
)
from ..permissions import is_jury
from ..validators import APPLICATION_TITLE_KEY
from .audit import record

MAX_ATTACHMENTS = 10
MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_TOTAL_SIZE = 10 * 1024 * 1024

ALLOWED_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
}


def submit_application(applicant, form: FormDefinition, data, files=None) -> Application:
    """Create and submit a complete application in one step."""
    _ensure_applicant(applicant)
    if not form.is_accepting_submissions:
        raise ValidationError(_("This form is not accepting applications."))
    if form.has_reached_submission_limit(applicant):
        raise ValidationError(
            _("You have reached the application limit for this form.")
        )

    dynamic_form = build_form(form, data=data)
    if not dynamic_form.is_valid():
        raise ValidationError(dynamic_form.errors)

    title = _application_title(dynamic_form)
    _ensure_profile_complete(applicant)

    uploads = list(files or [])
    _check_attachment_policy(form, len(uploads))
    prepared = _prepare_uploads(uploads)

    with transaction.atomic():
        if form.has_reached_submission_limit(applicant):
            raise ValidationError(
                _("You have reached the application limit for this form.")
            )
        application = Application.objects.create(
            applicant=applicant,
            form=form,
            year=form.year,
            category=form.category,
            title=title,
            status=Application.Status.SUBMITTED,
            submitted_at=timezone.now(),
        )
        application.code = _next_code(application)
        application.save(update_fields=["code"])

        _write_answers(application, dynamic_form, _active_fields(form))
        for upload, image_format, size in prepared:
            _create_attachment(application, upload, image_format, size)

        record(
            AuditEvent.Action.APPLICATION_SUBMITTED,
            actor=applicant,
            application=application,
            form=form,
            code=application.code,
            year=application.year.year,
            category=application.category.slug,
        )
        _send_confirmation(application)

    return application


def update_application(application: Application, data, files=None) -> Application:
    """Update a submitted application with full validation."""
    _ensure_applicant(application.applicant)
    _ensure_editable(application)

    dynamic_form = build_form(application.form, data=data)
    if not dynamic_form.is_valid():
        raise ValidationError(dynamic_form.errors)

    title = _application_title(dynamic_form)

    uploads = list(files or [])
    existing_count = application.attachments.count()
    existing_total = _attachment_total(application)
    _check_attachment_policy(application.form, existing_count + len(uploads))
    prepared = _prepare_uploads(
        uploads,
        existing_count=existing_count,
        existing_total=existing_total,
    )

    with transaction.atomic():
        _write_answers(application, dynamic_form, _active_fields(application.form))
        for upload, image_format, size in prepared:
            _create_attachment(application, upload, image_format, size)
        application.title = title
        application.save(update_fields=["title", "updated_at"])
        record(
            AuditEvent.Action.APPLICATION_UPDATED,
            actor=application.applicant,
            application=application,
            form=application.form,
            code=application.code,
        )

    return application


def delete_application(application: Application) -> None:
    """Delete an application and its files while it is still editable."""
    with transaction.atomic():
        application = Application.objects.select_for_update().get(pk=application.pk)
        _ensure_applicant(application.applicant)
        _ensure_editable(application)
        record(
            AuditEvent.Action.APPLICATION_DELETED,
            actor=application.applicant,
            application=application,
            form=application.form,
            code=application.code,
            year=application.year.year,
            category=application.category.slug,
        )
        application.delete()


def add_attachment(application: Application, upload: UploadedFile) -> Attachment:
    _ensure_applicant(application.applicant)
    _ensure_editable(application)

    existing_count = application.attachments.count()
    _check_attachment_policy(application.form, existing_count + 1)
    prepared = _prepare_uploads(
        [upload],
        existing_count=existing_count,
        existing_total=_attachment_total(application),
    )
    upload, image_format, size = prepared[0]
    return _create_attachment(application, upload, image_format, size)


def delete_attachment(attachment: Attachment) -> None:
    application = attachment.application
    _ensure_applicant(application.applicant)
    _ensure_editable(application)

    if (
        application.form.attachment_policy == FormDefinition.AttachmentPolicy.REQUIRED
        and application.attachments.count() <= 1
    ):
        raise ValidationError(
            _("At least one attachment is required for this form.")
        )

    record(
        AuditEvent.Action.ATTACHMENT_REMOVED,
        actor=application.applicant,
        application=application,
        form=application.form,
        code=application.code,
        name=attachment.original_name,
        size=attachment.size,
    )
    attachment.delete()


def _ensure_applicant(user) -> None:
    if is_jury(user):
        raise ValidationError(_("Jury accounts cannot submit applications."))


def _ensure_editable(application: Application) -> None:
    if not application.is_editable:
        raise ValidationError(_("This application can no longer be edited."))


def _ensure_profile_complete(user) -> None:
    profile = getattr(user, "profile", None)
    if profile is None or not profile.is_complete:
        raise ValidationError(_("Complete your profile before submitting."))


def _active_fields(form: FormDefinition) -> dict:
    return {
        field.key: field
        for field in form.fields.filter(is_active=True)
    }


def _application_title(dynamic_form) -> str:
    title = dynamic_form.cleaned_data.get(APPLICATION_TITLE_KEY)
    if not isinstance(title, str) or not title.strip():
        raise ValidationError(
            {APPLICATION_TITLE_KEY: _("This field is required.")}
        )
    return title.strip()


def _write_answers(application, dynamic_form, fields) -> None:
    for key, field in fields.items():
        value = dynamic_form.cleaned_data.get(key)
        if value in (None, "", []):
            ApplicationAnswer.objects.filter(
                application=application,
                field=field,
            ).delete()
            continue
        ApplicationAnswer.objects.update_or_create(
            application=application,
            field=field,
            defaults={"value": _json_value(value)},
        )


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _check_attachment_policy(form: FormDefinition, total_count: int) -> None:
    policy = form.attachment_policy
    if policy == FormDefinition.AttachmentPolicy.NONE and total_count:
        raise ValidationError(_("This form does not accept attachments."))
    if policy == FormDefinition.AttachmentPolicy.REQUIRED and total_count == 0:
        raise ValidationError(
            _("At least one attachment is required for this form.")
        )


def _prepare_uploads(uploads, existing_count=0, existing_total=0):
    if existing_count + len(uploads) > MAX_ATTACHMENTS:
        raise ValidationError(
            _("At most %(limit)s files can be uploaded per application.")
            % {"limit": MAX_ATTACHMENTS}
        )

    prepared = []
    total = existing_total
    for upload in uploads:
        size = upload.size or 0
        if size > MAX_FILE_SIZE:
            raise ValidationError(_("Each file must be 2 MB or smaller."))
        total += size
        image_format = _verify_image(upload)
        prepared.append((upload, image_format, size))

    if total > MAX_TOTAL_SIZE:
        raise ValidationError(_("Total attachment size must be 10 MB or smaller."))

    return prepared


def _attachment_total(application: Application) -> int:
    return application.attachments.aggregate(total=Sum("size"))["total"] or 0


def _create_attachment(application, upload, image_format, size) -> Attachment:
    content_type, extension = ALLOWED_IMAGE_FORMATS[image_format]
    original_name = Path(upload.name).name
    upload.name = f"{uuid.uuid4().hex}{extension}"

    attachment = Attachment.objects.create(
        application=application,
        file=upload,
        original_name=original_name,
        content_type=content_type,
        size=size,
    )
    record(
        AuditEvent.Action.ATTACHMENT_ADDED,
        actor=application.applicant,
        application=application,
        form=application.form,
        code=application.code,
        name=original_name,
        size=size,
    )
    return attachment


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
        raise ValidationError(_("Upload a JPG or PNG image.")) from exc
    finally:
        upload.seek(0)

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(_("Upload a JPG or PNG image."))
    return image_format


def _send_confirmation(application: Application) -> None:
    send_mail(
        subject=_("Application received: %(code)s") % {"code": application.code},
        message=_(
            "Your %(category)s application has been received.\n\n"
            "Application code: %(code)s\n"
            "Year: %(year)s\n\n"
            "You can edit or delete your application until the deadline."
        )
        % {
            "category": application.category.name,
            "code": application.code,
            "year": application.year.year,
        },
        from_email=None,
        recipient_list=[application.applicant.email],
        fail_silently=False,
    )

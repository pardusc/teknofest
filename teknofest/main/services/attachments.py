"""Attachment rules, validation and quota helpers.

The default profile keeps the historical behaviour (JPEG/PNG images).
Forms using the ``webp_webm`` profile accept WebP images and WebM videos with
separate quotas.  All limits are enforced server-side; the UI counters are only
an informative preview of the same rules.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext as _
from PIL import Image

from ..models import Attachment, FormDefinition

MEGABYTE = 1024 * 1024

DEFAULT_MAX_FILES = 10
DEFAULT_MAX_IMAGE_SIZE = 2 * MEGABYTE
DEFAULT_MAX_TOTAL_SIZE = 10 * MEGABYTE

WEBP_MAX_FILES = 10
WEBP_MAX_VIDEOS = 2
WEBP_MAX_IMAGE_SIZE = 5 * MEGABYTE
WEBP_MAX_VIDEO_SIZE = 40 * MEGABYTE
WEBP_MAX_TOTAL_SIZE = 80 * MEGABYTE

# Reject decompression bombs before Pillow tries to decode a huge image.
MAX_IMAGE_PIXELS = 50_000_000

DEFAULT_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
}
WEBP_IMAGE_FORMATS = {
    "WEBP": ("image/webp", ".webp"),
}
WEBM_FORMAT = ("video/webm", ".webm")

WEBM_MAGIC = b"\x1a\x45\xdf\xa3"
WEBM_DOCTYPE_ID = b"\x42\x82"
WEBM_SEGMENT_ID = b"\x18\x53\x80\x67"


def _megabytes(value: int) -> str:
    if value % MEGABYTE == 0:
        return str(value // MEGABYTE)
    return f"{value / MEGABYTE:.1f}"


@dataclass(frozen=True)
class AttachmentRules:
    profile: str
    max_files: int
    max_videos: int
    max_image_size: int
    max_video_size: int
    max_total_size: int
    image_formats: dict[str, tuple[str, str]]
    allow_videos: bool

    @property
    def is_webp_webm(self) -> bool:
        return self.profile == FormDefinition.AttachmentProfile.WEBP_WEBM

    @property
    def accept_attribute(self) -> str:
        if self.is_webp_webm:
            return ".webp,.webm,image/webp,video/webm"
        return ".jpg,.jpeg,.png,image/jpeg,image/png"

    @property
    def image_size_mb(self) -> str:
        return _megabytes(self.max_image_size)

    @property
    def video_size_mb(self) -> str:
        return _megabytes(self.max_video_size)

    @property
    def total_size_mb(self) -> str:
        return _megabytes(self.max_total_size)

    @property
    def hint(self) -> str:
        if self.is_webp_webm:
            return _(
                "WebP image up to %(image)s MB, WebM video up to %(video)s MB. "
                "Max %(videos)s videos, %(files)s files and %(total)s MB total."
            ) % {
                "image": self.image_size_mb,
                "video": self.video_size_mb,
                "videos": self.max_videos,
                "files": self.max_files,
                "total": self.total_size_mb,
            }
        return _(
            "JPG or PNG · max %(image)s MB per file · max %(total)s MB total"
        ) % {
            "image": self.image_size_mb,
            "total": self.total_size_mb,
        }


@dataclass(frozen=True)
class AttachmentUsage:
    file_count: int
    image_count: int
    video_count: int
    total_size: int
    rules: AttachmentRules

    @property
    def remaining_files(self) -> int:
        return max(0, self.rules.max_files - self.file_count)

    @property
    def remaining_videos(self) -> int:
        return max(0, self.rules.max_videos - self.video_count)

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.rules.max_total_size - self.total_size)


@dataclass(frozen=True)
class PreparedUpload:
    upload: UploadedFile
    kind: str
    image_format: str | None
    content_type: str
    extension: str
    size: int


def rules_for(form: FormDefinition) -> AttachmentRules:
    if form.attachment_profile == FormDefinition.AttachmentProfile.WEBP_WEBM:
        return AttachmentRules(
            profile=FormDefinition.AttachmentProfile.WEBP_WEBM,
            max_files=WEBP_MAX_FILES,
            max_videos=WEBP_MAX_VIDEOS,
            max_image_size=WEBP_MAX_IMAGE_SIZE,
            max_video_size=WEBP_MAX_VIDEO_SIZE,
            max_total_size=WEBP_MAX_TOTAL_SIZE,
            image_formats=WEBP_IMAGE_FORMATS,
            allow_videos=True,
        )
    return AttachmentRules(
        profile=FormDefinition.AttachmentProfile.DEFAULT,
        max_files=DEFAULT_MAX_FILES,
        max_videos=0,
        max_image_size=DEFAULT_MAX_IMAGE_SIZE,
        max_video_size=0,
        max_total_size=DEFAULT_MAX_TOTAL_SIZE,
        image_formats=DEFAULT_IMAGE_FORMATS,
        allow_videos=False,
    )


def usage_for(
    form: FormDefinition,
    attachments: Iterable[Attachment] = (),
) -> AttachmentUsage:
    attachments = list(attachments)
    return AttachmentUsage(
        file_count=len(attachments),
        image_count=sum(1 for attachment in attachments if attachment.is_image),
        video_count=sum(1 for attachment in attachments if attachment.is_video),
        total_size=sum(attachment.size or 0 for attachment in attachments),
        rules=rules_for(form),
    )


def prepare_uploads(
    form: FormDefinition,
    uploads: Iterable[UploadedFile],
    existing_attachments: Iterable[Attachment] = (),
) -> list[PreparedUpload]:
    """Validate uploads against the form profile and return prepared files."""
    uploads = list(uploads)
    existing = list(existing_attachments)
    rules = rules_for(form)

    if len(existing) + len(uploads) > rules.max_files:
        raise ValidationError(
            _("At most %(limit)s files can be uploaded per application.")
            % {"limit": rules.max_files}
        )

    existing_size = sum(attachment.size or 0 for attachment in existing)
    requested_size = sum(upload.size or 0 for upload in uploads)
    if existing_size + requested_size > rules.max_total_size:
        if rules.is_webp_webm:
            raise ValidationError(
                _("Total attachment size must be %(limit)s MB or smaller.")
                % {"limit": rules.total_size_mb}
            )
        raise ValidationError(_("Total attachment size must be 10 MB or smaller."))

    prepared: list[PreparedUpload] = []
    for upload in uploads:
        prepared.append(_prepare_upload(upload, rules))

    new_videos = sum(1 for item in prepared if item.kind == "video")
    existing_videos = sum(1 for attachment in existing if attachment.is_video)
    if rules.max_videos and existing_videos + new_videos > rules.max_videos:
        raise ValidationError(
            _("At most %(limit)s videos can be uploaded per application.")
            % {"limit": rules.max_videos}
        )

    return prepared

    return prepared


def _prepare_upload(upload: UploadedFile, rules: AttachmentRules) -> PreparedUpload:
    size = upload.size or 0
    looks_like_video = _looks_like_video(upload)

    if looks_like_video:
        if not rules.allow_videos:
            raise ValidationError(_("This form does not accept video attachments."))
        if size > rules.max_video_size:
            raise ValidationError(
                _("Each video must be %(limit)s MB or smaller.")
                % {"limit": rules.video_size_mb}
            )
        _verify_webm(upload)
        content_type, extension = WEBM_FORMAT
        return PreparedUpload(
            upload=upload,
            kind="video",
            image_format=None,
            content_type=content_type,
            extension=extension,
            size=size,
        )

    if size > rules.max_image_size:
        if rules.is_webp_webm:
            raise ValidationError(
                _("Each image must be %(limit)s MB or smaller.")
                % {"limit": rules.image_size_mb}
            )
        raise ValidationError(_("Each file must be 2 MB or smaller."))

    image_format = _verify_image(upload, rules)
    content_type, extension = rules.image_formats[image_format]
    return PreparedUpload(
        upload=upload,
        kind="image",
        image_format=image_format,
        content_type=content_type,
        extension=extension,
        size=size,
    )


def _looks_like_video(upload: UploadedFile) -> bool:
    name = (upload.name or "").lower()
    content_type = (getattr(upload, "content_type", "") or "").lower()
    return content_type.startswith("video/") or name.endswith(
        (".webm", ".mp4", ".mov", ".mkv", ".avi")
    )


def _verify_webm(upload: UploadedFile) -> None:
    try:
        header = upload.read(65536)
    finally:
        upload.seek(0)

    try:
        element_id, offset = _read_ebml_vint(header, 0, is_id=True)
        if element_id != WEBM_MAGIC:
            raise ValueError

        header_size, offset = _read_ebml_vint(header, offset)
        header_end = min(len(header), offset + header_size)
        doc_type = None

        while offset < header_end:
            child_id, offset = _read_ebml_vint(header, offset, is_id=True)
            child_size, offset = _read_ebml_vint(header, offset)
            if child_size > len(header) - offset:
                raise ValueError
            if child_id == WEBM_DOCTYPE_ID:
                doc_type = header[offset:offset + child_size]
                break
            offset += child_size

        if doc_type != b"webm" or WEBM_SEGMENT_ID not in header:
            raise ValueError
    except (IndexError, ValueError) as exc:
        raise ValidationError(_("Upload a WebM video.")) from exc


def _read_ebml_vint(data, offset, *, is_id=False):
    """Read one EBML variable-length integer from ``data``.

    Element IDs keep their marker bit (the returned value is the raw ID);
    sizes mask it out.
    """
    if offset >= len(data):
        raise ValueError

    first = data[offset]
    if first == 0:
        raise ValueError

    length = 1
    mask = 0x80
    while not first & mask:
        mask >>= 1
        length += 1
        if length > 8:
            raise ValueError

    if offset + length > len(data):
        raise ValueError

    if is_id:
        return data[offset:offset + length], offset + length

    value = first & (mask - 1)
    for byte in data[offset + 1:offset + length]:
        value = (value << 8) | byte
    return value, offset + length


def _verify_image(upload: UploadedFile, rules: AttachmentRules) -> str:
    error_message = (
        _("Upload a WebP image.")
        if rules.is_webp_webm
        else _("Upload a JPG or PNG image.")
    )
    try:
        image = Image.open(upload)
        image_format = image.format
        width, height = image.size
        image.verify()
    except Exception as exc:
        raise ValidationError(error_message) from exc
    finally:
        upload.seek(0)

    if (width or 0) * (height or 0) > MAX_IMAGE_PIXELS:
        raise ValidationError(_("The image dimensions are too large."))

    if image_format not in rules.image_formats:
        raise ValidationError(error_message)
    return image_format


def attachment_filename(upload: UploadedFile) -> str:
    """Return a sanitised original filename that fits the model field."""
    return Path(upload.name or "file").name[:255]

from PIL import Image
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG"}


def validate_image_upload(upload):
    """Reject files whose real image format is not JPEG or PNG."""
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

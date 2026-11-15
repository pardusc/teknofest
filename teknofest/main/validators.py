from PIL import Image
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG"}

APPLICATION_TITLE_KEY = "title"
APPLICATION_TITLE_MAX_LENGTH = 100
APPLICATION_TITLE_MIN_LENGTH = 3
_TITLE_TURKISH_LETTERS = set("ÇĞİÖŞÜçğıöşüÂâÎîÛû")
_TITLE_PUNCTUATION = set(" .,;:!?'\"()[]{}&+-/_#%@")


def validate_application_title(value):
    """Validate the user-provided application title strictly.

    Only Turkish/Latin letters, ASCII digits, single spaces and a small set of
    punctuation marks are accepted. This rejects homoglyphs, zero-width and
    bidirectional control characters, emoji and other ambiguous input.
    """
    if value is None:
        return

    value = str(value)
    if value != value.strip():
        raise ValidationError(
            _("Remove spaces from the beginning and end of the title.")
        )

    invalid = sorted(
        {
            character
            for character in value
            if character not in _TITLE_TURKISH_LETTERS
            and not (
                character.isascii()
                and (character.isalnum() or character in _TITLE_PUNCTUATION)
            )
        }
    )
    if invalid:
        raise ValidationError(
            _(
                "Use only Turkish/Latin letters, digits, spaces and basic "
                "punctuation. Ambiguous or special characters are not allowed."
            )
        )

    if not any(character.isalpha() for character in value):
        raise ValidationError(
            _("The title must contain at least one letter.")
        )


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

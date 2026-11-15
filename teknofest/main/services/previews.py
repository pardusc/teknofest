"""Thumbnail generation for protected attachment previews."""

import os
import tempfile
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageOps

THUMBNAIL_SIZE = (640, 480)
THUMBNAIL_QUALITY = 82


def thumbnail_path(attachment) -> Path:
    """Deterministic cache path for one attachment thumbnail."""
    return (
        Path(settings.MEDIA_ROOT)
        / "thumbnails"
        / str(attachment.application_id)
        / f"{attachment.pk}.webp"
    )


def get_or_create_thumbnail(attachment) -> Path:
    """Return the cached WebP thumbnail, generating it on first use."""
    if not attachment.is_image:
        raise ValueError("Only image attachments can have thumbnails.")

    source = Path(attachment.file.path)
    destination = thumbnail_path(attachment)

    if destination.exists():
        try:
            if destination.stat().st_mtime >= source.stat().st_mtime:
                return destination
        except OSError:
            pass

    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.seek(0)
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        handle, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            suffix=".webp",
        )
        os.close(handle)
        try:
            image.save(
                temporary_name,
                format="WEBP",
                quality=THUMBNAIL_QUALITY,
                method=4,
            )
            os.replace(temporary_name, destination)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    return destination


def delete_thumbnail(attachment) -> None:
    """Remove the cached thumbnail for an attachment, if present."""
    path = thumbnail_path(attachment)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return

    # Remove the per-application directory when it becomes empty.
    try:
        path.parent.rmdir()
    except OSError:
        pass

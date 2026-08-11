"""Upload validation -- steps 1 and 2 of the ingestion pipeline.

Format is decided by **magic bytes**, never by the client-supplied filename or
Content-Type. Both are attacker-controlled and, more mundanely, both are routinely
wrong: browsers mislabel HEIC, and mobile clients frequently send
``application/octet-stream`` for everything.

Sprint 1 scope: format sniffing and size limits, which need no image decoder.
Dimension checks, decode verification and EXIF handling arrive in Phase 2 with
Pillow, and their hooks are marked below.
"""

from __future__ import annotations

from biovision.config import Settings
from biovision.errors import (
    AnimatedImageError,
    FileTooLargeError,
    UnsupportedMediaTypeError,
)
from biovision.pipeline.types import PreparedImage
from biovision.schemas.enums import ImageFormat

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GIF_MAGICS = (b"GIF87a", b"GIF89a")

#: ISO-BMFF brands that indicate HEIF/HEIC still images.
_HEIF_BRANDS = frozenset(
    {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevm", b"hevs", b"mif1", b"msf1"}
)

#: Smallest input that could carry an identifiable magic number.
_MIN_SNIFF_BYTES = 16


def sniff_format(data: bytes) -> ImageFormat | None:
    """Identify the container from its leading bytes, or ``None`` if unrecognised."""
    if len(data) < _MIN_SNIFF_BYTES:
        return None

    if data.startswith(_JPEG_MAGIC):
        return ImageFormat.JPEG
    if data.startswith(_PNG_MAGIC):
        return ImageFormat.PNG
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ImageFormat.WEBP
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return ImageFormat.HEIC
    return None


def is_animated(data: bytes, image_format: ImageFormat) -> bool:
    """Cheap animation detection, without decoding.

    WebP: an ``ANIM`` chunk in the RIFF header.
    GIF: never reaches here -- GIF is not an accepted format at all.

    Phase 2 replaces this with Pillow's ``n_frames``, which is authoritative. Until
    then this catches the common case, and a false negative merely means a single
    frame gets analysed rather than something unsafe happening.
    """
    if image_format is ImageFormat.WEBP:
        return b"ANIM" in data[:1024]
    return False


def validate_upload(data: bytes, settings: Settings) -> PreparedImage:
    """Run the format and size gates and return a :class:`PreparedImage`.

    Raises the documented errors: 413 for oversize, 415 for an unsupported or
    animated container.
    """
    size = len(data)
    if size == 0:
        raise UnsupportedMediaTypeError("The uploaded file is empty.")
    if size > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / 1_048_576
        raise FileTooLargeError(
            f"Image is {size / 1_048_576:.1f} MB; the limit is {limit_mb:.0f} MB."
        )

    image_format = sniff_format(data)
    if image_format is None:
        if any(data.startswith(magic) for magic in _GIF_MAGICS):
            raise UnsupportedMediaTypeError(
                "GIF is not supported. Upload a JPEG, PNG, WebP or HEIC photograph."
            )
        raise UnsupportedMediaTypeError(
            "Unrecognised image format. Supported formats: JPEG, PNG, WebP, HEIC."
        )

    if is_animated(data, image_format):
        raise AnimatedImageError(
            "Animated images are not supported. Upload a still photograph."
        )

    # Phase 2 continues here: decode, apply EXIF orientation, check
    # min_image_dimension, compute the pHash, redact faces and plates, strip EXIF
    # and resize. Those steps populate the width/height/phash/integrity/privacy
    # fields left at their defaults below.
    return PreparedImage(data=data, image_format=image_format, byte_size=size)

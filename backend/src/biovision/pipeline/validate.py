"""Upload validation -- steps 1, 2 and the decode gate of the ingestion pipeline.

Format is decided by **magic bytes**, never by the client-supplied filename or
Content-Type. Both are attacker-controlled and, more mundanely, both are routinely
wrong: browsers mislabel HEIC, and mobile clients frequently send
``application/octet-stream`` for everything.

Decoding is itself a check. A file can carry a valid JPEG header and be truncated
three bytes later, and the only reliable way to find out is to decode it -- so the
pipeline decodes once, here, and passes the result on rather than handing raw bytes
to a model that will fail more obscurely.
"""

from __future__ import annotations

import io
import logging

import pillow_heif
from PIL import Image, UnidentifiedImageError

from biovision.config import Settings
from biovision.errors import (
    AnimatedImageError,
    CorruptImageError,
    FileTooLargeError,
    ImageTooSmallError,
    UnsupportedMediaTypeError,
)
from biovision.schemas.enums import ImageFormat

logger = logging.getLogger(__name__)

# Teaches Pillow to open HEIF/HEIC. Registered at import so every decode path in
# the process gets it, including the test fixtures.
pillow_heif.register_heif_opener()

# Decompression-bomb ceiling. Pillow's default is 89 megapixels; the upload limit is
# 10 MB, and a highly compressed image well inside that limit can still decode to
# something that exhausts memory on an 8 GB box. 80 MP is comfortably above any real
# phone camera (a 48 MP sensor produces ~48 MP) and far below dangerous.
Image.MAX_IMAGE_PIXELS = 80_000_000

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


def is_animated(image: Image.Image) -> bool:
    """Whether the decoded image carries more than one frame.

    Reads ``n_frames`` from the decoder rather than scanning for an ``ANIM`` chunk:
    the decoder is authoritative, and the byte-level heuristic this replaces could
    be fooled by the string appearing in metadata.
    """
    return getattr(image, "n_frames", 1) > 1


def validate_and_decode(data: bytes, settings: Settings) -> tuple[Image.Image, ImageFormat]:
    """Run every input gate and return the decoded image.

    Raises:
        FileTooLargeError: 413, oversize upload.
        UnsupportedMediaTypeError: 415, unrecognised container.
        AnimatedImageError: 415, more than one frame.
        CorruptImageError: 422, undecodable bytes.
        ImageTooSmallError: 422, below the minimum dimension.
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

    image = _decode(data)

    if is_animated(image):
        # 415 rather than 422: the problem is the container, not the content.
        # Silently analysing frame one would be picking for the user.
        raise AnimatedImageError(
            "Animated images are not supported. Upload a still photograph."
        )

    width, height = image.size
    if min(width, height) < settings.min_image_dimension:
        raise ImageTooSmallError(
            f"Image is {width}x{height}px; the shorter side must be at least "
            f"{settings.min_image_dimension}px for the analysis to be meaningful."
        )

    return image, image_format


def _decode(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        # `open` is lazy -- it parses the header and stops. `load` is what actually
        # decodes the pixels, and therefore what catches truncation.
        image.load()
    except UnidentifiedImageError as exc:
        raise UnsupportedMediaTypeError(
            "The file could not be identified as an image."
        ) from exc
    except Image.DecompressionBombError as exc:
        raise CorruptImageError(
            "The image decodes to an implausible number of pixels and was rejected."
        ) from exc
    except Exception as exc:
        logger.info("decode failed: %s", exc)
        raise CorruptImageError(
            "The image could not be decoded. It may be truncated or corrupt."
        ) from exc
    return image

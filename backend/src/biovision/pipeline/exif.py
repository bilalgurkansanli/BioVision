"""EXIF handling -- steps 3, 4 and part of 7 of the ingestion pipeline.

Three separate jobs, deliberately kept apart:

* **read** the fields that support integrity triage;
* **apply** the orientation tag, before any model sees the image;
* **strip** everything on the way out.

Order matters. Reading has to happen before stripping, and rotating has to happen
before inference -- a model handed a sideways photograph is being asked a different
question than the user asked.
"""

from __future__ import annotations

import logging
from datetime import datetime

from PIL import Image, ImageOps

from biovision.schemas.analyze import Integrity

logger = logging.getLogger(__name__)

# Baseline TIFF tags.
_TAG_MAKE = 0x010F
_TAG_MODEL = 0x0110
# Pointers into the sub-IFDs that hold the interesting fields.
_TAG_EXIF_IFD = 0x8769
_TAG_GPS_IFD = 0x8825
# Inside the Exif IFD.
_TAG_DATETIME_ORIGINAL = 0x9003
_TAG_DATETIME_DIGITIZED = 0x9004

#: EXIF stores timestamps as "YYYY:MM:DD HH:MM:SS", which is not ISO 8601.
_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"


def read_exif(image: Image.Image) -> Integrity:
    """Extract the integrity-relevant EXIF fields.

    GPS is reported as a **presence boolean only**. Whether a photograph carries
    location data is what matters for triage; the coordinates themselves would be a
    privacy liability with no analytical payoff, so they are never read into memory
    beyond checking that the IFD exists.

    Never raises: a photograph with unreadable metadata is still a photograph, and
    losing the analysis over a malformed tag would be the wrong trade.
    """
    try:
        exif = image.getexif()
    except Exception:
        logger.debug("EXIF block unreadable; continuing without metadata", exc_info=True)
        return Integrity()

    if not exif:
        return Integrity()

    return Integrity(
        exif_datetime=_read_datetime(exif),
        exif_gps_present=_has_gps(exif),
        device=_read_device(exif),
    )


def apply_orientation(image: Image.Image) -> Image.Image:
    """Rotate the image to its EXIF orientation and drop the tag.

    Phones record orientation as metadata rather than rotating the pixels. A model
    that reads the raw buffer sees a sideways car; worse, the bounding boxes it
    returns would be expressed in a coordinate frame the user never saw.

    ``exif_transpose`` also removes the orientation tag, which prevents a viewer
    downstream from applying the rotation a second time.
    """
    try:
        return ImageOps.exif_transpose(image) or image
    except Exception:
        logger.warning("could not apply EXIF orientation; using the image as-is", exc_info=True)
        return image


# There is no `strip_metadata` here on purpose. Stripping is structural in this
# pipeline: `ingest` rebuilds the stored image from a numpy array, so there is no
# metadata to carry forward, and `encode_jpeg` is never handed an `exif` argument.
# A second mechanism that deletes known keys would only invite the question of which
# one is authoritative -- and would miss whatever key nobody thought of.


def _read_datetime(exif: Image.Exif) -> datetime | None:
    ifd = _sub_ifd(exif, _TAG_EXIF_IFD)
    raw = ifd.get(_TAG_DATETIME_ORIGINAL) or ifd.get(_TAG_DATETIME_DIGITIZED)
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw.strip(), _EXIF_DATETIME_FORMAT)
    except ValueError:
        logger.debug("unparseable EXIF timestamp: %r", raw)
        return None


def _has_gps(exif: Image.Exif) -> bool:
    if _TAG_GPS_IFD not in exif:
        return False
    # The tag can be present but point at an empty IFD, which is not evidence of
    # anything. Only a populated block counts.
    return bool(_sub_ifd(exif, _TAG_GPS_IFD))


def _read_device(exif: Image.Exif) -> str | None:
    make = _clean(exif.get(_TAG_MAKE))
    model = _clean(exif.get(_TAG_MODEL))

    if make and model:
        # Manufacturers frequently repeat the make inside the model ("Apple"
        # / "Apple iPhone 14"), which would otherwise read as "Apple Apple iPhone 14".
        if model.lower().startswith(make.lower()):
            return model
        return f"{make} {model}"
    return model or make


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip().strip("\x00").strip()
    return stripped or None


def _sub_ifd(exif: Image.Exif, tag: int) -> dict[int, object]:
    try:
        return dict(exif.get_ifd(tag))
    except Exception:
        return {}

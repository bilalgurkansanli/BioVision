"""The ingestion pipeline end to end.

The individual stages have their own tests. What is checked here is that they run,
in the right order, and that the invariants the privacy claims rest on hold for the
artefact that actually reaches storage.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import numpy as np
import pytest
from PIL import Image

from biovision.config import Settings
from biovision.errors import ImageTooSmallError, UnsupportedMediaTypeError
from biovision.pipeline.ingest import prepare_image
from biovision.pipeline.phash import hamming_distance
from biovision.pipeline.redact import Redactor
from biovision.schemas.enums import ImageFormat
from tests.conftest import (
    FixedDetector,
    make_heic,
    make_image,
    make_jpeg,
    make_jpeg_with_exif,
    make_png,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _prepare(payload: bytes, settings: Settings, redactor: Redactor | None = None):  # type: ignore[no-untyped-def]
    return prepare_image(payload, settings=settings, redactor=redactor or Redactor())


# ---------------------------------------------------------------------------
# The stored derivative
# ---------------------------------------------------------------------------


def test_the_stored_derivative_carries_no_exif(settings: Settings) -> None:
    """The load-bearing privacy assertion: metadata does not reach storage."""
    payload = make_jpeg_with_exif(
        datetime_original="2026:03:14 10:22:00",
        make="Apple",
        model="iPhone 14",
        gps=True,
    )

    prepared = _prepare(payload, settings)
    stored = Image.open(io.BytesIO(prepared.stored_bytes))

    assert not dict(stored.getexif()), "EXIF survived into the stored image"
    assert "icc_profile" not in stored.info
    # ...while the integrity record still holds what was read before stripping.
    assert prepared.integrity.device == "Apple iPhone 14"
    assert prepared.integrity.exif_gps_present is True


def test_the_original_bytes_are_not_carried_forward(settings: Settings) -> None:
    """`PreparedImage` has nowhere to put the raw upload, by construction."""
    payload = make_jpeg(seed=3)
    prepared = _prepare(payload, settings)

    assert prepared.stored_bytes != payload
    assert not hasattr(prepared, "data")
    assert not hasattr(prepared, "raw")


def test_the_stored_derivative_is_bounded(settings: Settings) -> None:
    settings.stored_long_edge = 1280
    prepared = _prepare(make_png(size=(3000, 2000)), settings)

    assert max(prepared.width, prepared.height) == 1280
    assert prepared.pixels.shape == (prepared.height, prepared.width, 3)


def test_stored_bytes_and_pixels_describe_the_same_image(settings: Settings) -> None:
    """Bounding boxes are expressed in this frame, so the two must not diverge."""
    prepared = _prepare(make_png(size=(2000, 1500)), settings)
    stored = Image.open(io.BytesIO(prepared.stored_bytes))

    assert stored.size == (prepared.width, prepared.height)


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_orientation_is_applied_before_anything_else_sees_the_pixels(
    settings: Settings,
) -> None:
    """A model handed the raw buffer would see a sideways photograph."""
    prepared = _prepare(make_jpeg_with_exif(size=(640, 480), orientation=6), settings)

    assert (prepared.width, prepared.height) == (480, 640)


def test_the_hash_is_taken_before_redaction(settings: Settings) -> None:
    """Otherwise the fingerprint would depend on how many faces were found, and the
    same photograph could hash differently on a second submission."""
    payload = make_png(seed=21)

    without = _prepare(payload, settings)
    with_redaction = _prepare(
        payload, settings, Redactor(face_detector=FixedDetector("d", [(50, 50, 200, 200)]))
    )

    assert with_redaction.privacy.faces_blurred == 1
    assert with_redaction.phash == without.phash


def test_redaction_reaches_the_stored_bytes(settings: Settings) -> None:
    payload = make_png(seed=22)
    box = (100, 80, 200, 200)

    clean = _prepare(payload, settings)
    redacted = _prepare(payload, settings, Redactor(face_detector=FixedDetector("d", [box])))

    assert not np.array_equal(clean.pixels, redacted.pixels)
    assert redacted.privacy.faces_blurred == 1
    assert redacted.privacy.face_detector == "d"


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "expected"),
    [
        (make_png, ImageFormat.PNG),
        (make_jpeg, ImageFormat.JPEG),
        (make_heic, ImageFormat.HEIC),
    ],
)
def test_every_accepted_format_normalises_to_jpeg_pixels(
    factory: Callable[[], bytes], expected: ImageFormat, settings: Settings
) -> None:
    prepared = _prepare(factory(), settings)

    assert prepared.image_format is expected, "the original container is recorded"
    assert prepared.stored_bytes.startswith(b"\xff\xd8\xff"), "storage is always JPEG"
    assert prepared.pixels.dtype == np.uint8


def test_an_iphone_heic_photo_round_trips(settings: Settings) -> None:
    prepared = _prepare(make_heic(size=(1200, 900)), settings)

    assert prepared.image_format is ImageFormat.HEIC
    assert prepared.width == 1200
    assert len(prepared.phash) == 16


# ---------------------------------------------------------------------------
# Reported values
# ---------------------------------------------------------------------------


def test_byte_size_reports_the_original_upload(settings: Settings) -> None:
    payload = make_png(size=(1500, 1200))
    prepared = _prepare(payload, settings)

    assert prepared.byte_size == len(payload)
    assert prepared.byte_size != len(prepared.stored_bytes)


def test_the_same_photo_ingested_twice_hashes_the_same(settings: Settings) -> None:
    """The property the pHash cache and duplicate detection both depend on."""
    payload = make_jpeg(seed=31)

    assert _prepare(payload, settings).phash == _prepare(payload, settings).phash


def test_the_same_photo_at_different_qualities_still_matches(settings: Settings) -> None:
    image = make_image(seed=32)
    buffers = []
    for quality in (95, 60):
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality)
        buffers.append(buffer.getvalue())

    first, second = (_prepare(payload, settings).phash for payload in buffers)

    assert hamming_distance(first, second) <= 5


def test_different_photos_do_not_collide(settings: Settings) -> None:
    first = _prepare(make_png(seed=41), settings)
    second = _prepare(make_png(seed=42), settings)

    assert hamming_distance(first.phash, second.phash) >= 10


def test_pixel_area_matches_the_dimensions(settings: Settings) -> None:
    prepared = _prepare(make_png(size=(800, 600)), settings)

    assert prepared.pixel_area == prepared.width * prepared.height


# ---------------------------------------------------------------------------
# Rejections propagate
# ---------------------------------------------------------------------------


def test_rejections_reach_the_caller(settings: Settings) -> None:
    with pytest.raises(ImageTooSmallError):
        _prepare(make_png(size=(100, 100)), settings)

    with pytest.raises(UnsupportedMediaTypeError):
        _prepare(b"not an image at all, not even slightly", settings)

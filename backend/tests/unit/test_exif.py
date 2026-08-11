"""EXIF reading and orientation."""

from __future__ import annotations

import io
from datetime import datetime

import numpy as np
from PIL import Image

from biovision.pipeline.exif import apply_orientation, read_exif
from tests.conftest import make_image, make_jpeg, make_jpeg_with_exif


def _open(payload: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(payload))
    image.load()
    return image


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def test_reads_capture_time_device_and_gps_presence() -> None:
    payload = make_jpeg_with_exif(
        datetime_original="2026:03:14 10:22:00",
        make="Apple",
        model="iPhone 14",
        gps=True,
    )

    integrity = read_exif(_open(payload))

    assert integrity.exif_datetime == datetime(2026, 3, 14, 10, 22, 0)
    # Make and Model are joined: EXIF stores "Apple" / "iPhone 14" separately, and
    # the manufacturer is part of identifying the device.
    assert integrity.device == "Apple iPhone 14"
    assert integrity.exif_gps_present is True


def test_gps_coordinates_are_never_read_into_the_result() -> None:
    """Presence is the integrity signal; coordinates would be a liability."""
    integrity = read_exif(_open(make_jpeg_with_exif(gps=True)))

    assert integrity.exif_gps_present is True
    # The model has no field that could hold them, and that is the point.
    assert "latitude" not in integrity.model_dump()
    assert "longitude" not in integrity.model_dump()


def test_a_photo_without_exif_yields_empty_integrity() -> None:
    integrity = read_exif(_open(make_jpeg()))

    assert integrity.exif_datetime is None
    assert integrity.exif_gps_present is False
    assert integrity.device is None
    assert integrity.duplicate_of is None


def test_make_is_not_repeated_when_the_model_already_contains_it() -> None:
    """Manufacturers write "Apple" / "Apple iPhone 14"; naive joining reads badly."""
    repeated = read_exif(_open(make_jpeg_with_exif(make="Apple", model="Apple iPhone 14")))
    assert repeated.device == "Apple iPhone 14"

    distinct = read_exif(_open(make_jpeg_with_exif(make="samsung", model="SM-S911B")))
    assert distinct.device == "samsung SM-S911B"


def test_either_make_or_model_alone_still_yields_a_device() -> None:
    assert read_exif(_open(make_jpeg_with_exif(model="Pixel 8"))).device == "Pixel 8"
    assert read_exif(_open(make_jpeg_with_exif(make="Canon"))).device == "Canon"


def test_an_unparseable_timestamp_does_not_fail_the_request() -> None:
    """Losing the analysis over a malformed tag would be the wrong trade."""
    integrity = read_exif(_open(make_jpeg_with_exif(datetime_original="not a timestamp")))

    assert integrity.exif_datetime is None


def test_exif_timestamps_are_not_iso8601() -> None:
    """EXIF uses colons in the date; parsing it as ISO would silently fail."""
    integrity = read_exif(_open(make_jpeg_with_exif(datetime_original="2026:12:31 23:59:59")))

    assert integrity.exif_datetime == datetime(2026, 12, 31, 23, 59, 59)


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------


def test_orientation_6_swaps_the_axes() -> None:
    """Orientation 6 means "rotate 90 degrees" -- a portrait photo stored landscape."""
    payload = make_jpeg_with_exif(size=(640, 480), orientation=6)
    image = _open(payload)
    assert image.size == (640, 480), "stored buffer is landscape"

    rotated = apply_orientation(image)

    assert rotated.size == (480, 640), "the model must see the photo upright"


def test_orientation_1_is_a_no_op() -> None:
    image = _open(make_jpeg_with_exif(size=(640, 480), orientation=1))

    assert apply_orientation(image).size == (640, 480)


def test_the_orientation_tag_is_removed_after_rotating() -> None:
    """Otherwise a downstream viewer applies the rotation a second time."""
    rotated = apply_orientation(_open(make_jpeg_with_exif(orientation=6)))

    assert rotated.getexif().get(0x0112) in (None, 1)


def test_rotation_actually_moves_pixels() -> None:
    """Size alone would pass for a square image; check the content moved."""
    original = make_image((400, 400), seed=3)
    buffer = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6
    original.save(buffer, format="JPEG", quality=95, exif=exif)

    rotated = apply_orientation(_open(buffer.getvalue()))

    assert rotated.size == (400, 400)
    assert not np.array_equal(np.asarray(rotated.convert("RGB")), np.asarray(original))


def test_a_photo_without_an_orientation_tag_is_untouched() -> None:
    image = _open(make_jpeg(size=(640, 480)))

    assert apply_orientation(image).size == (640, 480)

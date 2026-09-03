"""Upload validation: format sniffing, size limits, and the decode gate."""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from PIL import Image

from biovision.config import Settings
from biovision.errors import (
    AnimatedImageError,
    CorruptImageError,
    FileTooLargeError,
    ImageTooSmallError,
    UnsupportedMediaTypeError,
)
from biovision.pipeline.validate import is_animated, sniff_format, validate_and_decode
from biovision.schemas.enums import ImageFormat
from tests.conftest import (
    make_animated_gif,
    make_animated_webp,
    make_gif,
    make_heic,
    make_jpeg,
    make_png,
    make_truncated_jpeg,
    make_webp,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Format identification
# ---------------------------------------------------------------------------


# Factories rather than bytes: a parametrised payload becomes part of the test id,
# and a 40 KB JPEG in a test id is unreadable and breaks the runner's id handling.
@pytest.mark.parametrize(
    ("factory", "expected"),
    [
        (make_png, ImageFormat.PNG),
        (make_jpeg, ImageFormat.JPEG),
        (make_webp, ImageFormat.WEBP),
        (make_heic, ImageFormat.HEIC),
    ],
)
def test_recognises_supported_formats(factory: Callable[[], bytes], expected: ImageFormat) -> None:
    assert sniff_format(factory()) is expected


@pytest.mark.parametrize(
    ("label", "factory"),
    [
        ("empty", bytes),
        ("too-short", lambda: b"short"),
        ("gif", make_gif),
        ("pdf", lambda: b"%PDF-1.7 not an image at all here"),
        ("zeros", lambda: b"\x00" * 64),
    ],
)
def test_unknown_containers_are_not_recognised(label: str, factory: Callable[[], bytes]) -> None:
    assert sniff_format(factory()) is None


def test_format_comes_from_bytes_not_from_the_filename(settings: Settings) -> None:
    """Filenames and Content-Type are client-controlled and routinely wrong."""
    _, image_format = validate_and_decode(make_jpeg(), settings)
    assert image_format is ImageFormat.JPEG


# ---------------------------------------------------------------------------
# HEIC -- the iPhone path
# ---------------------------------------------------------------------------


def test_heic_decodes(settings: Settings) -> None:
    """iPhones produce HEIC by default; rejecting it would exclude most uploads."""
    image, image_format = validate_and_decode(make_heic(), settings)

    assert image_format is ImageFormat.HEIC
    assert image.size == (640, 480)
    assert image.convert("RGB").getpixel((0, 0)) is not None


# ---------------------------------------------------------------------------
# Animation
# ---------------------------------------------------------------------------


def test_animation_is_detected_from_the_decoder() -> None:
    """`n_frames` from the decoder, not a byte-level guess at the container."""
    animated = Image.open(io.BytesIO(make_animated_webp()))
    still = Image.open(io.BytesIO(make_png()))

    assert is_animated(animated) is True
    assert is_animated(still) is False


def test_animated_webp_is_rejected(settings: Settings) -> None:
    with pytest.raises(AnimatedImageError):
        validate_and_decode(make_animated_webp(), settings)


def test_animated_gif_is_rejected_as_gif(settings: Settings) -> None:
    """GIF never reaches the animation check -- the container is unsupported first."""
    with pytest.raises(UnsupportedMediaTypeError, match="GIF"):
        validate_and_decode(make_animated_gif(), settings)


# ---------------------------------------------------------------------------
# Size and dimensions
# ---------------------------------------------------------------------------


def test_empty_upload_is_rejected(settings: Settings) -> None:
    with pytest.raises(UnsupportedMediaTypeError, match="empty"):
        validate_and_decode(b"", settings)


def test_oversize_upload_is_rejected(settings: Settings) -> None:
    settings.max_upload_bytes = 1024
    with pytest.raises(FileTooLargeError, match="limit"):
        validate_and_decode(make_png(), settings)


def test_images_below_the_minimum_dimension_are_rejected(settings: Settings) -> None:
    """A 150px photo cannot support a claim about a scratch."""
    tiny = make_png(size=(150, 150))

    with pytest.raises(ImageTooSmallError, match="150x150"):
        validate_and_decode(tiny, settings)


def test_the_shorter_side_is_what_counts(settings: Settings) -> None:
    """A wide, short strip is as unusable as a small square."""
    with pytest.raises(ImageTooSmallError):
        validate_and_decode(make_png(size=(2000, 100)), settings)


def test_exactly_at_the_minimum_is_accepted(settings: Settings) -> None:
    image, _ = validate_and_decode(make_png(size=(200, 200)), settings)
    assert image.size == (200, 200)


# ---------------------------------------------------------------------------
# Corruption
# ---------------------------------------------------------------------------


def test_a_truncated_file_is_caught_by_decoding(settings: Settings) -> None:
    """The header is valid; only decoding the pixels reveals the truncation."""
    payload = make_truncated_jpeg()
    assert sniff_format(payload) is ImageFormat.JPEG  # the sniffer is fooled

    with pytest.raises(CorruptImageError):
        validate_and_decode(payload, settings)


def test_garbage_with_a_valid_magic_number_is_rejected(settings: Settings) -> None:
    with pytest.raises((CorruptImageError, UnsupportedMediaTypeError)):
        validate_and_decode(b"\x89PNG\r\n\x1a\n" + b"\xff" * 512, settings)

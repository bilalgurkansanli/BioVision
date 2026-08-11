"""Upload validation: format sniffing and size limits."""

from __future__ import annotations

import pytest

from biovision.config import Settings
from biovision.errors import AnimatedImageError, FileTooLargeError, UnsupportedMediaTypeError
from biovision.pipeline.validate import is_animated, sniff_format, validate_upload
from biovision.schemas.enums import ImageFormat
from tests.conftest import make_animated_webp, make_gif, make_jpeg, make_png


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_recognises_supported_formats() -> None:
    assert sniff_format(make_png()) is ImageFormat.PNG
    assert sniff_format(make_jpeg()) is ImageFormat.JPEG

    webp = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8 " + b"\x00" * 16
    assert sniff_format(webp) is ImageFormat.WEBP

    # HEIC: an ISO-BMFF box whose brand marks it as a HEIF still image. Included
    # because iPhones produce it by default.
    heic = b"\x00\x00\x00\x18" + b"ftyp" + b"heic" + b"\x00" * 16
    assert sniff_format(heic) is ImageFormat.HEIC


@pytest.mark.parametrize(
    "payload",
    [b"", b"short", make_gif(), b"%PDF-1.7 not an image at all here", b"\x00" * 64],
)
def test_unknown_containers_are_not_recognised(payload: bytes) -> None:
    assert sniff_format(payload) is None


def test_format_comes_from_bytes_not_from_the_filename(settings: Settings) -> None:
    """Filenames and Content-Type are client-controlled and routinely wrong."""
    prepared = validate_upload(make_jpeg(), settings)
    assert prepared.image_format is ImageFormat.JPEG


def test_animated_webp_is_detected() -> None:
    assert is_animated(make_animated_webp(), ImageFormat.WEBP) is True
    assert is_animated(make_png(), ImageFormat.PNG) is False


def test_animated_uploads_are_rejected(settings: Settings) -> None:
    with pytest.raises(AnimatedImageError):
        validate_upload(make_animated_webp(), settings)


def test_gif_is_rejected_with_a_useful_message(settings: Settings) -> None:
    with pytest.raises(UnsupportedMediaTypeError, match="GIF"):
        validate_upload(make_gif(), settings)


def test_empty_upload_is_rejected(settings: Settings) -> None:
    with pytest.raises(UnsupportedMediaTypeError, match="empty"):
        validate_upload(b"", settings)


def test_oversize_upload_is_rejected(settings: Settings) -> None:
    settings.max_upload_bytes = 64
    with pytest.raises(FileTooLargeError, match="limit"):
        validate_upload(make_png() + b"\x00" * 256, settings)


def test_a_valid_upload_carries_its_size_and_format(settings: Settings) -> None:
    data = make_png()
    prepared = validate_upload(data, settings)

    assert prepared.byte_size == len(data)
    assert prepared.data == data
    # Phase 2 fills these in; until then they are honestly absent rather than zero.
    assert prepared.width is None
    assert prepared.phash is None
    assert prepared.pixel_area is None

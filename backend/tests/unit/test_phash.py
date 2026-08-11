"""Perceptual hashing.

The property that matters: stable under re-encoding, different across different
photographs. A hash that fails the first is useless as a cache key; one that fails
the second silently merges unrelated requests.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from biovision.pipeline.phash import (
    HASH_HEX_LENGTH,
    hamming_distance,
    perceptual_hash,
)
from tests.conftest import encode, make_image


def _pixels(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _hash_of(image: Image.Image) -> str:
    return perceptual_hash(_pixels(image))


def _reencode(image: Image.Image, image_format: str, **options: object) -> Image.Image:
    return Image.open(io.BytesIO(encode(image, image_format, **options)))


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_hash_is_16_hex_characters() -> None:
    value = _hash_of(make_image(seed=1))

    assert len(value) == HASH_HEX_LENGTH == 16
    assert int(value, 16) >= 0


def test_hashing_is_deterministic() -> None:
    image = make_image(seed=7)

    assert _hash_of(image) == _hash_of(image)


def test_grayscale_input_is_accepted() -> None:
    gray = np.asarray(make_image(seed=2).convert("L"), dtype=np.uint8)

    assert len(perceptual_hash(gray)) == HASH_HEX_LENGTH


def test_a_wrongly_shaped_array_is_a_bug() -> None:
    with pytest.raises(ValueError, match="shape"):
        perceptual_hash(np.zeros((4, 4, 3, 2), dtype=np.uint8))


# ---------------------------------------------------------------------------
# Stability -- the duplicate-detection and cache-key property
# ---------------------------------------------------------------------------


def test_survives_jpeg_recompression() -> None:
    """The same photo saved twice at different qualities is the same photo."""
    image = make_image(seed=11)

    high = _hash_of(_reencode(image, "JPEG", quality=95))
    low = _hash_of(_reencode(image, "JPEG", quality=55))

    assert hamming_distance(high, low) <= 5


def test_survives_a_format_change() -> None:
    image = make_image(seed=12)

    assert hamming_distance(
        _hash_of(_reencode(image, "PNG")), _hash_of(_reencode(image, "JPEG", quality=90))
    ) <= 5


def test_survives_moderate_resizing() -> None:
    """Uploads are resized to 1280px, so the hash must not depend on resolution."""
    image = make_image((1600, 1200), seed=13)
    resized = image.resize((800, 600), Image.Resampling.LANCZOS)

    assert hamming_distance(_hash_of(image), _hash_of(resized)) <= 5


def test_survives_a_brightness_shift() -> None:
    """Thresholding against the median is what buys this; the mean would not."""
    image = make_image(seed=14)
    brighter = Image.fromarray(
        np.clip(_pixels(image).astype(np.int16) + 25, 0, 255).astype(np.uint8)
    )

    assert hamming_distance(_hash_of(image), _hash_of(brighter)) <= 5


# ---------------------------------------------------------------------------
# Separation
# ---------------------------------------------------------------------------


def test_different_images_hash_differently() -> None:
    assert _hash_of(make_image(seed=1)) != _hash_of(make_image(seed=2))


def test_distinct_images_are_far_apart() -> None:
    """Comfortably beyond the <=5 band the stability tests occupy."""
    distances = [
        hamming_distance(_hash_of(make_image(seed=a)), _hash_of(make_image(seed=b)))
        for a in range(4)
        for b in range(4)
        if a < b
    ]

    assert min(distances) >= 10, f"closest pair was only {min(distances)} bits apart"


# ---------------------------------------------------------------------------
# Hamming distance
# ---------------------------------------------------------------------------


def test_distance_of_a_hash_to_itself_is_zero() -> None:
    value = _hash_of(make_image(seed=5))

    assert hamming_distance(value, value) == 0


def test_distance_counts_differing_bits() -> None:
    assert hamming_distance("0000000000000000", "000000000000000f") == 4
    assert hamming_distance("0000000000000000", "ffffffffffffffff") == 64


def test_mismatched_lengths_are_rejected() -> None:
    with pytest.raises(ValueError, match="lengths differ"):
        hamming_distance("abcd", "abcdef")

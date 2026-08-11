"""Resizing and re-encoding."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from biovision.pipeline.normalize import (
    encode_jpeg,
    from_rgb_array,
    resize_long_edge,
    to_rgb_array,
)
from tests.conftest import make_image


def test_resizes_by_the_longer_edge() -> None:
    landscape = resize_long_edge(make_image((3000, 2000)), 1280)
    portrait = resize_long_edge(make_image((2000, 3000)), 1280)

    assert landscape.size == (1280, 853)
    assert portrait.size == (853, 1280)


def test_aspect_ratio_is_preserved() -> None:
    original = make_image((1920, 1080))
    resized = resize_long_edge(original, 1280)

    assert abs(resized.width / resized.height - 1920 / 1080) < 0.01


def test_smaller_images_are_never_enlarged() -> None:
    """Upscaling would invent pixels and inflate storage for no gain."""
    small = make_image((400, 300))

    assert resize_long_edge(small, 1280).size == (400, 300)


def test_an_image_exactly_at_the_limit_is_untouched() -> None:
    assert resize_long_edge(make_image((1280, 720)), 1280).size == (1280, 720)


def test_encoded_output_is_jpeg() -> None:
    payload = encode_jpeg(make_image())

    assert payload.startswith(b"\xff\xd8\xff")
    assert Image.open(io.BytesIO(payload)).format == "JPEG"


def test_encoding_attaches_no_metadata() -> None:
    """Asserted rather than assumed: Pillow's behaviour here is what we rely on."""
    payload = encode_jpeg(make_image())
    decoded = Image.open(io.BytesIO(payload))

    assert not dict(decoded.getexif())
    assert "icc_profile" not in decoded.info
    assert "comment" not in decoded.info


def test_non_rgb_input_is_converted() -> None:
    grayscale = make_image(mode="L")

    assert Image.open(io.BytesIO(encode_jpeg(grayscale))).mode == "RGB"


def test_array_round_trip_preserves_pixels() -> None:
    original = make_image(seed=4)

    assert np.array_equal(to_rgb_array(from_rgb_array(to_rgb_array(original))),
                          to_rgb_array(original))


def test_array_conversion_produces_the_expected_shape_and_type() -> None:
    pixels = to_rgb_array(make_image((640, 480)))

    assert pixels.shape == (480, 640, 3)
    assert pixels.dtype == np.uint8

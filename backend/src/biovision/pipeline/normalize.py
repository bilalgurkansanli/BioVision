"""Resize and re-encode -- step 7 of the ingestion pipeline.

Produces the single representation that is ever persisted: metadata-free, bounded
in size, and encoded as JPEG regardless of what arrived.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

#: Quality for the stored derivative. 88 is well above the point where JPEG
#: artefacts start competing with the fine scratches the specialist has to detect,
#: while keeping a 1280 px image around 150-250 KB.
JPEG_QUALITY = 88


def resize_long_edge(image: Image.Image, long_edge: int) -> Image.Image:
    """Scale so the longer side is at most ``long_edge``, preserving aspect ratio.

    Only ever downscales. Enlarging a small photograph would invent pixels and
    inflate storage for no gain in what a model can see.
    """
    width, height = image.size
    longest = max(width, height)
    if longest <= long_edge:
        return image

    scale = long_edge / longest
    return image.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        resample=Image.Resampling.LANCZOS,
    )


def encode_jpeg(image: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
    """Encode to JPEG with no metadata attached.

    Pillow only writes EXIF when explicitly handed an ``exif`` argument, so simply
    not passing one is what keeps the output clean. ``test_normalize.py`` asserts
    the absence rather than trusting that behaviour to stay put.
    """
    buffer = io.BytesIO()
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    rgb.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def to_rgb_array(image: Image.Image) -> np.ndarray:
    """Convert to the HxWx3 uint8 RGB array every model in this project consumes."""
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    return np.asarray(rgb, dtype=np.uint8)


def from_rgb_array(pixels: np.ndarray) -> Image.Image:
    return Image.fromarray(pixels, mode="RGB")

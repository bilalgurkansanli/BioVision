"""Values handed between pipeline stages and models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from biovision.schemas.analyze import Integrity, Privacy
from biovision.schemas.enums import ImageFormat


@dataclass(frozen=True, eq=False)
class PreparedImage:
    """An upload that has been through the full ingestion pipeline.

    By the time this exists the image has been decoded, rotated to its EXIF
    orientation, hashed, redacted, stripped of metadata and resized. Nothing
    upstream of a model ever sees the original bytes.

    ``eq=False`` because the class holds a numpy array, and the generated
    ``__eq__`` would raise on the ambiguous truth value of an array comparison.
    """

    pixels: np.ndarray
    """RGB uint8, redacted and resized. This is what every model reads."""

    stored_bytes: bytes
    """EXIF-free JPEG. The only representation ever written to storage.

    The original upload is never persisted -- not to disk, not to Supabase, not to
    a temporary file that outlives the request.
    """

    image_format: ImageFormat
    """Container the upload arrived in, before any conversion."""

    byte_size: int
    """Size of the original upload, for the size limit and for logging."""

    width: int
    height: int
    phash: str
    """64-bit perceptual hash as 16 hex characters. Duplicate detection and VLM cache key."""

    integrity: Integrity
    privacy: Privacy

    @property
    def pixel_area(self) -> int:
        return self.width * self.height

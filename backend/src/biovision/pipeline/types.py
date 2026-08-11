"""Values handed between pipeline stages and models."""

from __future__ import annotations

from dataclasses import dataclass, field

from biovision.schemas.analyze import Integrity, Privacy
from biovision.schemas.enums import ImageFormat


@dataclass(frozen=True)
class PreparedImage:
    """An upload that has passed validation and is ready for inference.

    Sprint 1 populates `data`, `image_format` and `byte_size` only; the remaining
    fields arrive with the Phase 2 pipeline (decode, EXIF, pHash, redaction). They
    are declared now because they are part of the value's identity, and because a
    model that needs `width` should fail a type check rather than a runtime lookup.
    """

    data: bytes
    image_format: ImageFormat
    byte_size: int
    width: int | None = None
    height: int | None = None
    phash: str | None = None
    integrity: Integrity = field(default_factory=Integrity)
    privacy: Privacy = field(default_factory=Privacy)

    @property
    def pixel_area(self) -> int | None:
        if self.width is None or self.height is None:
            return None
        return self.width * self.height

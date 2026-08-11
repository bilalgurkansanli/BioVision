"""The ingestion pipeline: everything that happens to an image before inference.

The eight steps run here, in this order, and nowhere else:

1. format check (magic bytes)
2. size check
3. EXIF read -- capture time, GPS presence, device
4. EXIF orientation applied
5. perceptual hash
6. face and plate redaction
7. metadata stripped, resized to the stored long edge
8. inference (in ``orchestrator``, on the output of this module)

Two orderings are load-bearing and easy to get wrong:

* **Orientation before everything.** Phones record rotation as metadata rather than
  rotating pixels. A model handed the raw buffer sees a sideways car, and the boxes
  it returns are in a coordinate frame the user never saw.
* **Hash before redaction.** The perceptual hash identifies the *submitted*
  photograph. Hashing after redaction would make the fingerprint depend on how many
  faces the detector happened to find, so the same image submitted twice could hash
  differently and slip past duplicate detection.
"""

from __future__ import annotations

import logging

from biovision.config import Settings
from biovision.pipeline.exif import apply_orientation, read_exif
from biovision.pipeline.normalize import (
    encode_jpeg,
    from_rgb_array,
    resize_long_edge,
    to_rgb_array,
)
from biovision.pipeline.phash import perceptual_hash
from biovision.pipeline.redact import Redactor
from biovision.pipeline.types import PreparedImage
from biovision.pipeline.validate import validate_and_decode

logger = logging.getLogger(__name__)


def prepare_image(raw: bytes, *, settings: Settings, redactor: Redactor) -> PreparedImage:
    """Take raw upload bytes to something safe to analyse and safe to store.

    Raises:
        BioVisionError: any documented input failure; ``api.errors`` maps it.
    """
    # Steps 1-2, plus decoding, which is itself the check for truncation.
    image, image_format = validate_and_decode(raw, settings)

    # Step 3: read before anything can destroy it.
    integrity = read_exif(image)

    # Step 4: rotate before any model or hash sees the pixels.
    image = apply_orientation(image)

    # Step 5: fingerprint the photograph as submitted.
    oriented = to_rgb_array(image)
    phash = perceptual_hash(oriented)

    # Step 6: redact before the image can reach storage.
    redacted, privacy = redactor.apply(oriented)

    # Step 7: resize, then encode.
    #
    # Metadata stripping is structural rather than a separate step: the pixels have
    # been through a numpy array, so the PIL image rebuilt from them carries no EXIF,
    # ICC profile or comment block to begin with, and `encode_jpeg` is never handed
    # an `exif` argument. `test_ingest.py` asserts the absence rather than trusting
    # either of those to stay true.
    stored_image = resize_long_edge(from_rgb_array(redacted), settings.stored_long_edge)
    pixels = to_rgb_array(stored_image)
    stored_bytes = encode_jpeg(stored_image)

    height, width = pixels.shape[:2]

    logger.debug(
        "prepared %s %dx%d -> %dx%d, %d bytes -> %d, phash=%s, faces=%d plates=%d",
        image_format.value,
        *image.size,
        width,
        height,
        len(raw),
        len(stored_bytes),
        phash,
        privacy.faces_blurred,
        privacy.plates_blurred,
    )

    return PreparedImage(
        pixels=pixels,
        stored_bytes=stored_bytes,
        image_format=image_format,
        byte_size=len(raw),
        width=width,
        height=height,
        phash=phash,
        integrity=integrity,
        privacy=privacy,
    )

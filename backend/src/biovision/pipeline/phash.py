"""Perceptual hashing -- step 5 of the ingestion pipeline.

Two uses, both of which need the same property: an image that has been re-encoded,
lightly resized or re-compressed must hash to the same value as the original.

* **Duplicate detection.** The same photograph submitted twice -- possibly by a
  different user, possibly months apart -- is evidence worth surfacing.
* **VLM cache key.** A repeated image is answered from storage instead of from the
  paid API. Note for Phase 6: the cache key must combine this hash *with the
  response language*, or a cached Turkish description gets served to a request that
  asked for English.

Implemented here rather than pulled from `imagehash`, whose only reason for
depending on scipy is the DCT -- and OpenCV, already a dependency, provides one.
The algorithm is the standard DCT-based pHash and is pinned by test vectors.
"""

from __future__ import annotations

import cv2
import numpy as np

#: Working resolution before the DCT. 32x32 is the conventional choice: large enough
#: that the top-left 8x8 block carries real structure, small enough to be cheap.
_RESIZE = 32
#: Side of the retained low-frequency block. 8x8 minus the DC term gives 63 usable
#: coefficients, rounded to a 64-bit hash.
_BLOCK = 8

HASH_BITS = _BLOCK * _BLOCK
HASH_HEX_LENGTH = HASH_BITS // 4


def perceptual_hash(rgb: np.ndarray) -> str:
    """Compute a 64-bit perceptual hash, returned as 16 lowercase hex characters.

    Args:
        rgb: An HxWx3 uint8 RGB array, or an HxW grayscale array.

    The pipeline: grayscale -> 32x32 -> DCT -> keep the top-left 8x8 block of low
    frequencies -> threshold each coefficient against the block median. Comparing
    against the median rather than the mean is what makes the result robust to
    brightness and contrast shifts, since it moves with the distribution.
    """
    if rgb.ndim == 3:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    elif rgb.ndim == 2:
        gray = rgb
    else:
        raise ValueError(f"expected a 2D or 3D array, got shape {rgb.shape}")

    small = cv2.resize(gray, (_RESIZE, _RESIZE), interpolation=cv2.INTER_AREA)
    coefficients = cv2.dct(small.astype(np.float32))
    block = coefficients[:_BLOCK, :_BLOCK]

    # The DC term is total image brightness. It dwarfs everything else and carries
    # no structural information, so it is excluded from the median -- otherwise the
    # threshold tracks exposure rather than content.
    without_dc = block.flatten()[1:]
    median = float(np.median(without_dc))

    bits = (block.flatten() > median).astype(np.uint8)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)

    return f"{value:0{HASH_HEX_LENGTH}x}"


def hamming_distance(left: str, right: str) -> int:
    """Number of differing bits between two hashes.

    Rule of thumb for 64-bit pHash: 0 is the same image, <= 5 is very likely the
    same photograph re-encoded, >= 10 is a different photograph. Phase 7 pins the
    duplicate threshold against the golden set rather than adopting a number from
    folklore.
    """
    if len(left) != len(right):
        raise ValueError(f"hash lengths differ: {len(left)} vs {len(right)}")
    return bin(int(left, 16) ^ int(right, 16)).count("1")

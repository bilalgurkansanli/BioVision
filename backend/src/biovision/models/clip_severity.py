"""Whole-photograph damage severity, zero-shot on the shared CLIP encoder.

**Why this layer exists.** The specialist reports instances -- a dent here, a
scratch there. It was pointed at a photograph of a written-off Citroen and
returned one `dent` at 42%: true about that dent, and not an assessment. Cropping
to the car raised it to four findings, which is also not an assessment. A total is
not a sum of parts, and no confidence floor or tiling scheme turns one into the
other (ADR-030, ADR-033).

So this asks the whole image a different question. It looks at the frame rather
than hunting small regions, which is also why framing costs it less than it costs
the detector.

**It is measured and it is not good: 64.5%** over 248 held-out images. `minor`
recalls at 98% and `severe` at 51%, and nearly every error is one band low --
`severe` read as `moderate`. Every response therefore carries
`overall_severity_calibrated: false`, and README section 7.8 publishes the
confusion matrix rather than the headline.

**It costs nothing to run.** The image embedding is already computed for the gate
and reused by the router; this reuses it again. The only new work is a dot
product against 12 cached text embeddings.
"""

from __future__ import annotations

import logging

import numpy as np

from biovision.domains.severity import SeverityPrompts
from biovision.models.clip import ClipEncoder
from biovision.models.scoring import softmax
from biovision.schemas.enums import Severity

logger = logging.getLogger(__name__)


class ClipSeverityEstimator:
    """Zero-shot severity over the whole photograph."""

    def __init__(self, encoder: ClipEncoder, prompts: SeverityPrompts) -> None:
        self._encoder = encoder
        self._bands = prompts.band_order

        # One vector per band: the mean of its prompt ensemble, re-normalised.
        # A single phrasing is brittle; the mean of several is measurably steadier.
        vectors = []
        for band in self._bands:
            embedded = encoder.encode_texts(prompts.prompts_for(band))
            mean = np.asarray(embedded, dtype=np.float32).mean(axis=0)
            vectors.append(mean / np.linalg.norm(mean))
        self._text = np.stack(vectors)

        logger.info(
            "severity estimator ready: %d bands (%s), zero-shot, uncalibrated",
            len(self._bands),
            ", ".join(b.value for b in self._bands),
        )

    @property
    def name(self) -> str:
        return f"clip-severity-{self._encoder.name}"

    def estimate(self, rgb: np.ndarray, cache_key: str | None = None) -> tuple[Severity, float]:
        """Return the band and its softmax score.

        `cache_key` lets this share the embedding the gate already computed for
        the same image, which is why this layer costs no additional encode.
        """
        vector = self._encoder.encode_image(rgb, cache_key=cache_key)
        vector = vector / np.linalg.norm(vector)
        probabilities = softmax(100.0 * (self._text @ vector))
        index = int(probabilities.argmax())
        return self._bands[index], round(float(probabilities[index]), 4)

"""Layer 1 -- zero-shot domain routing."""

from __future__ import annotations

import logging

import numpy as np

from biovision.domains.catalog import DomainCatalog
from biovision.models.base import RouterDecision
from biovision.models.calibration import Calibration
from biovision.models.clip import ClipEncoder
from biovision.models.scoring import softmax
from biovision.pipeline.types import PreparedImage

logger = logging.getLogger(__name__)


class ClipRouter:
    """Assigns an image to a domain from `domains.yaml`.

    The candidate set is built from the catalogue at construction time, so adding a
    domain remains a one-line edit to that file: a new entry becomes a new column in
    the softmax with no code change here. The extensibility test exercises exactly
    this path.

    Each domain contributes a **prompt ensemble** rather than a single phrase.
    Zero-shot classification from one prompt is unstable -- the wording moves the
    result as much as the image does -- so the several phrasings per domain are
    averaged into one direction.
    """

    def __init__(
        self,
        encoder: ClipEncoder,
        catalog: DomainCatalog,
        calibration: Calibration | None = None,
    ) -> None:
        self._encoder = encoder
        self._calibration = calibration
        self._keys = catalog.keys

        prompt_map = catalog.prompt_map()
        self._text = np.stack(
            [encoder.embed_prompt_ensemble(prompt_map[key]) for key in self._keys]
        )
        self._ready = True

        logger.info(
            "router ready: %d domains (%s), calibrated=%s",
            len(self._keys),
            ", ".join(self._keys),
            calibration is not None,
        )

    @property
    def encoder(self) -> ClipEncoder:
        """The shared encoder. Exposed so a test can prove it is genuinely shared."""
        return self._encoder

    @property
    def name(self) -> str:
        return f"clip-router-{self._encoder.name}"

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def calibrated(self) -> bool:
        return self._calibration is not None

    def classify(self, image: PreparedImage) -> RouterDecision:
        # Same key the gate used, so the embedding is computed once per request
        # rather than once per layer.
        embedding = self._encoder.encode_image(image.pixels, cache_key=image.phash)
        logits = self._encoder.logit_scale * (self._text @ embedding)

        if self._calibration is not None:
            # Temperature scaling cannot reorder the classes, so the predicted
            # domain is identical either way -- only the reported confidence moves.
            logits = self._calibration.apply(logits)

        probabilities = softmax(logits)
        winner = int(np.argmax(probabilities))

        scores = {
            key: round(float(probability), 4)
            for key, probability in zip(self._keys, probabilities, strict=True)
        }

        return RouterDecision(
            domain=self._keys[winner],
            confidence=round(float(probabilities[winner]), 4),
            calibrated=self.calibrated,
            scores=scores,
        )

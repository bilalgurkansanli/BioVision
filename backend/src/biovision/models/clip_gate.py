"""Layer 0 -- zero-shot out-of-distribution rejection."""

from __future__ import annotations

import logging

import numpy as np

from biovision.domains.gate import GatePrompts
from biovision.models.base import GateDecision
from biovision.models.clip import ClipEncoder
from biovision.models.scoring import softmax
from biovision.pipeline.types import PreparedImage

logger = logging.getLogger(__name__)


class ClipGate:
    """Decides whether an upload shows a physical object at all.

    Both prompt groups are scored in a **single softmax** and the in-distribution
    probability is the summed mass of the accepting prompts. Scoring the groups
    separately would compare each against nothing; and the out-of-scope categories
    -- selfies, screenshots, food, memes -- are too varied for one "not damage"
    prompt to stand in for.

    Note what this layer does not ask. It does not ask whether anything is damaged.
    A photograph of an undamaged car should yield "no findings", not a 422:
    "there is nothing wrong with this" is an answer worth being able to give.
    """

    def __init__(
        self,
        encoder: ClipEncoder,
        prompts: GatePrompts,
        threshold: float,
    ) -> None:
        self._encoder = encoder
        self._threshold = threshold
        self._in_count = prompts.in_distribution_count

        # Embedded once at startup. The prompts are configuration and do not vary
        # per request, so encoding them per call would be pure waste.
        self._text = encoder.encode_texts(prompts.all_prompts)
        self._ready = True

        logger.info(
            "gate ready: %d in-distribution / %d out-of-distribution prompts, threshold=%.3f",
            self._in_count,
            len(prompts.out_of_distribution),
            threshold,
        )

    @property
    def encoder(self) -> ClipEncoder:
        """The shared encoder. Exposed so a test can prove it is genuinely shared."""
        return self._encoder

    @property
    def name(self) -> str:
        return f"clip-gate-{self._encoder.name}"

    @property
    def ready(self) -> bool:
        return self._ready

    def check(self, image: PreparedImage) -> GateDecision:
        return self.check_pixels(image.pixels, cache_key=image.phash)

    def check_pixels(self, rgb: np.ndarray, cache_key: str | None = None) -> GateDecision:
        """Score a raw RGB array.

        Exists so the evaluation scripts can measure this layer directly, without
        constructing a `PreparedImage` and paying for redaction and hashing they do
        not use. The request path goes through :meth:`check`.
        """
        embedding = self._encoder.encode_image(rgb, cache_key=cache_key)
        logits = self._encoder.logit_scale * (self._text @ embedding)
        probabilities = softmax(logits)

        score = float(probabilities[: self._in_count].sum())

        logger.debug(
            "gate score=%.4f threshold=%.4f top_out=%.4f",
            score,
            self._threshold,
            float(np.max(probabilities[self._in_count :])),
        )

        return GateDecision(
            passed=score >= self._threshold,
            score=round(score, 4),
            threshold=self._threshold,
        )

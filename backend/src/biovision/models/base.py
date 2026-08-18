"""Model interfaces.

Every layer is defined as a Protocol before any implementation exists. That is what
lets the whole system be tested without a single model weight on disk: the mock
implementations in `models/mock/` satisfy these same interfaces, so the pipeline
under test is the production pipeline, not a parallel one written for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from biovision.pipeline.types import PreparedImage
from biovision.schemas.analyze import Finding
from biovision.schemas.enums import Severity


@dataclass(frozen=True)
class GateDecision:
    """Layer 0 verdict: is this a damage/object photograph at all?"""

    passed: bool
    score: float
    threshold: float


@dataclass(frozen=True)
class RouterDecision:
    """Layer 1 verdict: which domain does this photograph belong to?"""

    domain: str
    confidence: float
    calibrated: bool
    scores: dict[str, float]
    """Full per-domain distribution. Logged for evaluation; not returned to clients."""


@runtime_checkable
class LoadableModel(Protocol):
    @property
    def name(self) -> str:
        """Stable identifier, reported by /health and in AnalyzeResponse."""

    @property
    def ready(self) -> bool:
        """False when the checkpoint failed to load; surfaces as /health degraded."""


@runtime_checkable
class GateModel(LoadableModel, Protocol):
    def check(self, image: PreparedImage) -> GateDecision: ...


@runtime_checkable
class RouterModel(LoadableModel, Protocol):
    @property
    def calibrated(self) -> bool:
        """Whether a fitted temperature is loaded behind the confidences.

        Part of the protocol rather than an implementation detail: `/v1/domains`
        and `/v1/analyze` both report a `calibrated` field to clients, and both
        must derive it from the same fact. Leaving it off the protocol let the
        two drift.
        """

    def classify(self, image: PreparedImage) -> RouterDecision: ...


@runtime_checkable
class SeverityModel(Protocol):
    """Whole-photograph severity, as opposed to per-instance findings."""

    @property
    def name(self) -> str: ...

    def estimate(self, rgb: np.ndarray, cache_key: str | None = None) -> tuple[Severity, float]:
        """Return the band and its score. Never calibrated -- see clip_severity."""


@runtime_checkable
class SpecialistModel(LoadableModel, Protocol):
    @property
    def domain(self) -> str:
        """The single domain key this specialist is trained for."""

    def analyze(self, image: PreparedImage) -> list[Finding]: ...


@runtime_checkable
class VLMClient(LoadableModel, Protocol):
    def describe(self, image: PreparedImage, language: str) -> str:
        """Free-text description for the fallback path.

        The return value is never parsed into findings. If a caller is tempted to
        extract structure from this string, the correct move is to train a
        specialist for that domain instead.
        """

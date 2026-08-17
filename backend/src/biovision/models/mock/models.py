"""Mock implementations of the four model interfaces.

Determinism comes from the SHA-256 of the image bytes: the same upload always
yields the same verdict, across processes and machines. Every mock also accepts
explicit overrides so a test can pin a specific branch of the pipeline without
having to hunt for input bytes that happen to hash the right way.
"""

from __future__ import annotations

import hashlib

from biovision.models.base import GateDecision, RouterDecision
from biovision.models.severity import severity_for
from biovision.pipeline.types import PreparedImage
from biovision.schemas.analyze import Finding
from biovision.schemas.enums import DamageType

#: Fixed bbox for mock findings. Coordinates are meaningless; only the shape of the
#: contract is being exercised.
_MOCK_BBOX = (120, 340, 260, 410)


def _digest(image: PreparedImage) -> int:
    # Hashes the stored derivative rather than the raw upload: it is deterministic
    # for a given input, and it is also what the real models actually see.
    return int.from_bytes(hashlib.sha256(image.stored_bytes).digest()[:8], "big")


def _unit(image: PreparedImage, salt: int) -> float:
    """A stable pseudo-random float in [0, 1) derived from the image bytes."""
    return ((_digest(image) >> salt) % 10_000) / 10_000.0


class MockGate:
    """Layer 0 stand-in.

    Passes by default. `forced_pass=False` produces the rejection branch (422) so
    the out-of-distribution path can be tested without a real CLIP model.
    """

    def __init__(self, threshold: float = 0.25, forced_pass: bool | None = None) -> None:
        self._threshold = threshold
        self._forced_pass = forced_pass

    @property
    def name(self) -> str:
        return "mock-gate-v1"

    @property
    def ready(self) -> bool:
        return True

    def check(self, image: PreparedImage) -> GateDecision:
        if self._forced_pass is not None:
            score = 0.99 if self._forced_pass else 0.01
            return GateDecision(passed=self._forced_pass, score=score, threshold=self._threshold)
        # Scaled into [0.30, 1.00) so the default path passes: the mock backend is
        # for exercising the contract, and a mock that randomly 422s would make the
        # local demo useless.
        score = 0.30 + 0.70 * _unit(image, salt=0)
        return GateDecision(
            passed=score >= self._threshold, score=round(score, 4), threshold=self._threshold
        )


class MockRouter:
    """Layer 1 stand-in. Picks a domain by hashing the image bytes."""

    def __init__(
        self,
        domain_keys: list[str],
        forced_domain: str | None = None,
        forced_confidence: float | None = None,
    ) -> None:
        if not domain_keys:
            raise ValueError("MockRouter needs at least one domain key")
        self._keys = list(domain_keys)
        self._forced_domain = forced_domain
        self._forced_confidence = forced_confidence

    @property
    def name(self) -> str:
        return "mock-router-v1"

    @property
    def ready(self) -> bool:
        return True

    @property
    def calibrated(self) -> bool:
        """Never. A mock has no fitted temperature and must not claim one."""
        return False

    def classify(self, image: PreparedImage) -> RouterDecision:
        domain = self._forced_domain or self._keys[_digest(image) % len(self._keys)]
        confidence = (
            self._forced_confidence
            if self._forced_confidence is not None
            else round(0.60 + 0.39 * _unit(image, salt=8), 4)
        )

        # A plausible distribution: the winner takes `confidence`, the remainder is
        # split evenly. Only the argmax and the top score are ever consumed.
        others = [key for key in self._keys if key != domain]
        share = (1.0 - confidence) / len(others) if others else 0.0
        scores = {domain: confidence} | {key: round(share, 4) for key in others}

        # calibrated=False is the honest answer here: no temperature scaling has
        # been fitted for a mock. Phase 4 flips this for the real router.
        return RouterDecision(
            domain=domain, confidence=confidence, calibrated=False, scores=scores
        )


class MockSpecialist:
    """Layer 2 stand-in for a domain-specific expert model."""

    def __init__(self, domain: str, name: str = "mock-specialist-v1") -> None:
        self._domain = domain
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def ready(self) -> bool:
        return True

    @property
    def domain(self) -> str:
        return self._domain

    def analyze(self, image: PreparedImage) -> list[Finding]:
        count = 1 + (_digest(image) % 2)
        types = [DamageType.SCRATCH, DamageType.DENT]
        findings: list[Finding] = []
        for index in range(count):
            area_ratio = round(0.01 + 0.10 * _unit(image, salt=16 + index * 4), 4)
            findings.append(
                Finding(
                    type=types[index % len(types)],
                    score=round(0.55 + 0.40 * _unit(image, salt=24 + index * 4), 4),
                    bbox=_MOCK_BBOX,
                    area_ratio=area_ratio,
                    severity=severity_for(area_ratio),
                )
            )
        return findings


class MockVLM:
    """Fallback stand-in.

    Counts its calls. Phase 6 asserts against this counter that a repeated upload
    is served from the pHash cache and never reaches the paid API a second time.
    """

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def name(self) -> str:
        return "mock-vlm-v1"

    @property
    def ready(self) -> bool:
        return True

    def describe(self, image: PreparedImage, language: str) -> str:
        self.call_count += 1
        if language == "tr":
            return (
                "[mock] Görselde bir hasar izlenimi var; bu açıklama sahte bir model "
                "tarafından üretildi ve ölçüm değeri taşımaz."
            )
        return (
            "[mock] The image appears to show damage. This description was produced by "
            "a mock model and carries no measurement value."
        )

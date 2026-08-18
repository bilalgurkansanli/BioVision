"""The analysis pipeline.

This module owns the order of operations for the whole system, and it is the only
place that order is expressed. Route handlers stay thin so that "what happens to an
image" is answerable by reading one function.

    validate -> gate -> route -> (specialist | fallback)

Three decisions are worth stating explicitly, because each is a place where a
system like this is normally tempted to overreach:

1. A weak routing decision does **not** get a specialist run against it. Guessing a
   domain and then reporting confident findings for it is precisely the failure
   mode this project exists to avoid.
2. A domain without a specialist returns an empty ``findings`` list. The VLM's
   free-text output never becomes structured data.
3. The VLM is unreachable from the specialist path. That is the cost control:
   vehicle photographs, which are the common case, cannot spend budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from biovision.config import Settings
from biovision.errors import OutOfDistributionError
from biovision.models.registry import ModelRegistry
from biovision.pipeline.ingest import prepare_image
from biovision.pipeline.timing import StageTimer
from biovision.pipeline.types import PreparedImage
from biovision.schemas.analyze import AnalyzeResponse
from biovision.schemas.enums import UNKNOWN_DOMAIN, Severity, WarningCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisResult:
    """What the pipeline produced, and what it produced it from.

    The prepared image travels alongside the response because the caller needs
    two things the response deliberately does not carry: the perceptual hash, and
    the redacted derivative to persist. Neither belongs in the public contract --
    the hash is an internal fingerprint, and the bytes are already stored -- but
    the route needs both to write the record.
    """

    response: AnalyzeResponse
    image: PreparedImage


def analyze_image(
    raw: bytes,
    *,
    settings: Settings,
    registry: ModelRegistry,
    language: str,
    vlm_allowed: bool,
    request_id: UUID | None = None,
) -> AnalysisResult:
    """Run one image through the full pipeline.

    Args:
        raw: The uploaded bytes, unmodified.
        vlm_allowed: Whether this caller may reach the paid fallback. Anonymous
            demo traffic is allowed to use the specialist path but not the VLM, so
            unauthenticated requests cannot spend the monthly budget.

    Raises:
        BioVisionError: Any documented failure; ``api.errors`` maps it to a status.
    """
    request_id = request_id or uuid4()
    timer = StageTimer()

    with timer.stage("preprocess"):
        image = prepare_image(raw, settings=settings, redactor=registry.redactor)

    # --- Layer 0: is this a damage/object photograph at all? ---
    with timer.stage("gate"):
        gate = registry.gate.check(image)
    if not gate.passed:
        logger.info(
            "gate rejected request_id=%s score=%.4f threshold=%.4f",
            request_id,
            gate.score,
            gate.threshold,
        )
        raise OutOfDistributionError(
            "This does not look like a photograph of damage or a physical object. "
            "Upload a photo of the damaged item."
        )

    # --- Layer 1: which domain? ---
    with timer.stage("router"):
        decision = registry.router.classify(image)

    logger.info(
        "routed request_id=%s domain=%s confidence=%.4f calibrated=%s scores=%s",
        request_id,
        decision.domain,
        decision.confidence,
        decision.calibrated,
        decision.scores,
    )

    if decision.confidence < settings.router_min_confidence:
        # Q8: the image passed the gate, so it is a real photograph of something
        # damaged -- we simply cannot place it. That is an answer, not an error.
        return AnalysisResult(
            _unplaced_response(
                request_id, decision.confidence, decision.calibrated, image, timer
            ),
            image,
        )

    # Asked of the whole photograph, before the specialist hunts instances. A
    # written-off car returns one `dent` from the detector; this is the layer that
    # can say the car is written off. It reuses the embedding the gate already
    # computed for this image, so it costs a dot product.
    overall, overall_confidence = _estimate_severity(registry, image)

    specialist = registry.specialist_for(decision.domain)
    if specialist is not None:
        with timer.stage("specialist"):
            findings = specialist.analyze(image)

        # Optionally describe it as well. The specialist measured, and where it
        # is weak -- ~25% recall on dents -- a written-off car can come back as a
        # single finding, which reads as light damage to anyone not holding the
        # per-class table. A description cannot repair that measurement and does
        # not try: it stays in `vlm_description`, and the schema still refuses to
        # let free text become a finding.
        description = _describe(
            request_id=request_id,
            image=image,
            timer=timer,
            settings=settings,
            registry=registry,
            language=language,
            vlm_allowed=vlm_allowed,
            enabled=settings.vlm_augments_specialist,
        )

        return AnalysisResult(
            AnalyzeResponse(
                request_id=request_id,
                domain=decision.domain,
                domain_confidence=decision.confidence,
                domain_confidence_calibrated=decision.calibrated,
                specialist_model=specialist.name,
                # A measurement is calibrated only if the confidence behind it
                # is. Phase 4 fits the router temperature; until then this is
                # false, and the response says so rather than implying a
                # precision we lack.
                calibrated=decision.calibrated,
                overall_severity=overall,
                overall_severity_confidence=overall_confidence,
                findings=findings,
                vlm_description=description,
                integrity=image.integrity,
                privacy=image.privacy,
                timing_ms=timer.build(),
            ),
            image,
        )

    return AnalysisResult(
        _fallback_response(
            request_id=request_id,
            decision_domain=decision.domain,
            confidence=decision.confidence,
            confidence_calibrated=decision.calibrated,
            image=image,
            timer=timer,
            settings=settings,
            registry=registry,
            language=language,
            vlm_allowed=vlm_allowed,
        ),
        image,
    )


def _estimate_severity(
    registry: ModelRegistry, image: PreparedImage
) -> tuple[Severity | None, float | None]:
    """Whole-photograph severity, or (None, None) where no estimator is loaded.

    Never raises. This is a supplementary judgement -- 64.5% accurate, zero-shot,
    uncalibrated -- and it must not be able to fail a request that the specialist
    answered correctly.
    """
    if registry.severity is None:
        return None, None
    try:
        return registry.severity.estimate(image.pixels, cache_key=image.phash)
    except Exception:
        logger.exception("severity estimation failed; reporting null")
        return None, None


def _unplaced_response(
    request_id: UUID,
    confidence: float,
    confidence_calibrated: bool,
    image: PreparedImage,
    timer: StageTimer,
) -> AnalyzeResponse:
    """Router was not confident enough to name a domain."""
    return AnalyzeResponse(
        request_id=request_id,
        domain=UNKNOWN_DOMAIN,
        domain_confidence=confidence,
        domain_confidence_calibrated=confidence_calibrated,
        specialist_model=None,
        calibrated=False,
        findings=[],
        warning=WarningCode.LOW_DOMAIN_CONFIDENCE,
        integrity=image.integrity,
        privacy=image.privacy,
        timing_ms=timer.build(),
    )


def _describe(
    *,
    request_id: UUID,
    image: PreparedImage,
    timer: StageTimer,
    settings: Settings,
    registry: ModelRegistry,
    language: str,
    vlm_allowed: bool,
    enabled: bool,
) -> str | None:
    """One free-text description, or None, with every guard in one place.

    Both callers -- the domain with no specialist and the domain whose specialist
    is thin -- need the same protections: the cache, the budget, and the rule that
    anonymous traffic cannot spend money. Duplicating them was how one copy would
    eventually lose one of them.
    """
    if not (enabled and vlm_allowed and settings.vlm_enabled and registry.vlm is not None):
        logger.info(
            "no description request_id=%s enabled=%s vlm_allowed=%s vlm_enabled=%s",
            request_id,
            enabled,
            vlm_allowed,
            settings.vlm_enabled,
        )
        return None

    # Cache first: an image already described costs nothing to describe again. The
    # key includes the language -- without it a cached Turkish description would be
    # served to a request that asked for English.
    cached = registry.cache.get(image.phash, language)
    if cached is not None:
        return cached

    # The budget check lives inside `describe` and runs before the request, so an
    # exhausted budget raises ServiceDegradedError (503) without spending anything.
    # A VLM merely unavailable to *this caller* is a different case: it returns 200,
    # because nothing has broken.
    with timer.stage("vlm"):
        description = registry.vlm.describe(image, language)
    registry.cache.put(image.phash, language, description)
    return description


def _fallback_response(
    *,
    request_id: UUID,
    decision_domain: str,
    confidence: float,
    confidence_calibrated: bool,
    image: PreparedImage,
    timer: StageTimer,
    settings: Settings,
    registry: ModelRegistry,
    language: str,
    vlm_allowed: bool,
) -> AnalyzeResponse:
    """The domain is known but no specialist exists for it.

    This is the response the project is built around. ``findings`` stays empty, the
    warning names the reason, and any text comes from the VLM clearly labelled as a
    description.
    """
    # Always enabled on this path: describing it is the entire answer here, since
    # there is no specialist to produce findings.
    description = _describe(
        request_id=request_id,
        image=image,
        timer=timer,
        settings=settings,
        registry=registry,
        language=language,
        vlm_allowed=vlm_allowed,
        enabled=True,
    )

    return AnalyzeResponse(
        request_id=request_id,
        domain=decision_domain,
        domain_confidence=confidence,
        domain_confidence_calibrated=confidence_calibrated,
        specialist_model=None,
        calibrated=False,
        findings=[],
        vlm_description=description,
        warning=WarningCode.NO_SPECIALIST,
        integrity=image.integrity,
        privacy=image.privacy,
        timing_ms=timer.build(),
    )

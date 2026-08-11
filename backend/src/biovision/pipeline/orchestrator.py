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
from uuid import UUID, uuid4

from biovision.config import Settings
from biovision.errors import OutOfDistributionError
from biovision.models.registry import ModelRegistry
from biovision.pipeline.ingest import prepare_image
from biovision.pipeline.timing import StageTimer
from biovision.pipeline.types import PreparedImage
from biovision.schemas.analyze import AnalyzeResponse
from biovision.schemas.enums import UNKNOWN_DOMAIN, WarningCode

logger = logging.getLogger(__name__)


def analyze_image(
    raw: bytes,
    *,
    settings: Settings,
    registry: ModelRegistry,
    language: str,
    vlm_allowed: bool,
    request_id: UUID | None = None,
) -> AnalyzeResponse:
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
        return _unplaced_response(
            request_id, decision.confidence, decision.calibrated, image, timer
        )

    specialist = registry.specialist_for(decision.domain)
    if specialist is not None:
        with timer.stage("specialist"):
            findings = specialist.analyze(image)
        return AnalyzeResponse(
            request_id=request_id,
            domain=decision.domain,
            domain_confidence=decision.confidence,
            domain_confidence_calibrated=decision.calibrated,
            specialist_model=specialist.name,
            # A measurement is calibrated only if the confidence behind it is.
            # Phase 4 fits the router temperature; until then this is false, and
            # the response says so rather than implying a precision we lack.
            calibrated=decision.calibrated,
            findings=findings,
            integrity=image.integrity,
            privacy=image.privacy,
            timing_ms=timer.build(),
        )

    return _fallback_response(
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
    )


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
    description: str | None = None

    if vlm_allowed and settings.vlm_enabled and registry.vlm is not None:
        # Phase 6 inserts the pHash cache lookup and the budget check here. A
        # budget that has run out raises ServiceDegradedError (503); a VLM that is
        # merely unavailable to this caller leaves `description` as None and
        # returns 200, because nothing has actually broken.
        with timer.stage("vlm"):
            description = registry.vlm.describe(image, language)
    else:
        logger.info(
            "fallback without VLM request_id=%s domain=%s vlm_allowed=%s vlm_enabled=%s",
            request_id,
            decision_domain,
            vlm_allowed,
            settings.vlm_enabled,
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

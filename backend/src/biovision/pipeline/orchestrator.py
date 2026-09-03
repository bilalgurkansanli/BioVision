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
from biovision.models.band_reliability import reliability_out
from biovision.models.base import DamageRegion, RegionAwareSpecialist
from biovision.models.registry import ModelRegistry
from biovision.pipeline.ingest import prepare_image
from biovision.pipeline.timing import StageTimer
from biovision.pipeline.types import PreparedImage
from biovision.schemas.analyze import AnalyzeResponse, DamageRegionOut, Finding
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
            _unplaced_response(request_id, decision.confidence, decision.calibrated, image, timer),
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
            # A specialist that can report the damaged region does; one that
            # cannot still returns findings, and `damage_region` stays null. The
            # capability is checked rather than required so that a box-only
            # specialist cannot be forced to report a box's area as a segmented
            # measurement.
            if isinstance(specialist, RegionAwareSpecialist):
                assessment = specialist.assess(image)
                findings, region = assessment.findings, assessment.region
            else:
                findings, region = specialist.analyze(image), None

        # Applied here rather than inside the specialist: the band is computed
        # before the specialist runs and belongs to the pipeline, not to the
        # detector. Filtering first also lets the region rule below see the
        # findings a reader will actually be shown.
        findings = _findings_the_band_cannot_talk_you_out_of(
            findings, overall, settings.specialist_strict_confidence
        )

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
                overall_severity_reliability=reliability_out(overall),
                findings=findings,
                damage_region=_region_out(
                    _region_unless_nothing_is_wrong(region, overall, findings)
                ),
                vlm_description=description,
                warning=_specialist_caveat(
                    findings, getattr(specialist, "evaluation_size", None)
                ),
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


#: Below this many evaluation images behind a class, the result is reported as a
#: suggestion. 100 is a stated round number rather than a fitted one: it is the
#: point at which a single misjudged photograph stops moving a percentage by more
#: than a point, and nothing about this set was consulted in choosing it.
SMALL_EVALUATION_BELOW = 100


def _specialist_caveat(findings: list[Finding], evaluation_size: int | None) -> WarningCode | None:
    """Say when a specialist's numbers rest on too few photographs to lean on.

    The building crack specialist is the case this exists for. Through the
    pipeline it finds 59 of 60 cracked walls and falsely flags 1 of 15 intact
    rooms -- usable figures, and far better than the 15 of 15 the checkpoint
    produces when fed directly, because the gate and the router reject most
    ordinary room photographs before it ever runs. But 60 and 15 are small, and
    neither set contains a Turkish residential interior, which is the population
    that matters. A reader is owed that.

    Driven by the size of the evidence rather than by a specialist's name, so a
    future model earns silence by being measured on more, not by being trusted.
    """
    if not findings or evaluation_size is None:
        return None
    if evaluation_size < SMALL_EVALUATION_BELOW:
        return WarningCode.SPECIALIST_SMALL_EVALUATION
    return None


def _findings_the_band_cannot_talk_you_out_of(
    findings: list[Finding],
    band: Severity | None,
    strict_floor: float,
) -> list[Finding]:
    """Ask for more confidence where a second signal says nothing is wrong.

    The finding floor was chosen on damaged photographs only -- every published
    sweep used a set with no intact cars in it, so none of them could see a false
    alarm. Measured against intact vehicles it fires on **44%** of them, which is
    the failure a user notices first: being told their undamaged car is damaged.

    Raising the floor globally fixes it and costs too much. From 0.20 to 0.40,
    false alarms fall 44% -> 24% and instance recall falls 0.369 -> 0.258. Doing
    it only where the band disagrees reaches 20% for a recall cost of **0.009**,
    because the band rarely says `none` on a genuinely damaged car (10 of 248).

    The floor is a stated rule rather than a fitted one: when independent
    evidence says there is nothing here, list only a finding the detector holds
    more likely true than not. README 7.10 publishes the sweep, including that a
    stricter floor would have gone further -- choosing it would have meant
    picking a parameter by looking at the answer.
    """
    if band is not Severity.NONE:
        return findings
    return [finding for finding in findings if finding.score >= strict_floor]


def _region_unless_nothing_is_wrong(
    region: DamageRegion | None,
    band: Severity | None,
    findings: list[Finding],
) -> DamageRegion | None:
    """Drop the damaged region when both stronger signals say there is none.

    A user uploaded a showroom photograph of an intact car. The specialist listed
    nothing, correctly. The region still reported "2% of the vehicle", built from
    a single detection the system had itself judged too weak to name.

    The region floor sits at 0.10 to catch damage the finding list misses, and
    that is worth having -- but it fires on **60% of intact cars** (README 7.8),
    so on its own it is not evidence of anything. When the band says `none` and
    the finding list is empty, the region is the only signal claiming damage and
    it is the weakest of the three. Reporting it contradicts both others.

    Measured before it shipped: on the 248 damaged images behind the published
    matrix, only **4 (1.6%)** have both an empty finding list and a `none` band,
    so this silences almost nothing that mattered.

    Deliberately narrow. It does NOT drop the region when findings are empty and
    the band is minor/moderate/severe -- that is exactly the wide-shot case the
    region exists for.
    """
    if region is None:
        return None
    if band is Severity.NONE and not findings:
        return None
    return region


def _region_out(region: DamageRegion | None) -> DamageRegionOut | None:
    """Model-layer region into the response contract, or null if there was none."""
    if region is None:
        return None
    return DamageRegionOut(
        area_ratio_image=region.area_ratio_image,
        area_ratio_vehicle=region.area_ratio_vehicle,
        vehicle_frame_share=region.vehicle_frame_share,
        instances=region.instances,
        confidence_floor=region.confidence_floor,
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

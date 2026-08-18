"""The `/v1/analyze` response contract.

The honesty rules of this project are enforced here as model validators rather than
as conventions in the route handler. A convention can be forgotten by a future code
path; a validator cannot. If any layer ever tries to emit findings without a
specialist behind them, the response fails to construct.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from biovision.schemas.enums import DamageType, Severity, WarningCode


class Finding(BaseModel):
    """One detected damage instance produced by a specialist model."""

    model_config = ConfigDict(extra="forbid")

    type: DamageType
    score: float = Field(ge=0.0, le=1.0, description="Model confidence for this instance.")
    bbox: tuple[int, int, int, int] = Field(
        description="Pixel box [x1, y1, x2, y2] in the stored (resized) image."
    )
    area_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Segmented damage area divided by total image area.",
    )
    severity: Severity
    severity_calibrated: Literal[False] = Field(
        default=False,
        description=(
            "Always false. Severity starts from the damage class and can be raised "
            "by area_ratio, but it is a judgement call rather than a calibrated "
            "prediction -- VehiDE provides no severity ground truth. The class "
            "floors and area thresholds are documented in the README."
        ),
    )
    class_recall: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Measured recall for this damage class on the held-out evaluation split, "
            "or null where it has not been measured. `score` says how sure the model "
            "is about this instance; this says how much the model tends to MISS in "
            "this class. A reader needs both: a lone finding on a wrecked car can "
            "mean light damage, or it can mean a class with recall 0.25."
        ),
    )
    class_reliable: bool | None = Field(
        default=None,
        description=(
            "Whether this project considers the class usable, drawn at recall >= 0.40. "
            "False is not an error -- it is the system saying this class misses more "
            "than it finds, and the result should be read as a floor rather than an "
            "assessment."
        ),
    )

    @model_validator(mode="after")
    def _check_bbox(self) -> Self:
        x1, y1, x2, y2 = self.bbox
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"bbox must have positive width and height, got {self.bbox}")
        if x1 < 0 or y1 < 0:
            raise ValueError(f"bbox coordinates must be non-negative, got {self.bbox}")
        return self


class Integrity(BaseModel):
    """Metadata evidence about the upload, for fraud triage.

    GPS is reported as a *presence boolean*, never as coordinates: knowing a photo
    carries location data is what matters for integrity, and storing the coordinates
    themselves would create a privacy liability with no analytical payoff.
    """

    model_config = ConfigDict(extra="forbid")

    exif_datetime: datetime | None = Field(
        default=None, description="Capture time from EXIF, if present."
    )
    exif_gps_present: bool = Field(
        default=False, description="Whether GPS tags existed. Coordinates are not stored."
    )
    device: str | None = Field(default=None, description="Camera make/model from EXIF.")
    duplicate_of: UUID | None = Field(
        default=None,
        description="request_id of an earlier submission with an identical perceptual hash.",
    )


class Privacy(BaseModel):
    """What was redacted before the image was stored.

    A `None` detector field means **no redaction of that class was applied**. It is
    reported rather than hidden: claiming privacy protection that did not run would
    be the same failure this project exists to avoid.
    """

    model_config = ConfigDict(extra="forbid")

    faces_blurred: int = Field(default=0, ge=0)
    plates_blurred: int = Field(default=0, ge=0)
    face_detector: str | None = Field(
        default=None, description="Detector that ran, or null if faces were not redacted."
    )
    plate_detector: str | None = Field(
        default=None, description="Detector that ran, or null if plates were not redacted."
    )

    @model_validator(mode="after")
    def _counts_require_detectors(self) -> Self:
        if self.faces_blurred > 0 and self.face_detector is None:
            raise ValueError("faces_blurred > 0 requires a named face_detector")
        if self.plates_blurred > 0 and self.plate_detector is None:
            raise ValueError("plates_blurred > 0 requires a named plate_detector")
        return self


class TimingMs(BaseModel):
    """Per-stage wall-clock cost. Feeds the p50/p95 table in the README.

    A stage that did not run is `null`, not `0` -- the distinction matters when
    aggregating percentiles.
    """

    model_config = ConfigDict(extra="forbid")

    preprocess: int | None = None
    gate: int | None = None
    router: int | None = None
    specialist: int | None = None
    vlm: int | None = None
    total: int = Field(ge=0)


class AnalyzeResponse(BaseModel):
    """Result of a single image analysis.

    Two shapes, one schema:

    * A domain **with** a specialist -> `specialist_model` names it, `calibrated` is
      true, `findings` may be non-empty, `vlm_description` is null.
    * A domain **without** a specialist -> `specialist_model` is null, `calibrated`
      is false, `findings` is empty, `warning` explains why, and `vlm_description`
      may carry free text.

    Free text never becomes a finding. A description is not a measurement, and the
    schema keeps the two apart.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    domain: str = Field(description="Domain key from domains.yaml, or 'unknown'.")
    domain_confidence: float = Field(ge=0.0, le=1.0)
    domain_confidence_calibrated: bool = Field(
        default=False,
        description=(
            "Whether `domain_confidence` itself has been temperature-scaled. Reported "
            "separately from `calibrated` because the two are genuinely different "
            "facts: the router can be calibrated for a domain that has no specialist "
            "at all, and in that case the confidence is trustworthy while the result "
            "is still not a measurement."
        ),
    )
    specialist_model: str | None = Field(
        default=None, description="Identifier of the specialist that ran, or null if none exists."
    )
    overall_severity: Severity | None = Field(
        default=None,
        description=(
            "How bad the damage is, judged over the whole photograph rather than "
            "summed from findings -- a total is not a sum of parts. Null where it "
            "was not estimated. Zero-shot and NOT calibrated: 64.5% over 248 "
            "held-out images, with `severe` recalled at 51%. The confusion matrix "
            "is in README section 7.8 and should be read before relying on this."
        ),
    )
    overall_severity_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Softmax score for the chosen band."
    )
    overall_severity_calibrated: Literal[False] = Field(
        default=False,
        description=(
            "Always false. The bands come from a zero-shot prompt ensemble with no "
            "fitted temperature behind them. Typed as a literal so it cannot become "
            "true without someone deleting this line and answering for it."
        ),
    )
    calibrated: bool = Field(
        description=(
            "Whether this *result* is a calibrated measurement. True only when a "
            "calibrated specialist produced the findings. See "
            "`domain_confidence_calibrated` for the routing confidence."
        )
    )
    findings: list[Finding] = Field(default_factory=list)
    vlm_description: str | None = Field(
        default=None, description="Free-text fallback description. Never derived into findings."
    )
    warning: WarningCode | None = None
    integrity: Integrity = Field(default_factory=Integrity)
    privacy: Privacy = Field(default_factory=Privacy)
    timing_ms: TimingMs

    @model_validator(mode="after")
    def _enforce_honesty_contract(self) -> Self:
        if self.specialist_model is None:
            # The core invariant. Without a specialist there is nothing that could
            # have produced a measured finding, so a non-empty list would be a lie.
            if self.findings:
                raise ValueError(
                    "findings must be empty when specialist_model is null: "
                    "no model produced them"
                )
            if self.calibrated:
                raise ValueError("calibrated must be false when specialist_model is null")
            if self.warning is None:
                raise ValueError(
                    "a response without a specialist must carry a warning explaining why"
                )
        elif self.vlm_description is not None and not self.findings:
            # A specialist ran and found nothing, yet text appeared. That is the
            # shape this contract exists to forbid: an empty measurement dressed
            # up in prose reads as an answer when it is the absence of one.
            #
            # A description *beside* findings is allowed, and is opt-in via
            # `vlm_augments_specialist`. It used to be forbidden outright, on the
            # grounds that a specialist running proved the VLM had not been
            # called -- a cost guarantee rather than an honesty one. That
            # guarantee now lives where it belongs: in the setting, in the
            # sign-in requirement, and in the budget, each with a contract test.
            # See ADR-032.
            raise ValueError(
                "vlm_description must be null when a specialist produced no findings: "
                "free text cannot stand in for a measurement that did not happen"
            )
        return self

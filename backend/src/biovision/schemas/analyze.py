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

from biovision.models.damage_position import Band, Level
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
    def _a_finding_is_damage(self) -> Self:
        """`Severity.NONE` is a whole-photograph band, never an instance.

        The enum gained it so an intact car had somewhere to go. A *finding* is
        by definition a piece of damage the specialist located, so "a finding of
        no damage" is not a weak claim -- it is a contradiction, and making it
        unrepresentable is cheaper than trusting every future caller not to.
        """
        if self.severity is Severity.NONE:
            raise ValueError(
                "a finding cannot have severity 'none': a finding IS damage. "
                "The undamaged band belongs to overall_severity."
            )
        return self

    @model_validator(mode="after")
    def _check_bbox(self) -> Self:
        x1, y1, x2, y2 = self.bbox
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"bbox must have positive width and height, got {self.bbox}")
        if x1 < 0 or y1 < 0:
            raise ValueError(f"bbox coordinates must be non-negative, got {self.bbox}")
        return self


class ZoneShareOut(BaseModel):
    """How much of one zone of the vehicle the damage covers."""

    model_config = ConfigDict(extra="forbid")

    band: Band = Field(
        description=(
            "A third across the vehicle AS THE PHOTOGRAPH FRAMES IT. Not "
            "front/rear: side-on these thirds are roughly bonnet, doors and "
            "boot, head-on they are left, middle and right of one bumper, and "
            "which you are looking at is a fact about the camera."
        )
    )
    level: Level = Field(
        description=(
            "Upper or lower half of the vehicle. This one survives the viewpoint "
            "problem, because gravity is in the photograph."
        )
    )
    share: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Damaged pixels over the VEHICLE's pixels in this zone, not over the "
            "zone's rectangle. A corner zone is mostly background, and dividing "
            "by the rectangle would make the same dent look smaller there."
        ),
    )


class DamagePositionOut(BaseModel):
    """Where the damage sits on the vehicle — and the claim this will not make.

    **It does not say "left front wing".** A photograph does not say which side
    of a car you are standing on: the same dent appears on the left of the frame
    whether it is the driver's door seen from outside or the passenger's door
    seen across the bonnet. Resolving that needs the vehicle's orientation, which
    needs another model and a measurement nobody here has made.

    So the zones are positions **in this photograph, relative to the vehicle's
    own footprint**, and the field names say so. It is less than an assessor
    wants and more than "a dent covering 36% of the vehicle", which is true and
    useless for finding it.

    No accuracy figure is attached because there is nothing to be accurate
    about: this describes a mask rather than predicting anything, and a
    description can only mislead through its units — which is what the naming is
    for.
    """

    model_config = ConfigDict(extra="forbid")

    zones: list[ZoneShareOut] = Field(
        description="Zones holding damage, heaviest first. Empty is not returned; the whole "
        "object is null instead."
    )
    dominant: ZoneShareOut = Field(description="The heaviest zone. Always the first of `zones`.")
    spans_whole_vehicle: bool = Field(
        description=(
            "True when every zone holds damage. Usually means the detector has "
            "smeared rather than that the car is uniformly wrecked, and a reader "
            "seeing six zones should be told that rather than left to notice."
        )
    )


class DamageRegionOut(BaseModel):
    """The damaged area as a single region — and what it is a fraction OF.

    This field exists because a user asked "42% of what?" and the honest answer
    was "of the photograph", which makes the number a measure of how close the
    photographer stood rather than of the damage. README 7.5 measures the same
    damage moving thirtyfold across four crops of one image.

    So the fraction of the **vehicle** is reported when the vehicle could be
    located, and `null` when it could not — never silently swapped for the frame
    figure. A field that means one thing on one request and another thing on the
    next is worse than a field that is sometimes absent.
    """

    model_config = ConfigDict(extra="forbid")

    area_ratio_image: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Damaged pixels over the whole photograph. Framing-sensitive: the "
            "same damage padded to twice the canvas retains a median 0.23 of "
            "this value."
        ),
    )
    area_ratio_vehicle: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Damaged pixels over the vehicle's own footprint, or null where no "
            "vehicle could be located. This is the framing-stable one — 0.92 of "
            "its value survives the same 100% pad — and it is the number that "
            "answers 'percent of what'."
        ),
    )
    vehicle_frame_share: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "How much of the photograph the vehicle fills, or null if it was not "
            "located. Lets a reader judge the frame-relative figure when the "
            "vehicle-relative one is missing: near 1.0 they nearly agree."
        ),
    )
    instances: int = Field(
        ge=0,
        description=(
            "Detections that contributed area. Normally MORE than `findings`, "
            "because the region uses a lower confidence floor — see below."
        ),
    )
    position: DamagePositionOut | None = Field(
        default=None,
        description=(
            "Where on the vehicle the damage sits, or null when no vehicle could "
            "be located — the same load-bearing null as `area_ratio_vehicle`, "
            "because without a vehicle there is no frame of reference."
        ),
    )
    confidence_floor: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "The floor used to build this region, deliberately below the one that "
            "produces findings. Area and instance identification are different "
            "questions with different measured optima (README 7.9), and reporting "
            "both floors is what stops the difference from looking like a bug."
        ),
    )
    calibrated: Literal[False] = Field(
        default=False,
        description=(
            "Always false. The region is a measured pixel union, but the mask "
            "boundaries it unions come from an uncalibrated segmenter that covers "
            "a measured 0.788 of annotated damage — a floor on the real area, not "
            "an estimate of it."
        ),
    )


class BandOutcomeOut(BaseModel):
    """One truth that stood behind a predicted band, and how often."""

    model_config = ConfigDict(extra="forbid")

    band: Severity
    count: int = Field(ge=0)
    share: float = Field(ge=0.0, le=1.0)


class SeverityReliabilityOut(BaseModel):
    """What `overall_severity` turned out to mean, counted rather than modelled.

    The only probability this API publishes. It is the confusion matrix of README
    7.8 read down its columns instead of across its rows: not "of the severe cars,
    how many did we catch" (recall, the developer's question) but "of the cars we
    called severe, how many were" — which is the question a reader holding a band
    actually has.

    The `moderate` column is why this exists. Of 73 photographs called moderate,
    37 were severe and 34 were moderate: the modal truth behind "orta" is "ağır".
    A product that printed the band alone would mislead in the expensive
    direction, and no change to the model fixes that — only printing this does.
    """

    model_config = ConfigDict(extra="forbid")

    predicted: Severity
    support: int = Field(ge=0, description="Photographs in the evaluation set that got this band.")
    outcomes: list[BandOutcomeOut]
    correct_share: float = Field(
        ge=0.0, le=1.0, description="How often this band was the true one."
    )
    worse_share: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How often the truth was WORSE than this band. Reported separately "
            "because the errors are asymmetric — the estimator under-calls — so "
            "this is the direction with a cost attached."
        ),
    )
    evaluation_set: str
    evaluation_note_tr: str = Field(
        description=(
            "The limit that makes these conditional: they are frequencies on one "
            "set whose band mix is not a claims queue's. P(true|predicted) moves "
            "with the prior."
        )
    )


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
    overall_severity_reliability: SeverityReliabilityOut | None = Field(
        default=None,
        description=(
            "What this band turned out to mean on 248 held-out images. Present "
            "whenever `overall_severity` is. This is the closest thing to a "
            "probability the system publishes, and it is a count rather than a "
            "model output."
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
    damage_region: DamageRegionOut | None = Field(
        default=None,
        description=(
            "The damaged area as one region, with the vehicle-relative fraction "
            "where the vehicle could be located. Null when no specialist ran or "
            "nothing was detected."
        ),
    )
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
                    "findings must be empty when specialist_model is null: no model produced them"
                )
            if self.damage_region is not None:
                # The same invariant as `findings`, and it needs stating
                # separately: a region is a measurement of area, so a region
                # without a model behind it is the same lie in a different shape.
                raise ValueError(
                    "damage_region must be null when specialist_model is null: "
                    "no model measured that area"
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

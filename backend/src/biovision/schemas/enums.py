"""Closed vocabularies used across the API.

Every string a client can branch on lives here. Magic strings scattered through
route handlers are how a contract quietly drifts.
"""

from __future__ import annotations

from enum import StrEnum


class DamageType(StrEnum):
    """The seven classes the VehiDE-trained vehicle specialist predicts.

    **This vocabulary follows the data, not the other way round.** It was written
    for CarDD's six classes; after counting what VehiDE actually contains
    (ADR-026) all seven match VehiDE. `tire_flat` is gone because VehiDE has no
    such annotations, and `surface_damage` went the same way in ADR-034 when the
    building specialist that emitted it was removed -- keeping either would
    advertise a class no model can emit. `torn`, `missing_part` and `punctured`
    are new, and together account for 30% of the dataset's instances; dropping
    them to preserve the old enum would have thrown away a third of the training
    signal to keep a list tidy.

    Ordering is alphabetical rather than meaningful. The model emits integer ids,
    so this order **is** the contract with the training notebook -- reordering it
    silently relabels every prediction. Alphabetical is chosen because it is the
    one rule that cannot drift as the dataset's class frequencies change.
    """

    DENT = "dent"
    GLASS_SHATTER = "glass_shatter"
    LAMP_BROKEN = "lamp_broken"
    MISSING_PART = "missing_part"
    PUNCTURED = "punctured"
    SCRATCH = "scratch"
    TORN = "torn"


class Severity(StrEnum):
    """Coarse damage extent.

    On a finding: the floor its damage CLASS carries, which `area_ratio` can raise
    but never lower. Thresholds over area alone were the earlier rule and were
    wrong -- area divides by the frame, so a wide shot of a wrecked car reported
    `minor` (README 7.5). `models.severity` holds the mapping and the measurement.

    Either way an **uncalibrated heuristic**: VehiDE carries no severity ground
    truth, so there is nothing to calibrate against. Responses carry
    `severity_calibrated: false` and no accuracy claim in the README covers this
    field.
    """

    #: No damage at all. Reachable ONLY as a whole-photograph band, never on a
    #: finding -- a finding IS damage, and `Finding` rejects this value.
    #:
    #: It exists because the band used to be a three-way softmax with nowhere to
    #: put an intact car, so a showroom photograph came back as `minor` at 72%.
    #: There was no threshold to tune: the answer was missing from the vocabulary.
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


class CorrectionKind(StrEnum):
    """What a user says is wrong with a result.

    Closed rather than free text, for the reason every vocabulary here is closed:
    an open field produces a thousand phrasings of five things and none of them
    counts. The note field carries the phrasing; this carries the count.
    """

    #: This finding is not there at all. The false-alarm case README 7.10 puts at
    #: 44% on intact vehicles before the strict floor, and 20% after.
    WRONG_FINDING = "wrong_finding"
    #: There is damage here that nothing reported. The case the published recall
    #: figures describe in aggregate and cannot point at.
    MISSED_DAMAGE = "missed_damage"
    #: Right place, wrong class.
    WRONG_TYPE = "wrong_type"
    #: Right damage, wrong band. Severity carries `severity_calibrated: false`
    #: precisely because there is no ground truth for it; this is where some
    #: would come from.
    WRONG_SEVERITY = "wrong_severity"
    #: The vehicle is undamaged and the result says otherwise.
    NOTHING_WRONG = "nothing_wrong"


class WarningCode(StrEnum):
    """Non-fatal conditions. The request succeeded; the answer is qualified."""

    NO_SPECIALIST = "no_specialist_model_for_domain"
    LOW_DOMAIN_CONFIDENCE = "low_domain_confidence"
    VLM_UNAVAILABLE = "vlm_unavailable"
    DUPLICATE_SUBMISSION = "duplicate_submission"


class ErrorCode(StrEnum):
    """Fatal conditions, one per HTTP status the API can return.

    | code                    | status |
    |-------------------------|--------|
    | file_too_large          | 413    |
    | unsupported_media_type  | 415    |
    | animated_image          | 415    |
    | corrupt_image           | 422    |
    | image_too_small         | 422    |
    | out_of_distribution     | 422    |
    | invalid_correction      | 422    |
    | unauthenticated         | 401    |
    | not_found               | 404    |
    | rate_limited            | 429    |
    | not_implemented         | 501    |
    | service_degraded        | 503    |
    """

    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    ANIMATED_IMAGE = "animated_image"
    CORRUPT_IMAGE = "corrupt_image"
    IMAGE_TOO_SMALL = "image_too_small"
    OUT_OF_DISTRIBUTION = "out_of_distribution"
    INVALID_CORRECTION = "invalid_correction"
    UNAUTHENTICATED = "unauthenticated"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    NOT_IMPLEMENTED = "not_implemented"
    SERVICE_DEGRADED = "service_degraded"


class ImageFormat(StrEnum):
    """Accepted upload formats.

    HEIC is included because iPhones produce it by default; rejecting it would
    exclude a large share of real-world uploads.
    """

    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    HEIC = "heic"


class Band(StrEnum):
    """A third across the vehicle, as the photograph frames it.

    **Not `front`/`rear`.** Photographed side-on these thirds are roughly the
    bonnet, the doors and the boot; photographed head-on they are the left, the
    middle and the right of the same bumper. Which one you are looking at is a
    fact about the camera, not about the car, so the names stay about the frame.

    Lives here rather than beside the arithmetic that produces it because it is a
    string a client branches on, and because `schemas` must not import `models`:
    that edge closed a cycle through `pipeline.types`, and only the alphabetical
    order of a few import blocks was keeping it from firing.
    """

    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"


class Level(StrEnum):
    """Upper or lower half of the vehicle's footprint.

    This one survives the viewpoint problem: gravity is in the photograph. The
    lower half is sills, bumpers and wheels; the upper half is glass, roof and
    the top of the wings, whichever way the car is facing.
    """

    UPPER = "upper"
    LOWER = "lower"


#: Domain key returned when the router's top prediction is below threshold. It is a
#: real answer ("I could not place this"), not an error, so it is not in ErrorCode.
UNKNOWN_DOMAIN = "unknown"

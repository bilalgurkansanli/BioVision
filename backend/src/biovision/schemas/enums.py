"""Closed vocabularies used across the API.

Every string a client can branch on lives here. Magic strings scattered through
route handlers are how a contract quietly drifts.
"""

from __future__ import annotations

from enum import StrEnum


class DamageType(StrEnum):
    """Damage classes across every specialist, not just one.

    **This vocabulary follows the data, not the other way round.** It was written
    for CarDD's six classes; after counting what VehiDE actually contains
    (ADR-026) seven of them match VehiDE. `tire_flat` is gone because VehiDE
    has no such annotations -- keeping it would have advertised a class no model
    can emit. `surface_damage` was added for the opposite reason: the building
    specialist emits it, so the enum would otherwise hide a class that exists.
    It is deliberately not called `crack`, even though its model was trained on
    cracks -- pointed at a mould-stained wall the model fires, and reporting
    that as a crack would be a false claim about the KIND of damage on top of a
    true one about its location.
    `torn`, `missing_part` and `punctured` are new, and together account for 30%
    of the dataset's instances; dropping them to preserve the old enum would have
    thrown away a third of the training signal to keep a list tidy.

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
    #: Building specialist only, and named for what the evidence supports rather
    #: than for what its model was trained on. METU/Özgenel is crack-vs-plain
    #: concrete; off that distribution -- which every konut interior is -- what
    #: the model responds to is a surface that is not plain, and the CLIP veto
    #: only confirms the surface is a wall. Together they support "this wall
    #: looks damaged", not "this is a crack". A screenshot of a mould-stained
    #: wall reported as `crack` is what prompted the rename.
    SURFACE_DAMAGE = "surface_damage"
    TORN = "torn"


class Severity(StrEnum):
    """Coarse damage extent.

    Derived from `area_ratio` by fixed thresholds. This is an **uncalibrated
    heuristic**: VehiDE carries no severity ground truth, so there is nothing to
    calibrate against. Responses carry `severity_calibrated: false` and no accuracy
    claim in the README covers this field.
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


class WarningCode(StrEnum):
    """Non-fatal conditions. The request succeeded; the answer is qualified."""

    NO_SPECIALIST = "no_specialist_model_for_domain"
    #: A specialist ran, and the sets it was measured on are small enough that
    #: its findings are suggestions rather than determinations. The building
    #: crack specialist is measured on 60 cracked walls and 15 intact rooms,
    #: neither of which contains a Turkish residential interior.
    SPECIALIST_SMALL_EVALUATION = "specialist_small_evaluation"
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


#: Domain key returned when the router's top prediction is below threshold. It is a
#: real answer ("I could not place this"), not an error, so it is not in ErrorCode.
UNKNOWN_DOMAIN = "unknown"

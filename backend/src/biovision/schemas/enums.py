"""Closed vocabularies used across the API.

Every string a client can branch on lives here. Magic strings scattered through
route handlers are how a contract quietly drifts.
"""

from __future__ import annotations

from enum import StrEnum


class DamageType(StrEnum):
    """The six classes the CarDD-trained vehicle specialist predicts."""

    DENT = "dent"
    SCRATCH = "scratch"
    CRACK = "crack"
    GLASS_SHATTER = "glass_shatter"
    LAMP_BROKEN = "lamp_broken"
    TIRE_FLAT = "tire_flat"


class Severity(StrEnum):
    """Coarse damage extent.

    Derived from `area_ratio` by fixed thresholds. This is an **uncalibrated
    heuristic**: CarDD carries no severity ground truth, so there is nothing to
    calibrate against. Responses carry `severity_calibrated: false` and no accuracy
    claim in the README covers this field.
    """

    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


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

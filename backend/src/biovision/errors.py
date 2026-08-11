"""Domain exceptions.

Deliberately framework-free so the pipeline can raise them without importing
FastAPI. ``api/errors.py`` owns the single place that turns them into HTTP
responses, which is what keeps the status-code table in the README true.
"""

from __future__ import annotations

from biovision.schemas.enums import ErrorCode


class BioVisionError(Exception):
    """Base class for every failure that maps to a documented status code."""

    code: ErrorCode
    status_code: int

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class FileTooLargeError(BioVisionError):
    code = ErrorCode.FILE_TOO_LARGE
    status_code = 413


class UnsupportedMediaTypeError(BioVisionError):
    code = ErrorCode.UNSUPPORTED_MEDIA_TYPE
    status_code = 415


class AnimatedImageError(BioVisionError):
    """Animated GIF/WebP.

    415 rather than 422: the problem is the container format, not the content. A
    single frame cannot be assumed to represent the damage, and picking one for the
    user would be a silent guess.
    """

    code = ErrorCode.ANIMATED_IMAGE
    status_code = 415


class CorruptImageError(BioVisionError):
    code = ErrorCode.CORRUPT_IMAGE
    status_code = 422


class ImageTooSmallError(BioVisionError):
    code = ErrorCode.IMAGE_TOO_SMALL
    status_code = 422


class OutOfDistributionError(BioVisionError):
    """Rejected by the gate: this is not a photograph of damage or an object."""

    code = ErrorCode.OUT_OF_DISTRIBUTION
    status_code = 422


class RateLimitedError(BioVisionError):
    code = ErrorCode.RATE_LIMITED
    status_code = 429


class NotImplementedYetError(BioVisionError):
    """A documented endpoint whose implementation lands in a later phase.

    501 rather than a plausible-looking empty result. An endpoint that returns
    ``[]`` because it was never built is indistinguishable from one that returns
    ``[]`` because there is genuinely nothing there -- and this project does not get
    to apply its honesty rule only to model outputs.
    """

    code = ErrorCode.NOT_IMPLEMENTED
    status_code = 501


class ServiceDegradedError(BioVisionError):
    """The VLM budget is exhausted.

    Raised only when the fallback path is the *only* way to answer. Requests for a
    domain that has a specialist keep returning 200: the service degrades, it does
    not fail. Note the distinction from a VLM that is merely disabled for this
    caller -- that returns 200 with a warning, because nothing has broken.
    """

    code = ErrorCode.SERVICE_DEGRADED
    status_code = 503

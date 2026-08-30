"""Mapping domain exceptions onto HTTP responses.

One place, one table. The status codes documented in the README are the ones
produced here, and a contract test walks every ``BioVisionError`` subclass to make
sure none of them can escape as an untyped 500.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from biovision.errors import BioVisionError
from biovision.schemas.enums import ErrorCode
from biovision.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _envelope(status_code: int, detail: ErrorDetail) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=detail).model_dump(mode="json"),
    )


async def biovision_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BioVisionError)
    logger.info("%s -> %d: %s", exc.code.value, exc.status_code, exc.message)
    return _envelope(exc.status_code, ErrorDetail(code=exc.code, message=exc.message))


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """FastAPI request-validation failures.

    **A body failure is 415; anything else is 422.**

    The upload endpoint reports 415 rather than the framework default, because
    there the only way to fail validation is to omit the file or send something
    that is not a multipart upload -- and keeping 422 exclusively for "the gate
    rejected your photograph" makes that status unambiguous.

    That reasoning was written when `/v1/analyze` was the only endpoint taking
    input, and it was baked into a handler registered for the whole app. Adding
    `/v1/claims`, whose inputs are query parameters, made it wrong: a missing
    `vehicle_value_try` came back as "send a multipart body with an image file".
    The discriminator became the error's own location rather than an assumption
    about which endpoint is being called.

    **That was still too coarse, and the same defect came back.** `POST
    /v1/claims/assessment` takes a JSON body, so a model validator rejecting an
    incoherent request -- two thirds of a vehicle trim, which names a different
    car -- also reports `loc == ("body",)`, and a caller sending perfectly good
    JSON was told to send a multipart image instead. Caught by a contract test,
    which is the second time this handler has been fixed by one.

    The discriminator is now the declared content type, which is the fact the
    415 is actually about: a client that sent JSON has a *content* problem, and
    telling them their media type is unsupported is simply false.
    """
    assert isinstance(exc, RequestValidationError)
    logger.info("request validation failed: %s", exc.errors())

    errors = exc.errors()
    from_body = any(error.get("loc", (None,))[0] == "body" for error in errors)
    sent_json = request.headers.get("content-type", "").startswith("application/json")

    if from_body and not sent_json:
        return _envelope(
            415,
            ErrorDetail(
                code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                message="Malformed request. Send a multipart/form-data body with an 'image' file.",
            ),
        )

    # Body-level failures from a model validator have no field path -- the whole
    # object is what is wrong -- so the validator's own message is carried
    # through. It is written for a human and it names the actual problem, which
    # "Invalid or missing parameter: ?" does not.
    details = []
    for error in errors:
        path = ".".join(str(part) for part in error.get("loc", ())[1:])
        details.append(f"{path}: {error.get('msg', '')}" if path else str(error.get("msg", "")))

    return _envelope(
        422,
        ErrorDetail(
            code=ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            message=f"Invalid or missing parameter: {'; '.join(details)}",
        ),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort.

    The traceback goes to the logs with a correlation id; the client gets the id and
    nothing else. Leaking internals into an error body is how stack traces end up in
    a screenshot.
    """
    incident = uuid4()
    logger.exception("unhandled error incident=%s path=%s", incident, request.url.path)
    return _envelope(
        500,
        ErrorDetail(
            code=ErrorCode.SERVICE_DEGRADED,
            message="Internal error. Quote the request_id when reporting this.",
            request_id=incident,
        ),
    )


#: Which documented code carries each status a route may raise directly. The
#: envelope has a fixed vocabulary, so a status without a code here would leak
#: FastAPI's own shape.
_STATUS_CODES = {
    401: ErrorCode.UNAUTHENTICATED,
    404: ErrorCode.NOT_FOUND,
    413: ErrorCode.FILE_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.CORRUPT_IMAGE,
    429: ErrorCode.RATE_LIMITED,
    501: ErrorCode.NOT_IMPLEMENTED,
    503: ErrorCode.SERVICE_DEGRADED,
}


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Route-raised HTTPExceptions, put into the project's envelope.

    Without this they leave as FastAPI's `{"detail": "..."}`, which the frontend
    client cannot read -- it parses `{"error": {code, message, request_id}}` and
    would show a generic failure instead of the sentence the route wrote. The
    claims routes surfaced this: "TSB listesi yalnızca 2012-2026 model yıllarını
    kapsar" is exactly the message a user needs, and it was being discarded.

    An unmapped status falls back to service_degraded rather than inventing a
    code, and says so in the log.
    """
    assert isinstance(exc, HTTPException)
    code = _STATUS_CODES.get(exc.status_code)
    if code is None:
        logger.warning(
            "status %d has no documented ErrorCode; reporting as service_degraded",
            exc.status_code,
        )
        code = ErrorCode.SERVICE_DEGRADED

    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    logger.info("http error %d: %s", exc.status_code, message)
    return _envelope(exc.status_code, ErrorDetail(code=code, message=message))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BioVisionError, biovision_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
